"""
STEP 7 - Assemble model-ready tables.

Stacks per cell: geometry/QC + labels + own-marker P(positive) + spatial features + micro_env.
Stores each cohort's OWN markers (renamed x_<marker>); the 102-marker UNION alignment + the
measured-mask are rebuilt cheaply at load time by common.load_model() - storing 55 all-NaN
columns per cohort would just waste GBs and blow memory.

Column-stacking is done with pyarrow (no pandas merge) because a 2.6M x ~200 float32 merge
doubles memory during consolidation and OOMs.

Output: harmonised/model/{cohort}_model.parquet
        harmonised/model/feature_columns.json
        _audit/step7_report.md
"""
import numpy as np, pandas as pd, os, json
import pyarrow as pa, pyarrow.parquet as pq
from common import COHORTS, OUT, AUDIT

MODEL = os.path.join(OUT, "model"); os.makedirs(MODEL, exist_ok=True)
PANEL = json.load(open(os.path.join(AUDIT, "panel.json")))
UNION = PANEL["union"]; PER_COHORT = PANEL["per_cohort"]

GEO   = ['cell_id','cohort','image_id','patient_id','x_um','y_um','area_um2','qc_flag','is_clean']
LABEL = ['native_label','cl_id','cl_name','L1','L2','state','keep','ambiguous','label_confidence','is_gold']

def _t(path, columns=None):
    return pq.read_table(os.path.join(OUT, path), columns=columns)

def assemble(cohort):
    cel = _t(f"{cohort}_cells.parquet", GEO)
    lab = _t(f"{cohort}_labels.parquet", ['cell_id'] + LABEL)
    exf = _t(f"{cohort}_expr.parquet")
    own = [c for c in exf.column_names if c != 'cell_id' and not c.startswith('pct_')]
    spa = _t(f"{cohort}_spatial_r30.parquet")
    me  = _t(f"{cohort}_microenv.parquet")

    cid = cel['cell_id'].to_numpy()
    for name, t in [('labels', lab), ('expr', exf), ('spatial', spa), ('microenv', me)]:
        assert np.array_equal(t['cell_id'].to_numpy(), cid), f"{cohort} {name} cell_id misaligned"

    d = {}
    for c in GEO:                       d[c] = cel[c]
    for c in LABEL:                     d[c] = lab[c]
    for m in own:                       d['x_' + m] = exf[m]
    for c in spa.column_names:
        if c != 'cell_id':              d[c] = spa[c]
    d['micro_env'] = me['micro_env']

    tbl = pa.table(d)
    pq.write_table(tbl, os.path.join(MODEL, f"{cohort}_model.parquet"))
    return tbl.num_rows, tbl.num_columns, own

def main():
    layouts = {}
    rows = []
    for c in COHORTS:
        n, ncol, own = assemble(c)
        m = pd.read_parquet(os.path.join(MODEL, f"{c}_model.parquet"),
                            columns=['is_gold', 'is_clean'])
        gc = int((m.is_gold & m.is_clean).sum())
        rows.append(dict(cohort=c, rows=n, cols=ncol, own_markers=len(own),
                         gold=int(m.is_gold.sum()), gold_clean=gc))
        layouts[c] = own
        print(f"[{c:8s}] {n:>9,} rows x {ncol} cols  own_markers {len(own)}  gold&clean {gc:>9,}")

    # feature-block layout + union recipe for the model/ablation step
    sample = pd.read_parquet(os.path.join(MODEL, "Keren_model.parquet")).columns.tolist()
    layout = {
        'union_markers': UNION,                         # 102, order fixed
        'per_cohort_markers': PER_COHORT,               # which each cohort actually has
        'marker_cols': ['x_' + m for m in UNION],       # THE feature columns - use this list, NOT a 'x_' prefix scan
        'mask_cols':   ['mask_' + m for m in UNION],    # built at load by common.load_model
        'coord_cols':  ['x_um', 'y_um'],                # NOTE: x_um also starts with 'x_' but is a COORDINATE, not a marker
        'morphology': ['area_um2'],
        'spatial_local':  [c for c in sample if c.startswith('nb_')] + ['density_30um', 'micro_env'],
        'spatial_global': [c for c in sample if c.startswith('img_')],
        'label_cols': LABEL,
        'group_cols': ['cohort', 'image_id', 'patient_id'],
        'note': 'load with common.load_model(cohort): reindexes x_ to union order + builds mask_.',
    }
    json.dump(layout, open(os.path.join(MODEL, "feature_columns.json"), "w"), indent=1)

    t = pd.DataFrame(rows)
    rep = ["# STEP 7 - Assembled model tables\n",
           "Each `model/{cohort}_model.parquet`: geometry + labels + own-marker `x_*` P(positive) "
           "+ spatial `nb_*/img_*/density_30um/micro_env`. UNION(102) + mask rebuilt at load "
           "(`common.load_model`).\n", t.to_markdown(index=False)]
    open(os.path.join(AUDIT, "step7_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("\n" + t.to_string(index=False))
    print("\nwrote harmonised/model/{cohort}_model.parquet + feature_columns.json")

if __name__ == "__main__":
    main()

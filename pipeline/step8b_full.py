"""
STEP 8b - FULL run: all 102 union markers (vs Stage-1's 19-marker backbone).

Lifts the biggest Stage-1 limiter (backbone-only). Same LOCO ablation (expr vs expr+spatial),
same gradient-boosting model, but features use the full 102-marker UNION + measured-mask, with
spatial features union-aligned too. Gradient boosting handles the many NaNs natively.

Memory-safe on a ~2 GB box:
  - training: subsample each cohort's resolved-L2 cells, union-align the small frame, fit.
  - testing: STREAM the held cohort in row-batches (pyarrow), union-align + predict per batch,
    never holding the full ~3 GB test matrix.

Output: harmonised/model/step8b_full_results.csv + _audit/step8b_report.md
"""
import numpy as np, pandas as pd, os, json, time
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import f1_score
from common import COHORTS, OUT, AUDIT

PANEL = json.load(open(os.path.join(AUDIT, "panel.json")))
UNION = PANEL["union"]; PER_COHORT = PANEL["per_cohort"]
BACKBONE = PANEL["backbone"]
MODEL = os.path.join(OUT, "model")
RNG = np.random.default_rng(0)
CAP = 120_000            # train subsample per cohort (546 features; memory-safe concat of 4)
BATCH = 200_000          # test streaming batch size

L2_L1 = {'T cell':'Immune','B/Plasma':'Immune','Myeloid':'Immune','NK':'Immune',
         'Granulocyte':'Immune','Endothelial':'Stromal','Fibroblast/Muscle':'Stromal',
         'Other':'Stromal','Epithelial/Tumour':'Epithelial/Tumour'}
L1S = ['Immune','Stromal','Epithelial/Tumour']

# feature column order (identical for train and test)
EXPR_COLS = [f'x_{m}' for m in UNION] + [f'mask_{m}' for m in UNION] + ['area_um2']
SPA_COLS  = ([f'nb_mean_{m}' for m in UNION] + [f'nb_std_{m}' for m in BACKBONE]
             + [f'img_mean_{m}' for m in UNION] + [f'img_pos_{m}' for m in UNION]
             + ['density_30um'] + [f'me_{k}' for k in range(15)])
ALL_COLS  = EXPR_COLS + SPA_COLS

# which own columns to read from a cohort's model parquet
def read_cols(cohort, schema):
    want = ['is_gold','is_clean','L1','L2','label_confidence','area_um2','density_30um','micro_env']
    for m in UNION:
        for p in ('x_','nb_mean_','img_mean_','img_pos_'):
            want.append(p+m)
    for m in BACKBONE:
        want.append('nb_std_'+m)
    return [c for c in want if c in schema]

def align(d, cohort):
    """own-column frame -> full union-aligned feature frame (adds NaN cols + mask)."""
    own = set(PER_COHORT[cohort]); n = len(d)
    out = {}
    for m in UNION:
        out[f'x_{m}']       = d[f'x_{m}'].to_numpy('float32')       if f'x_{m}' in d else np.full(n, np.nan, 'float32')
        out[f'mask_{m}']    = np.full(n, 1.0 if m in own else 0.0, 'float32')
        out[f'nb_mean_{m}'] = d[f'nb_mean_{m}'].to_numpy('float32') if f'nb_mean_{m}' in d else np.full(n, np.nan, 'float32')
        out[f'img_mean_{m}']= d[f'img_mean_{m}'].to_numpy('float32')if f'img_mean_{m}' in d else np.full(n, np.nan, 'float32')
        out[f'img_pos_{m}'] = d[f'img_pos_{m}'].to_numpy('float32') if f'img_pos_{m}' in d else np.full(n, np.nan, 'float32')
    for m in BACKBONE:
        out[f'nb_std_{m}']  = d[f'nb_std_{m}'].to_numpy('float32')  if f'nb_std_{m}' in d else np.full(n, np.nan, 'float32')
    out['area_um2']    = d['area_um2'].to_numpy('float32')
    out['density_30um']= d['density_30um'].to_numpy('float32')
    me = d['micro_env'].to_numpy()
    for k in range(15):
        out[f'me_{k}'] = (me == k).astype('float32')
    return pd.DataFrame(out)

def train_frame(cohort):
    path = os.path.join(MODEL, f"{cohort}_model.parquet")
    schema = set(pq.ParquetFile(path).schema_arrow.names)
    d = pd.read_parquet(path, columns=read_cols(cohort, schema))
    d = d[d.is_gold.values & d.is_clean.values]
    d = d[d.L2.values != '']
    if len(d) > CAP:
        d = d.sample(CAP, random_state=0)
    X = align(d, cohort)
    X['L2'] = d['L2'].values; X['conf'] = d['label_confidence'].to_numpy('float32')
    return X

def stream_predict(clf, cohort, feat_cols):
    """predict the whole held cohort in batches; return (yL1_true, predL1, yL2_true, predL2)."""
    path = os.path.join(MODEL, f"{cohort}_model.parquet")
    pf = pq.ParquetFile(path)
    schema = set(pf.schema_arrow.names)
    cols = read_cols(cohort, schema)
    yL1, pL1, yL2, pL2 = [], [], [], []
    for batch in pf.iter_batches(batch_size=BATCH, columns=cols):
        d = batch.to_pandas()
        d = d[d.is_gold.values & d.is_clean.values]
        if len(d) == 0:
            continue
        X = align(d, cohort)[feat_cols].to_numpy('float32')
        pred = clf.predict(X)
        pl1 = pd.Series(pred).map(L2_L1).values
        yL1.append(d['L1'].values); pL1.append(pl1)
        m = d['L2'].values != ''
        if m.any():
            yL2.append(d['L2'].values[m]); pL2.append(pred[m])
    cat = lambda xs: np.concatenate(xs) if xs else np.array([])
    return cat(yL1), cat(pL1), cat(yL2), cat(pL2)

def macro(y, p):
    return f1_score(y, p, average='macro', labels=sorted(pd.unique(y)), zero_division=0) if len(y) else np.nan

def fit(tr, cols):
    # drop columns that are all-NaN in TRAIN (markers absent from every training cohort ->
    # no learnable signal, and they crash HistGB's binning). Predict must use the same subset.
    valid = [c for c in cols if tr[c].notna().any()]
    clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, l2_regularization=1.0,
        class_weight='balanced', random_state=0, early_stopping=False)
    clf.fit(tr[valid].to_numpy('float32'), tr.L2.values, sample_weight=tr.conf.values)
    return clf, valid

CACHE = os.path.join(MODEL, "_traincache")

def main():
    os.makedirs(CACHE, exist_ok=True)
    print("caching full-union training frames to disk ...", flush=True)
    for c in COHORTS:                                  # write to disk, do NOT hold all in RAM
        tf = train_frame(c)
        tf.to_parquet(os.path.join(CACHE, f"{c}.parquet"), index=False)
        print(f"  {c:8s}: cached {len(tf):,} train cells (full union)", flush=True)
        del tf

    rows = []
    for held in COHORTS:
        tr = pd.concat([pd.read_parquet(os.path.join(CACHE, f"{c}.parquet"))
                        for c in COHORTS if c != held], ignore_index=True)
        res = {'held_out': held, 'n_train': len(tr)}
        for name, cols in [('expr', EXPR_COLS), ('expr+spatial', ALL_COLS)]:
            t0 = time.time()
            clf, valid = fit(tr, cols)
            yL1, pL1, yL2, pL2 = stream_predict(clf, held, valid)
            res[f'{name}_F1_L1'] = round(float(macro(yL1, pL1)), 4)
            res[f'{name}_F1_L2'] = round(float(macro(yL2, pL2)), 4) if len(yL2) else None
            res[f'{name}_sec']   = round(time.time()-t0, 1)
        res['dF1_L1'] = round(res['expr+spatial_F1_L1'] - res['expr_F1_L1'], 4)
        rows.append(res)
        print(f"[{held:8s}] L1 expr={res['expr_F1_L1']} +spatial={res['expr+spatial_F1_L1']} "
              f"dF1={res['dF1_L1']:+.4f} | L2 expr={res['expr_F1_L2']} +spatial={res['expr+spatial_F1_L2']}",
              flush=True)
        del tr, clf

    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(MODEL, "step8b_full_results.csv"), index=False)
    rep = ["# STEP 8b - FULL 102-union run\n",
           "Same LOCO ablation as Step 8 but full 102-marker union (vs 19-marker backbone).\n",
           R.to_markdown(index=False),
           f"\n**Mean L1: expr {R['expr_F1_L1'].mean():.3f} -> +spatial {R['expr+spatial_F1_L1'].mean():.3f} "
           f"(dF1 {R['dF1_L1'].mean():+.3f})**",
           f"\nMean L2 (excl ferguson): expr {R[R.held_out!='ferguson']['expr_F1_L2'].mean():.3f} "
           f"-> +spatial {R[R.held_out!='ferguson']['expr+spatial_F1_L2'].mean():.3f}",
           "\nCompare to Stage-1 backbone: L1 0.620->0.630, L2 ~0.41."]
    open(os.path.join(AUDIT, "step8b_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("\n" + R.to_string(index=False), flush=True)

if __name__ == "__main__":
    main()

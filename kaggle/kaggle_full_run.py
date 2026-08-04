"""
================================================================================
 FULL-SCALE CROSS-COHORT RUN  -  for Kaggle (30 GB RAM)
================================================================================
Self-contained. Paste this whole file into ONE Kaggle notebook cell and Run All.
It reproduces our experiments WITHOUT the local memory cap, using Kaggle's 30 GB.

It needs only these files, uploaded once as a Kaggle Dataset (see INSTRUCTIONS.md):
    model/CRC_model.parquet   model/HubMap_model.parquet   ... (all 5)
    feature_columns.json      panel.json

Set INPUT_DIR below to where Kaggle mounts that dataset (shown in the right panel,
usually /kaggle/input/<your-dataset-name>).

Outputs (download from the Kaggle "Output" tab):
    /kaggle/working/full_loco.csv        cross-cohort (train 4, test 1) - expr vs +spatial
    /kaggle/working/full_within.csv      within-cohort 5-fold (the ceiling)
================================================================================
"""
import numpy as np, pandas as pd, os, json, time
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score

# ----------------------------- CONFIG (edit me) -----------------------------
INPUT_DIR = "/kaggle/input/cross-cohort-model"   # <-- folder holding model/ + the two .json
OUT_DIR   = "/kaggle/working"
PANEL_SET = "union"        # "union" = all 102 markers (the heavy full run) | "backbone" = 19 shared
CAP       = None           # None = use ALL cells (needs ~11 GB for union). Set e.g. 300_000 if OOM.
BATCH     = 200_000        # test streaming batch size (keeps the wide test matrix off memory)
RUN_LOCO   = True          # cross-cohort experiment
RUN_WITHIN = True          # within-cohort ceiling experiment
# ----------------------------------------------------------------------------

COHORTS = ['CRC', 'HubMap', 'Keren', 'UPMC', 'ferguson']
MODELDIR = os.path.join(INPUT_DIR, "model")
lay = json.load(open(os.path.join(INPUT_DIR, "feature_columns.json")))
UNION = lay["union_markers"]; PER_COHORT = lay["per_cohort_markers"]
try:
    BACKBONE = json.load(open(os.path.join(INPUT_DIR, "panel.json")))["backbone"]
except Exception:
    # fallback only - gene-symbol names, must match panel.json (Step 1, 2026-08-04 naming)
    BACKBONE = ['ACTA2','CD274','CD3E','CD4','CD68','CD8A','FCGR3A','FOXP3','HLA-DRA','ITGAX',
                'KRT_PAN','MKI67','MS4A1','PDCD1','PDPN','PECAM1','PTPRC','PTPRC_RO','VIM']
MARK = UNION if PANEL_SET == "union" else BACKBONE
os.makedirs(OUT_DIR, exist_ok=True)

L2_L1 = {'T cell':'Immune','B/Plasma':'Immune','Myeloid':'Immune','NK':'Immune',
         'Granulocyte':'Immune','Endothelial':'Stromal','Fibroblast/Muscle':'Stromal',
         'Other':'Stromal','Epithelial/Tumour':'Epithelial/Tumour'}

# feature column layout (same order for train and test)
EXPR_COLS = [f'x_{m}' for m in MARK] + [f'mask_{m}' for m in MARK] + ['area_um2']
SPA_COLS  = ([f'nb_mean_{m}' for m in MARK] + [f'nb_std_{m}' for m in BACKBONE]
             + [f'img_mean_{m}' for m in MARK] + [f'img_pos_{m}' for m in MARK]
             + ['density_30um'] + [f'me_{k}' for k in range(15)])
ALL_COLS  = EXPR_COLS + SPA_COLS


def read_cols(cohort, schema):
    want = ['cell_id','is_gold','is_clean','L1','L2','label_confidence','area_um2',
            'density_30um','micro_env']
    for m in MARK:
        for p in ('x_','nb_mean_','img_mean_','img_pos_'):
            want.append(p+m)
    for m in BACKBONE:
        want.append('nb_std_'+m)
    return [c for c in want if c in schema]


def align(d, cohort):
    """own-column frame -> full feature frame (adds NaN + mask for markers this cohort lacks)."""
    own = set(PER_COHORT[cohort]); n = len(d); out = {}
    for m in MARK:
        out[f'x_{m}']        = d[f'x_{m}'].to_numpy('float32')        if f'x_{m}' in d else np.full(n, np.nan,'float32')
        out[f'mask_{m}']     = np.full(n, 1.0 if m in own else 0.0, 'float32')
        out[f'nb_mean_{m}']  = d[f'nb_mean_{m}'].to_numpy('float32')  if f'nb_mean_{m}' in d else np.full(n, np.nan,'float32')
        out[f'img_mean_{m}'] = d[f'img_mean_{m}'].to_numpy('float32') if f'img_mean_{m}' in d else np.full(n, np.nan,'float32')
        out[f'img_pos_{m}']  = d[f'img_pos_{m}'].to_numpy('float32')  if f'img_pos_{m}' in d else np.full(n, np.nan,'float32')
    for m in BACKBONE:
        out[f'nb_std_{m}']   = d[f'nb_std_{m}'].to_numpy('float32')   if f'nb_std_{m}' in d else np.full(n, np.nan,'float32')
    out['area_um2']     = d['area_um2'].to_numpy('float32')
    out['density_30um'] = d['density_30um'].to_numpy('float32')
    me = d['micro_env'].to_numpy()
    for k in range(15):
        out[f'me_{k}'] = (me == k).astype('float32')
    return pd.DataFrame(out)


def train_frame(cohort, cap=CAP):
    path = os.path.join(MODELDIR, f"{cohort}_model.parquet")
    schema = set(pq.ParquetFile(path).schema_arrow.names)
    d = pd.read_parquet(path, columns=read_cols(cohort, schema))
    d = d[d.is_gold.values & d.is_clean.values]
    d = d[d.L2.values != '']
    if cap and len(d) > cap:
        d = d.sample(cap, random_state=0)
    X = align(d, cohort)
    X['L2'] = d['L2'].values; X['conf'] = d['label_confidence'].to_numpy('float32')
    X['L1'] = d['L1'].values
    return X


def valid_cols(tr, cols):
    return [c for c in cols if tr[c].notna().any()]      # drop all-NaN-in-train (HistGB crash fix)


def new_clf():
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, l2_regularization=1.0,
        class_weight='balanced', random_state=0, early_stopping=False)


def macro(y, p):
    return float(f1_score(y, p, average='macro', labels=sorted(pd.unique(y)), zero_division=0)) if len(y) else np.nan


def stream_predict(clf, cohort, feat_cols):
    """predict the whole held cohort in row-batches; return true/pred at L1 and L2."""
    pf = pq.ParquetFile(os.path.join(MODELDIR, f"{cohort}_model.parquet"))
    cols = read_cols(cohort, set(pf.schema_arrow.names))
    yL1,pL1,yL2,pL2 = [],[],[],[]
    for batch in pf.iter_batches(batch_size=BATCH, columns=cols):
        d = batch.to_pandas(); d = d[d.is_gold.values & d.is_clean.values]
        if len(d)==0: continue
        pred = clf.predict(align(d, cohort)[feat_cols].to_numpy('float32'))
        yL1.append(d['L1'].values); pL1.append(pd.Series(pred).map(L2_L1).values)
        m = d['L2'].values != ''
        if m.any(): yL2.append(d['L2'].values[m]); pL2.append(pred[m])
    cat = lambda xs: np.concatenate(xs) if xs else np.array([])
    return cat(yL1),cat(pL1),cat(yL2),cat(pL2)


def run_loco():
    print(f"\n=== FULL LOCO ({PANEL_SET}, cap={CAP}) ===", flush=True)
    frames = {c: train_frame(c) for c in COHORTS}
    for c in COHORTS: print(f"  {c:8s}: {len(frames[c]):,} train cells", flush=True)
    rows = []
    for held in COHORTS:
        tr = pd.concat([frames[c] for c in COHORTS if c != held], ignore_index=True)
        res = {'held_out': held, 'n_train': len(tr)}
        for nm, cols in [('expr', EXPR_COLS), ('spatial', ALL_COLS)]:
            t0 = time.time(); v = valid_cols(tr, cols); clf = new_clf()
            clf.fit(tr[v].to_numpy('float32'), tr.L2.values, sample_weight=tr.conf.values)
            yL1,pL1,yL2,pL2 = stream_predict(clf, held, v)
            res[f'{nm}_F1_L1'] = round(macro(yL1,pL1),4)
            res[f'{nm}_F1_L2'] = round(macro(yL2,pL2),4) if len(yL2) else None
            res[f'{nm}_sec']   = round(time.time()-t0,1)
        res['dF1_L1'] = round(res['spatial_F1_L1']-res['expr_F1_L1'],4)
        rows.append(res); print(f"[{held:8s}] {res}", flush=True)
        del tr, clf
    R = pd.DataFrame(rows); R.to_csv(os.path.join(OUT_DIR,"full_loco.csv"), index=False)
    print("\nMean L1: expr %.3f -> +spatial %.3f" % (R.expr_F1_L1.mean(), R.spatial_F1_L1.mean()))
    print(R.to_string(index=False))


def run_within():
    print(f"\n=== WITHIN-COHORT 5-fold ({PANEL_SET}, cap={CAP}) ===", flush=True)
    rows = []
    for c in COHORTS:
        F = train_frame(c)
        if F.L2.nunique() < 2:
            print(f"[within {c}] 1 L2 class -> skip"); continue
        skf = StratifiedKFold(5, shuffle=True, random_state=0)
        for nm, cols in [('expr', EXPR_COLS), ('spatial', ALL_COLS)]:
            f1s = []
            for tr_i, te_i in skf.split(F, F.L2):
                tr, te = F.iloc[tr_i], F.iloc[te_i]; v = valid_cols(tr, cols); clf = new_clf()
                clf.fit(tr[v].to_numpy('float32'), tr.L2.values, sample_weight=tr.conf.values)
                pred = clf.predict(te[v].to_numpy('float32'))
                f1s.append(macro(te.L1.values, pd.Series(pred).map(L2_L1).values))
            rows.append({'cohort': c, 'features': nm, 'F1_L1': round(np.mean(f1s),4)})
            print(f"[within {c:8s} {nm:8s}] L1={rows[-1]['F1_L1']}", flush=True)
        del F
    pd.DataFrame(rows).to_csv(os.path.join(OUT_DIR,"full_within.csv"), index=False)


if __name__ == "__main__":
    t0 = time.time()
    if RUN_LOCO:   run_loco()
    if RUN_WITHIN: run_within()
    print(f"\nALL DONE in {(time.time()-t0)/60:.1f} min", flush=True)

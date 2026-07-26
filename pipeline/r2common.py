"""
Shared helpers for the 2nd evaluation report (Steps 10a/10b).

Builds a small, memory-bounded per-cohort feature cache on the 19-marker BACKBONE so every
follow-up experiment (within-cohort CV, skip-ferguson LOCO, k10-vs-r30 graph, model zoo) reads
the SAME frames and stays apples-to-apples. Everything here mirrors step8's backbone features.

Cap: to keep peak memory < ~1 GB and runs fast on a 2 GB box, each cohort is randomly
subsampled to CAP gold&clean cells. Deltas (spatial gain, k10-r30, model gaps) are the signal;
absolute F1 will differ slightly from step8's FULL-cohort numbers (stated in the report).
"""
import numpy as np, pandas as pd, os, json, tempfile
import pyarrow.parquet as pq
from common import COHORTS, OUT, AUDIT

BACKBONE = json.load(open(os.path.join(AUDIT, "panel.json")))["backbone"]
MODEL = os.path.join(OUT, "model")
RICH = [c for c in COHORTS if c != 'ferguson']       # 4 rich-panel cohorts
CAP = 120_000                                         # gold&clean cells kept per cohort

# cache lives in the scratchpad (not the project tree)
CACHE = os.path.join(tempfile.gettempdir(), "claude", "r2_featcache")
os.makedirs(CACHE, exist_ok=True)

L2_L1 = {'T cell':'Immune','B/Plasma':'Immune','Myeloid':'Immune','NK':'Immune',
         'Granulocyte':'Immune','Endothelial':'Stromal','Fibroblast/Muscle':'Stromal',
         'Other':'Stromal','Epithelial/Tumour':'Epithelial/Tumour'}

EXPR_COLS = ['x_'+m for m in BACKBONE] + ['area_um2']
SPA_R30   = ([f'{p}{m}' for m in BACKBONE for p in ('nb_mean_','nb_std_','img_mean_','img_pos_')]
             + ['density_30um'] + [f'me_{k}' for k in range(15)])
# k10 variant: swap the two graph-derived blocks (nb_mean/nb_std) for their k10 versions,
# keep the graph-independent image-level + density + micro_env blocks identical.
SPA_K10   = ([f'{p}k10_{m}' for m in BACKBONE for p in ('nb_mean_','nb_std_')]
             + [f'{p}{m}' for m in BACKBONE for p in ('img_mean_','img_pos_')]
             + ['density_30um'] + [f'me_{k}' for k in range(15)])


def _build_one(cohort):
    path = os.path.join(MODEL, f"{cohort}_model.parquet")
    have = set(pq.ParquetFile(path).schema_arrow.names)
    meta = ['cell_id','is_gold','is_clean','patient_id','L1','L2','label_confidence',
            'area_um2','density_30um','micro_env']
    derived = [p+m for m in BACKBONE for p in ('x_','nb_mean_','nb_std_','img_mean_','img_pos_')]
    read = [c for c in meta + derived if c in have]
    d = pd.read_parquet(path, columns=read)
    d = d[d.is_gold.values & d.is_clean.values]
    if len(d) > CAP:
        d = d.sample(CAP, random_state=0)
    n = len(d)
    cols = {'cell_id': d['cell_id'].to_numpy('int64')}
    for m in BACKBONE:
        for p in ('x_','nb_mean_','nb_std_','img_mean_','img_pos_'):
            c = p+m
            cols[c] = d[c].to_numpy('float32') if c in d.columns else np.full(n, np.nan, 'float32')
    cols['area_um2']     = d['area_um2'].to_numpy('float32')
    cols['density_30um'] = d['density_30um'].to_numpy('float32')
    me = d['micro_env'].to_numpy()
    for k in range(15):
        cols[f'me_{k}'] = (me == k).astype('float32')
    F = pd.DataFrame(cols)
    F['L1'] = d['L1'].values
    F['L2'] = d['L2'].values
    F['patient_id'] = d['patient_id'].values
    F['conf'] = d['label_confidence'].to_numpy('float32')
    F.to_parquet(os.path.join(CACHE, f"{cohort}.parquet"), index=False)
    return len(F), (F.L2.values != '').sum()


def build_cache(force=False):
    made = []
    for c in COHORTS:
        fp = os.path.join(CACHE, f"{c}.parquet")
        if os.path.exists(fp) and not force:
            continue
        n, nl2 = _build_one(c)
        made.append((c, n, nl2))
        print(f"  cached {c:8s}: {n:>8,} gold&clean ({nl2:,} L2-resolved)", flush=True)
    return made


def load(cohort):
    return pd.read_parquet(os.path.join(CACHE, f"{cohort}.parquet"))


def macro(y, p):
    from sklearn.metrics import f1_score
    y = np.asarray(y);
    return float(f1_score(y, p, average='macro', labels=sorted(pd.unique(y)),
                          zero_division=0)) if len(y) else np.nan


def valid_cols(tr, cols):
    """Drop columns all-NaN in TRAIN (a marker absent from every training cohort). They carry no
    signal and crash HistGB binning ('window shape cannot be larger than input array shape').
    Predict must use the same subset."""
    return [c for c in cols if tr[c].notna().any()]

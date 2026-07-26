"""
STEP 8 - Cross-cohort model + spatial ablation (Stage 1).

Answers the project question: does spatial context improve CROSS-COHORT annotation?

Design:
  - Model: HistGradientBoostingClassifier (NaN-native -> handles missing markers directly).
  - Features on the 19-marker BACKBONE (shared by >=4 cohorts). For leave-one-cohort-out,
    only markers shared with training cohorts can transfer, so the backbone is the honest
    cross-cohort ground. (Full union + marker-dropout + hierarchical-loss MLP = Stage 2.)
  - Target: L2 (9 classes) on gold & clean cells with a resolved L2.
  - Evaluation: macro-F1 at L2, and L1 descendant-tolerant macro-F1 (map predicted L2 -> its
    L1 parent) so ferguson (L1-only labels) is scored at its own granularity.
  - LOCO: train on 4 cohorts, test on the held-out 5th.
  - Ablation: EXPR-only vs EXPR+SPATIAL. Control: permute the spatial block within the test
    cohort (breaks cell<->neighbourhood correspondence) - a first-pass proxy for the full
    coordinate-shuffle (Stage 2).

Output: harmonised/model/step8_loco_results.csv + _audit/step8_report.md
"""
import numpy as np, pandas as pd, os, json, time
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import f1_score
import common
from common import COHORTS, OUT, AUDIT

BACKBONE = json.load(open(os.path.join(AUDIT, "panel.json")))["backbone"]
MODEL = os.path.join(OUT, "model")
RNG = np.random.default_rng(0)
CAP = 300_000          # max training cells per fold (stratified), for speed

L2_L1 = {'T cell':'Immune','B/Plasma':'Immune','Myeloid':'Immune','NK':'Immune',
         'Granulocyte':'Immune','Endothelial':'Stromal','Fibroblast/Muscle':'Stromal',
         'Other':'Stromal','Epithelial/Tumour':'Epithelial/Tumour'}

EXPR_COLS = ['x_'+m for m in BACKBONE] + ['area_um2']
SPA_COLS  = ([f'{p}{m}' for m in BACKBONE for p in ('nb_mean_','nb_std_','img_mean_','img_pos_')]
             + ['density_30um'] + [f'me_{k}' for k in range(15)])

def features(cohort):
    # read ONLY the backbone-derived columns that exist (avoid the 342-col union expansion -> OOM)
    path = os.path.join(MODEL, f"{cohort}_model.parquet")
    have = set(pq.ParquetFile(path).schema_arrow.names)
    meta = ['is_gold','is_clean','patient_id','L1','L2','label_confidence','area_um2',
            'density_30um','micro_env']
    derived = [p+m for m in BACKBONE for p in ('x_','nb_mean_','nb_std_','img_mean_','img_pos_')]
    read_cols = [c for c in meta + derived if c in have]
    d = pd.read_parquet(path, columns=read_cols)
    d = d[d.is_gold.values & d.is_clean.values]                 # boolean mask, no big copy
    n = len(d)
    cols = {}
    for m in BACKBONE:
        for p in ('x_','nb_mean_','nb_std_','img_mean_','img_pos_'):
            c = p+m
            cols[c] = d[c].to_numpy('float32') if c in d.columns else np.full(n, np.nan, 'float32')
    cols['area_um2'] = d['area_um2'].to_numpy('float32')
    cols['density_30um'] = d['density_30um'].to_numpy('float32')
    me = d['micro_env'].to_numpy()
    for k in range(15):
        cols[f'me_{k}'] = (me == k).astype('float32')
    F = pd.DataFrame(cols)
    F['cohort'] = cohort
    F['patient_id'] = d['patient_id'].values
    F['L1'] = d['L1'].values
    F['L2'] = d['L2'].values
    F['conf'] = d['label_confidence'].to_numpy('float32')
    return F

def macro(y, p, labels=None):
    return f1_score(y, p, average='macro', labels=labels, zero_division=0)

def fit_eval(Xtr, ytr, wtr, Xte, feat_cols):
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, max_depth=None,
        l2_regularization=1.0, class_weight='balanced', random_state=0, early_stopping=False)
    clf.fit(Xtr[feat_cols].to_numpy('float32'), ytr, sample_weight=wtr)
    return clf, clf.predict(Xte[feat_cols].to_numpy('float32'))

PER_COHORT_TRAIN = 100_000     # cached resolved-L2 subsample per cohort (bounds memory)

def main():
    # cache only a SMALL resolved-L2 subsample per cohort for training; the full test cohort
    # is loaded fresh inside each fold and freed (keeps peak memory < ~1.3 GB on this box)
    print("caching training subsamples per cohort ...")
    TRAIN = {}
    for c in COHORTS:
        F = features(c)
        g = F[F.L2 != '']
        TRAIN[c] = (g.sample(min(len(g), PER_COHORT_TRAIN), random_state=0)
                    if len(g) > PER_COHORT_TRAIN else g).copy()
        print(f"  {c:8s}: {len(F):>8,} gold&clean, cached {len(TRAIN[c]):,} for training")
        del F

    rows = []
    for held in COHORTS:
        tr = pd.concat([TRAIN[c] for c in COHORTS if c != held], ignore_index=True)
        te = features(held)                                        # full held cohort, fresh
        te_l2 = te[te.L2 != ''].reset_index(drop=True)              # L2-scorable test cells
        ytr = tr.L2.values
        # weight: balanced handled by clf; multiply by label confidence
        wtr = tr.conf.values
        res = {'held_out': held, 'n_train': len(tr), 'n_test_L2': len(te_l2), 'n_test_L1': len(te)}

        for name, cols in [('expr', EXPR_COLS), ('expr+spatial', EXPR_COLS+SPA_COLS)]:
            t0 = time.time()
            clf, _ = fit_eval(tr, ytr, wtr, te_l2, cols)
            # L2 macro-F1 (classes present in test)
            if len(te_l2):
                pL2 = clf.predict(te_l2[cols].to_numpy('float32'))
                f1L2 = macro(te_l2.L2.values, pL2, labels=sorted(te_l2.L2.unique()))
            else:
                f1L2 = np.nan
            # L1 descendant-tolerant: predict on ALL test cells, map L2->L1
            pAll = clf.predict(te[cols].to_numpy('float32'))
            pL1 = pd.Series(pAll).map(L2_L1).values
            f1L1 = macro(te.L1.values, pL1, labels=sorted(pd.unique(te.L1)))
            res[f'{name}_F1_L2'] = round(float(f1L2), 4) if not np.isnan(f1L2) else None
            res[f'{name}_F1_L1'] = round(float(f1L1), 4)
            res[f'{name}_sec'] = round(time.time()-t0, 1)

        # permutation control: shuffle spatial block rows in the test set, re-score the spatial model
        clf, _ = fit_eval(tr, ytr, wtr, te_l2, EXPR_COLS+SPA_COLS)
        te_perm = te.copy()
        perm = RNG.permutation(len(te_perm))
        for c in SPA_COLS:
            te_perm[c] = te_perm[c].values[perm]
        pAllp = clf.predict(te_perm[EXPR_COLS+SPA_COLS].to_numpy('float32'))
        pL1p = pd.Series(pAllp).map(L2_L1).values
        res['spatial_permuted_F1_L1'] = round(float(macro(te.L1.values, pL1p,
                                        labels=sorted(pd.unique(te.L1)))), 4)

        res['dF1_L1_spatial'] = round(res['expr+spatial_F1_L1'] - res['expr_F1_L1'], 4)
        rows.append(res)
        print(f"[{held:8s}] L1  expr={res['expr_F1_L1']}  +spatial={res['expr+spatial_F1_L1']}  "
              f"(perm={res['spatial_permuted_F1_L1']})  dF1={res['dF1_L1_spatial']:+.4f}  | "
              f"L2 expr={res['expr_F1_L2']} +spatial={res['expr+spatial_F1_L2']}", flush=True)
        del te, te_l2

    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(MODEL, "step8_loco_results.csv"), index=False)
    rep = ["# STEP 8 - Cross-cohort model + spatial ablation (Stage 1)\n",
           "HistGradientBoosting on the 19-marker backbone. LOCO = train 4 cohorts, test the 5th.",
           "L1 = 3-class descendant-tolerant (ferguson scorable here). L2 = 9-class.",
           f"Backbone: {', '.join(BACKBONE)}\n",
           R.to_markdown(index=False),
           f"\n**Mean L1 macro-F1: expr {R['expr_F1_L1'].mean():.3f} -> +spatial "
           f"{R['expr+spatial_F1_L1'].mean():.3f}  (dF1 {R['dF1_L1_spatial'].mean():+.3f})**",
           f"\nMean permuted-spatial L1: {R['spatial_permuted_F1_L1'].mean():.3f} "
           "(should fall back toward expr if the gain is genuinely spatial).",
           "\nBaseline to beat (MAPS cross-dataset): 0.5-0.6 macro-F1."]
    open(os.path.join(AUDIT, "step8_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("\n" + R.to_string(index=False))
    print("\nMEAN L1: expr %.3f -> +spatial %.3f (dF1 %+.3f) | permuted %.3f" % (
        R['expr_F1_L1'].mean(), R['expr+spatial_F1_L1'].mean(),
        R['dF1_L1_spatial'].mean(), R['spatial_permuted_F1_L1'].mean()))

if __name__ == "__main__":
    main()

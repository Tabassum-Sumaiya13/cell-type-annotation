"""
STEP 10c - Lean spatial block: neighbourhood MEAN only, from the k10 graph.

Asks: how much of the spatial gain survives if we keep ONLY the neighbourhood mean?
Everything else in the spatial block is dropped - no nb_std, no img_mean/img_pos,
no density_30um, no micro_env.

Three feature sets, identical model + identical folds (LOCO):
  expr         : 19 backbone x_ + area_um2                            20 features
  nb_mean r30  : expr + nb_mean_<m>       (radius-30um graph)         39 features
  nb_mean k10  : expr + nb_mean_k10_<m>   (10-nearest-neighbour graph) 39 features

The r30 column is the reference: it isolates the GRAPH choice, since both spatial variants
now carry exactly the same kind of feature. Compare against step10b_graph.csv, which used the
same cache/cap/model but the FULL spatial block (112 features).

Output: harmonised/model/step10c_k10_nbmean.csv + _audit/step10c_report.md
"""
import numpy as np, pandas as pd, os, time
from sklearn.ensemble import HistGradientBoostingClassifier
from r2common import (build_cache, load, macro, valid_cols, COHORTS, MODEL, AUDIT,
                      BACKBONE, EXPR_COLS, L2_L1)
from step10b_graph_models import compute_k10          # reuse the tested k10 builder

# lean spatial blocks: neighbourhood MEAN only
SPA_MEAN_R30 = [f'nb_mean_{m}'     for m in BACKBONE]
SPA_MEAN_K10 = [f'nb_mean_k10_{m}' for m in BACKBONE]

SETS = [('expr',            EXPR_COLS),
        ('nb_mean_r30',     EXPR_COLS + SPA_MEAN_R30),
        ('nb_mean_k10',     EXPR_COLS + SPA_MEAN_K10)]


def new_clf():
    # identical to step10b so the numbers are directly comparable
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1,
        l2_regularization=1.0, class_weight='balanced', random_state=0, early_stopping=False)


def score(te, pred):
    l1 = pd.Series(pred).map(L2_L1).values
    f1L1 = macro(te.L1.values, l1)
    m = te.L2.values != ''
    f1L2 = macro(te.L2.values[m], pred[m]) if m.any() and len(np.unique(te.L2.values[m])) > 1 else np.nan
    return f1L1, f1L2


def main():
    print("building backbone feature cache ...", flush=True)
    build_cache()

    print("\nattaching k10 neighbourhood means ...", flush=True)
    cache = {}
    for c in COHORTS:
        F = load(c).merge(compute_k10(c), on='cell_id', how='left')
        cache[c] = F
        print(f"  {c:8s}: {len(F):,} cells", flush=True)

    t0 = time.time()
    rows = []
    for held in COHORTS:
        te = cache[held]
        tr = pd.concat([cache[c] for c in COHORTS if c != held], ignore_index=True)
        trl2 = tr[tr.L2.values != '']
        res = {'held_out': held, 'n_train': len(trl2), 'n_test': len(te)}
        for name, cols in SETS:
            v = valid_cols(trl2, cols)              # drop columns all-NaN in TRAIN
            clf = new_clf()
            clf.fit(trl2[v].to_numpy('float32'), trl2.L2.values, sample_weight=trl2.conf.values)
            f1L1, f1L2 = score(te, clf.predict(te[v].to_numpy('float32')))
            res[f'{name}_F1_L1'] = round(float(f1L1), 4)
            res[f'{name}_F1_L2'] = round(float(f1L2), 4) if not np.isnan(f1L2) else None
            res[f'{name}_nfeat'] = len(v)
        res['dF1_k10'] = round(res['nb_mean_k10_F1_L1'] - res['expr_F1_L1'], 4)
        res['dF1_r30'] = round(res['nb_mean_r30_F1_L1'] - res['expr_F1_L1'], 4)
        res['k10_minus_r30'] = round(res['nb_mean_k10_F1_L1'] - res['nb_mean_r30_F1_L1'], 4)
        rows.append(res)
        print(f"[{held:8s}] expr={res['expr_F1_L1']} nb_mean_r30={res['nb_mean_r30_F1_L1']} "
              f"nb_mean_k10={res['nb_mean_k10_F1_L1']} "
              f"(k10-r30={res['k10_minus_r30']:+.4f}, k10-expr={res['dF1_k10']:+.4f})", flush=True)
        del tr, trl2

    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(MODEL, "step10c_k10_nbmean.csv"), index=False)

    mean = {n: R[f'{n}_F1_L1'].mean() for n, _ in SETS}
    rep = ["# STEP 10c - Lean spatial block: neighbourhood mean only\n",
           "19-marker backbone, LOCO, same cache/cap/model as Step 10b. Spatial block reduced to "
           "`nb_mean` ONLY - no `nb_std`, no `img_mean`/`img_pos`, no `density_30um`, no `micro_env`.\n",
           "| set | features |\n|---|---|\n"
           f"| expr | {len(EXPR_COLS)} |\n"
           f"| + nb_mean r30 | {len(EXPR_COLS)+len(SPA_MEAN_R30)} |\n"
           f"| + nb_mean k10 | {len(EXPR_COLS)+len(SPA_MEAN_K10)} |\n",
           R.to_markdown(index=False),
           f"\n**Mean L1: expr {mean['expr']:.3f} | nb_mean r30 {mean['nb_mean_r30']:.3f} | "
           f"nb_mean k10 {mean['nb_mean_k10']:.3f}**",
           f"\nMean k10 - r30 = {R['k10_minus_r30'].mean():+.4f}  |  "
           f"mean k10 - expr = {R['dF1_k10'].mean():+.4f}",
           "\nCompare with `step10b_graph.csv` (same folds, FULL 112-feature spatial block) to see "
           "how much the dropped blocks were actually contributing.",
           f"\n_(run {time.time()-t0:.0f}s)_"]
    open(os.path.join(AUDIT, "step10c_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("\n" + R.to_string(index=False), flush=True)
    print(f"\nDONE 10c in {time.time()-t0:.0f}s -> step10c_report.md", flush=True)


if __name__ == "__main__":
    main()

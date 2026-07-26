"""
STEP 10a - Alternative validation for the 2nd evaluation report.

Answers report items:
  2. Did we ever test WITHIN a dataset?  -> within-cohort stratified 5-fold (the "ceiling":
     no domain shift). Gap vs LOCO = the pure cross-cohort transfer penalty.
  5. Best validation scheme?             -> we compare within-cohort CV, LOCO, and
     patient-grouped CV so the report can argue from numbers, not opinion.
  6. Skip ferguson entirely?             -> LOCO on the 4 rich cohorts only, with vs without
     ferguson in the TRAIN set, to isolate what the weak-panel cohort does to transfer.

All on the 19-marker backbone, HistGradientBoosting, capped (see r2common). Output:
  harmonised/model/step10a_within.csv, step10a_skipferg.csv + _audit/step10a_report.md
"""
import numpy as np, pandas as pd, os, time
from sklearn.model_selection import StratifiedKFold, GroupKFold
from sklearn.ensemble import HistGradientBoostingClassifier
from r2common import (build_cache, load, macro, valid_cols, COHORTS, RICH, MODEL, AUDIT,
                      EXPR_COLS, SPA_R30, L2_L1)


def new_clf():
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, l2_regularization=1.0,
        class_weight='balanced', random_state=0, early_stopping=False)


def fit_pred(tr, te, cols):
    v = valid_cols(tr, cols)                                  # drop all-NaN-in-train columns
    clf = new_clf()
    clf.fit(tr[v].to_numpy('float32'), tr.L2.values, sample_weight=tr.conf.values)
    return clf.predict(te[v].to_numpy('float32'))


def score(te, cols, pred):
    """L2 macro-F1 over L2-resolved test rows; L1 macro-F1 (predicted L2 -> L1 parent)."""
    l1_pred = pd.Series(pred).map(L2_L1).values
    f1L1 = macro(te.L1.values, l1_pred)
    m = te.L2.values != ''
    f1L2 = macro(te.L2.values[m], pred[m]) if m.any() and len(np.unique(te.L2.values[m])) > 1 else np.nan
    return f1L1, f1L2


# ---------- EXPERIMENT 1: within-cohort validation ----------
def within_cohort():
    rows = []
    for c in COHORTS:
        F = load(c)
        g = F[F.L2.values != ''].reset_index(drop=True)          # need resolved L2 to stratify
        if g.L2.nunique() < 2:
            print(f"[within {c:8s}] only {g.L2.nunique()} L2 class -> skip (ferguson is L1-only)", flush=True)
            rows.append({'cohort': c, 'scheme': 'within-strat-5fold', 'note': 'L1-only, skipped'})
            continue
        # patient-grouped feasibility
        n_pat = g.patient_id.nunique()
        for scheme in ['strat5', 'patientCV']:
            if scheme == 'patientCV' and n_pat < 5:
                continue
            splitter = (StratifiedKFold(5, shuffle=True, random_state=0).split(g, g.L2)
                        if scheme == 'strat5'
                        else GroupKFold(min(5, n_pat)).split(g, g.L2, g.patient_id))
            eL1=[]; eL2=[]; sL1=[]; sL2=[]
            for tr_i, te_i in splitter:
                tr, te = g.iloc[tr_i], g.iloc[te_i]
                pe = fit_pred(tr, te, EXPR_COLS);          a1,a2 = score(te, EXPR_COLS, pe)
                ps = fit_pred(tr, te, EXPR_COLS+SPA_R30);  b1,b2 = score(te, EXPR_COLS+SPA_R30, ps)
                eL1.append(a1); eL2.append(a2); sL1.append(b1); sL2.append(b2)
            rows.append({'cohort': c, 'scheme': scheme, 'n_patients': n_pat,
                'expr_F1_L1': round(np.nanmean(eL1),4), 'expr_F1_L2': round(np.nanmean(eL2),4),
                'spatial_F1_L1': round(np.nanmean(sL1),4), 'spatial_F1_L2': round(np.nanmean(sL2),4),
                'dF1_L1': round(np.nanmean(sL1)-np.nanmean(eL1),4)})
            print(f"[within {c:8s} {scheme:9s}] L1 expr={rows[-1]['expr_F1_L1']} "
                  f"+spa={rows[-1]['spatial_F1_L1']} | L2 expr={rows[-1]['expr_F1_L2']} "
                  f"+spa={rows[-1]['spatial_F1_L2']}", flush=True)
        del F, g
    return pd.DataFrame(rows)


# ---------- EXPERIMENT 2: skip-ferguson LOCO ----------
def skip_ferguson():
    """For each held RICH cohort: train on the other RICH cohorts (a) WITH ferguson, (b) WITHOUT.
    Test = the held rich cohort. Isolates ferguson's effect on transfer to rich cohorts."""
    cache = {c: load(c) for c in COHORTS}
    rows = []
    for held in RICH:
        te = cache[held]
        for mode, train_src in [('with_ferg',  [c for c in COHORTS if c != held]),
                                ('no_ferg',    [c for c in RICH    if c != held])]:
            tr = pd.concat([cache[c] for c in train_src], ignore_index=True)
            trl2 = tr[tr.L2.values != '']
            res = {'held_out': held, 'train': mode, 'n_train': len(trl2)}
            for nm, cols in [('expr', EXPR_COLS), ('spatial', EXPR_COLS+SPA_R30)]:
                p = fit_pred(trl2, te, cols); f1L1, f1L2 = score(te, cols, p)
                res[f'{nm}_F1_L1'] = round(f1L1,4); res[f'{nm}_F1_L2'] = round(f1L2,4) if not np.isnan(f1L2) else None
            rows.append(res)
            print(f"[skipf {held:8s} {mode:9s}] L1 expr={res['expr_F1_L1']} +spa={res['spatial_F1_L1']}"
                  f" | L2 expr={res['expr_F1_L2']} +spa={res['spatial_F1_L2']}", flush=True)
    return pd.DataFrame(rows)


def main():
    print("building backbone feature cache ...", flush=True)
    build_cache()
    t0 = time.time()
    print("\n=== E1: within-cohort validation (ceiling) ===", flush=True)
    W = within_cohort(); W.to_csv(os.path.join(MODEL, "step10a_within.csv"), index=False)
    print("\n=== E2: skip-ferguson LOCO ===", flush=True)
    S = skip_ferguson(); S.to_csv(os.path.join(MODEL, "step10a_skipferg.csv"), index=False)

    rep = ["# STEP 10a - Alternative validation (2nd report)\n",
           "19-marker backbone, HistGradientBoosting, capped diagnostic run "
           f"(<= {load(COHORTS[0]).shape[0]:,} cells/cohort). Deltas are the signal.\n",
           "## E1 - Within-cohort validation (no domain shift = the ceiling)\n",
           W.to_markdown(index=False),
           "\n## E2 - Skip-ferguson LOCO (train with vs without ferguson)\n",
           S.to_markdown(index=False),
           f"\n_(run {time.time()-t0:.0f}s)_"]
    open(os.path.join(AUDIT, "step10a_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print(f"\nDONE 10a in {time.time()-t0:.0f}s -> step10a_report.md", flush=True)


if __name__ == "__main__":
    main()

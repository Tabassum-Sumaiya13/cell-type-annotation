"""
STEP 10b - Graph choice + model zoo for the 2nd evaluation report.

Answers report items:
  3. Only r30 graph used?   -> build neighbourhood features from the k=10 nearest-neighbour graph
     and re-run LOCO, comparing k10-spatial vs r30-spatial (esp. for sparse ferguson).
  4. Other / neural-net models? -> LOCO model zoo on identical backbone features:
     HistGB (NaN-native), RandomForest, LogisticRegression, MLP (neural net). Shows the cost of
     NOT being NaN-native (imputation) and whether a plain NN competes.

Output: harmonised/model/step10b_graph.csv, step10b_models.csv + _audit/step10b_report.md
"""
import numpy as np, pandas as pd, os, time
import scipy.sparse as sp
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from r2common import (build_cache, load, macro, valid_cols, COHORTS, MODEL, OUT, AUDIT,
                      BACKBONE, EXPR_COLS, SPA_R30, SPA_K10, L2_L1)

MODELZOO_TRAIN = 150_000       # shared train subsample so RF/MLP stay tractable + fair


def score(te, pred):
    l1 = pd.Series(pred).map(L2_L1).values
    f1L1 = macro(te.L1.values, l1)
    m = te.L2.values != ''
    f1L2 = macro(te.L2.values[m], pred[m]) if m.any() and len(np.unique(te.L2.values[m]))>1 else np.nan
    return f1L1, f1L2


# ---------- k10 neighbourhood features (computed fresh from the k10 graph) ----------
def compute_k10(cohort):
    ex = pd.read_parquet(os.path.join(OUT, f"{cohort}_expr.parquet"))
    present = [m for m in BACKBONE if m in ex.columns]
    N = len(ex)
    X = ex[present].to_numpy('float32')
    g = pd.read_parquet(os.path.join(OUT, f"{cohort}_graph_k10.parquet"), columns=['src','dst'])
    s = np.concatenate([g.src.values, g.dst.values])
    d = np.concatenate([g.dst.values, g.src.values])
    A = sp.csr_matrix((np.ones(len(s),'float32'), (s,d)), shape=(N,N))
    deg = np.asarray(A.sum(1)).ravel(); deg[deg==0] = 1.0
    W = sp.diags((1.0/deg).astype('float32')) @ A
    nbm = W @ X
    nbstd = np.sqrt(np.clip((W @ (X*X)) - nbm**2, 0, None)).astype('float32')
    out = {'cell_id': ex.cell_id.to_numpy('int64')}
    for i, m in enumerate(present):
        out[f'nb_mean_k10_{m}'] = nbm[:, i]; out[f'nb_std_k10_{m}'] = nbstd[:, i]
    for m in [m for m in BACKBONE if m not in present]:
        out[f'nb_mean_k10_{m}'] = np.full(N, np.nan, 'float32')
        out[f'nb_std_k10_{m}']  = np.full(N, np.nan, 'float32')
    del X, A, W, nbm, nbstd, ex, g
    return pd.DataFrame(out)


def cache_with_k10(cohort):
    F = load(cohort)
    k = compute_k10(cohort)
    F = F.merge(k, on='cell_id', how='left')
    return F


# ---------- EXPERIMENT 3: k10 vs r30 spatial ----------
def graph_compare():
    print("attaching k10 neighbourhood features ...", flush=True)
    cache = {}
    for c in COHORTS:
        cache[c] = cache_with_k10(c)
        print(f"  {c:8s}: k10 features attached ({len(cache[c]):,} cells)", flush=True)
    rows = []
    for held in COHORTS:
        te = cache[held]
        tr = pd.concat([cache[c] for c in COHORTS if c != held], ignore_index=True)
        trl2 = tr[tr.L2.values != '']
        res = {'held_out': held}
        for nm, cols in [('expr', EXPR_COLS), ('r30', EXPR_COLS+SPA_R30), ('k10', EXPR_COLS+SPA_K10)]:
            v = valid_cols(trl2, cols)                        # drop all-NaN-in-train columns
            clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1,
                l2_regularization=1.0, class_weight='balanced', random_state=0, early_stopping=False)
            clf.fit(trl2[v].to_numpy('float32'), trl2.L2.values, sample_weight=trl2.conf.values)
            f1L1, _ = score(te, clf.predict(te[v].to_numpy('float32')))
            res[f'{nm}_F1_L1'] = round(f1L1, 4)
        res['dF1_r30'] = round(res['r30_F1_L1'] - res['expr_F1_L1'], 4)
        res['dF1_k10'] = round(res['k10_F1_L1'] - res['expr_F1_L1'], 4)
        res['k10_minus_r30'] = round(res['k10_F1_L1'] - res['r30_F1_L1'], 4)
        rows.append(res)
        print(f"[graph {held:8s}] expr={res['expr_F1_L1']} r30={res['r30_F1_L1']} "
              f"k10={res['k10_F1_L1']} (k10-r30={res['k10_minus_r30']:+.4f})", flush=True)
        del tr, trl2
    return pd.DataFrame(rows), cache


# ---------- EXPERIMENT 4: model zoo ----------
def model_zoo(cache):
    cols = EXPR_COLS + SPA_R30
    def models():
        return {
            'HistGB (NaN-native)': ('native', HistGradientBoostingClassifier(max_iter=200,
                learning_rate=0.1, l2_regularization=1.0, class_weight='balanced',
                random_state=0, early_stopping=False)),
            'RandomForest':        ('impute', RandomForestClassifier(n_estimators=200, max_depth=None,
                class_weight='balanced', n_jobs=-1, random_state=0)),
            'LogReg':              ('scale',  LogisticRegression(class_weight='balanced',
                max_iter=300, n_jobs=-1)),
            'MLP (neural net)':    ('scale',  MLPClassifier(hidden_layer_sizes=(128,64),
                early_stopping=True, max_iter=60, random_state=0)),
        }
    rows = []
    for held in COHORTS:
        te = cache[held]
        tr = pd.concat([cache[c] for c in COHORTS if c != held], ignore_index=True)
        trl2 = tr[tr.L2.values != '']
        if len(trl2) > MODELZOO_TRAIN:
            trl2 = trl2.sample(MODELZOO_TRAIN, random_state=0)
        v = valid_cols(trl2, cols)                            # same non-empty feature set for all models
        Xtr = trl2[v].to_numpy('float32'); ytr = trl2.L2.values; w = trl2.conf.values
        Xte = te[v].to_numpy('float32')
        res = {'held_out': held}
        for name, (kind, est) in models().items():
            t0 = time.time()
            try:
                if kind == 'native':
                    est.fit(Xtr, ytr, sample_weight=w); pred = est.predict(Xte)
                elif kind == 'impute':
                    pipe = make_pipeline(SimpleImputer(strategy='median'), est)
                    pipe.fit(Xtr, ytr, **{f'{est.__class__.__name__.lower()}__sample_weight': w}
                             if hasattr(est, 'class_weight') else {})
                    pred = pipe.predict(Xte)
                else:  # scale (impute+standardise); MLP takes no weight, LogReg does
                    pipe = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), est)
                    pipe.fit(Xtr, ytr)
                    pred = pipe.predict(Xte)
                f1L1, _ = score(te, pred)
            except Exception as e:
                f1L1 = np.nan; print(f"   {name} FAILED: {e}", flush=True)
            res[name] = round(float(f1L1), 4) if not np.isnan(f1L1) else None
            print(f"[zoo {held:8s}] {name:22s} L1={res[name]} ({time.time()-t0:.0f}s)", flush=True)
        rows.append(res)
        del tr, trl2, Xtr, Xte
    return pd.DataFrame(rows)


def main():
    print("building backbone feature cache ...", flush=True)
    build_cache()
    t0 = time.time()
    print("\n=== E3: k10 vs r30 graph ===", flush=True)
    G, cache = graph_compare(); G.to_csv(os.path.join(MODEL, "step10b_graph.csv"), index=False)
    print("\n=== E4: model zoo ===", flush=True)
    M = model_zoo(cache); M.to_csv(os.path.join(MODEL, "step10b_models.csv"), index=False)

    gmean = G[['expr_F1_L1','r30_F1_L1','k10_F1_L1']].mean()
    rep = ["# STEP 10b - Graph choice + model zoo (2nd report)\n",
           "19-marker backbone, LOCO, capped diagnostic run. Deltas are the signal.\n",
           "## E3 - Neighbourhood graph: r30 (radius 30um) vs k10 (10 nearest)\n",
           G.to_markdown(index=False),
           f"\n**Mean L1: expr {gmean['expr_F1_L1']:.3f} | r30 {gmean['r30_F1_L1']:.3f} | "
           f"k10 {gmean['k10_F1_L1']:.3f}**\n",
           "## E4 - Model zoo (expr+spatial-r30, identical features)\n",
           M.to_markdown(index=False),
           "\nMeans: " + ", ".join(f"{c} {M[c].mean():.3f}" for c in M.columns if c != 'held_out'),
           f"\n_(run {time.time()-t0:.0f}s)_"]
    open(os.path.join(AUDIT, "step10b_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print(f"\nDONE 10b in {time.time()-t0:.0f}s -> step10b_report.md", flush=True)


if __name__ == "__main__":
    main()

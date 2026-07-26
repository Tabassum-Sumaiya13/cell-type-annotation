"""
STEP 2 - Value normalisation.

Input : native marker matrices (raw / z / arcsinh) via common.load_expression
Output: harmonised/{cohort}_expr.parquet   cell_id + per-marker P(positive) + pct_<marker>
        harmonised/_audit/step2_{cohort}_marker_audit.csv
        harmonised/_audit/step2_report.md

Per (image, marker):
  1. percentile rank -> pct in [0,1]              (bounded, robust to 200-SD outliers)
  2. 2-component Gaussian mixture on winsorised [p0.1,p99.9]; P(positive) = posterior of the
     higher-mean component. BIC vs 1-component decides if the marker actually splits.
     - bimodal  -> continuous P(positive)
     - unimodal -> soft flat value: 0.85 if the image runs high for this marker (image mean
       above the cohort-wide median), else 0.15   (handles all-positive and all-negative images)
     - tiny image (<MIN_CELLS) -> fall back to percentile
Only rank order within (image, marker) is used, so all 5 value scales become comparable.
"""
import numpy as np, pandas as pd, os, sys, time, warnings
from sklearn.mixture import GaussianMixture
from common import COHORTS, OUT, AUDIT, load_expression, load_geometry
warnings.filterwarnings("ignore")

FIT_SUB   = 4000      # subsample size for the GMM fit (score all cells regardless)
MIN_CELLS = 50        # below this, use percentile fallback
RNG = np.random.default_rng(0)

def gmm_positive(x):
    """x: 1-D array for one (image, marker). Returns (p_pos array, mode) aligned to x."""
    n = len(x)
    # percentile rank (average ties) -> [0,1]
    order = x.argsort(kind='mergesort')
    ranks = np.empty(n); ranks[order] = np.arange(n)
    pct = (ranks + 0.5) / n

    if n < MIN_CELLS or np.nanstd(x) == 0:
        return pct.astype('float32'), pct.astype('float32'), 'fallback'

    lo, hi = np.percentile(x, [0.1, 99.9])
    xw = np.clip(x, lo, hi)
    fit = xw if n <= FIT_SUB else xw[RNG.choice(n, FIT_SUB, replace=False)]
    fit = fit.reshape(-1, 1)
    try:
        g1 = GaussianMixture(1, n_init=1, max_iter=100, random_state=0).fit(fit)
        g2 = GaussianMixture(2, n_init=1, max_iter=100, random_state=0).fit(fit)
    except Exception:
        return pct.astype('float32'), pct.astype('float32'), 'fallback'

    if g2.bic(fit) < g1.bic(fit):                      # bimodal -> real pos/neg split
        hi_comp = int(np.argmax(g2.means_.ravel()))
        p = g2.predict_proba(xw.reshape(-1, 1))[:, hi_comp]
        return p.astype('float32'), pct.astype('float32'), 'bimodal'
    # unimodal -> soft flat by whether this image runs high for this marker (set by caller)
    return None, pct.astype('float32'), 'unimodal'

def process(cohort):
    X = load_expression(cohort)
    geo = load_geometry(cohort)[['cell_id', 'image_id']]
    assert (X.cell_id.values == geo.cell_id.values).all()
    markers = [c for c in X.columns if c != 'cell_id']
    img = geo.image_id.values
    global_med = {m: np.median(X[m].values) for m in markers}     # cohort-wide per marker

    P = {m: np.empty(len(X), 'float32') for m in markers}
    PC = {m: np.empty(len(X), 'float32') for m in markers}
    audit = []
    # index rows per image once
    idx_by_img = pd.Series(np.arange(len(X))).groupby(img).apply(lambda s: s.values)
    for m in markers:
        xm = X[m].values.astype('float64')
        modes = {'bimodal':0, 'unimodal':0, 'fallback':0}
        for im, idx in idx_by_img.items():
            xi = xm[idx]
            p, pc, mode = gmm_positive(xi)
            modes[mode] += 1
            if p is None:                                          # unimodal soft-flat
                p = np.full(len(idx), 0.85 if np.mean(xi) > global_med[m] else 0.15, 'float32')
            P[m][idx] = p; PC[m][idx] = pc
        audit.append(dict(marker=m, n_images=len(idx_by_img), **modes,
                          pct_bimodal=round(100*modes['bimodal']/len(idx_by_img), 1),
                          mean_Ppos=round(float(P[m].mean()), 3)))

    out = pd.DataFrame({'cell_id': X.cell_id.values})
    for m in markers:
        out[m] = P[m]
    for m in markers:
        out['pct_' + m] = PC[m]
    out.to_parquet(os.path.join(OUT, f"{cohort}_expr.parquet"), index=False)
    ad = pd.DataFrame(audit)
    ad.to_csv(os.path.join(AUDIT, f"step2_{cohort}_marker_audit.csv"), index=False)
    return len(X), markers, ad

def main(cohorts):
    rep = ["# STEP 2 - Value normalisation report\n",
           "Per (image, marker): percentile + 2-component GMM P(positive). Output = "
           "`{cohort}_expr.parquet` (P(positive) columns + `pct_` percentile columns).\n"]
    for c in cohorts:
        t = time.time(); n, mk, ad = process(c)
        flat = ad[(ad.pct_bimodal < 50)]
        print(f"[{c:8s}] {n:>9,} cells x {len(mk)} markers  "
              f"median %bimodal={ad.pct_bimodal.median():.0f}%  ({time.time()-t:.0f}s)")
        rep.append(f"## {c}\n- cells {n:,} x {len(mk)} markers\n"
                   f"- median share of images where a marker is bimodal (splits pos/neg): "
                   f"**{ad.pct_bimodal.median():.0f}%**\n"
                   f"- markers rarely bimodal (<50% of images): "
                   f"{', '.join(flat.marker) if len(flat) else 'none'}\n")
    open(os.path.join(AUDIT, "step2_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("wrote {cohort}_expr.parquet + _audit/step2_*")

if __name__ == "__main__":
    cohorts = sys.argv[1:] or COHORTS
    main(cohorts)

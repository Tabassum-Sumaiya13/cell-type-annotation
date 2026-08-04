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

Reproducible by design: the GMM subsample seed is derived from (cohort, marker, image), so
running one cohort on its own gives exactly the same numbers as running all five together.
"""
import numpy as np, pandas as pd, os, sys, time, warnings, zlib
from sklearn.mixture import GaussianMixture
from common import COHORTS, OUT, AUDIT, load_expression, load_geometry
warnings.filterwarnings("ignore")

FIT_SUB   = 4000      # subsample size for the GMM fit (score all cells regardless)
MIN_CELLS = 50        # below this, use percentile fallback

# familiar antibody names (CD8 for CD8A) so the audit CSV stays readable after the
# 2026-08-04 switch to gene-symbol marker names
import json
try:
    DISPLAY = json.load(open(os.path.join(AUDIT, "panel.json"))).get("display", {})
except FileNotFoundError:
    DISPLAY = {}


def seed_for(cohort, marker, image_id):
    """Stable seed per (cohort, marker, image).

    The GMM is fitted on a random subsample when an image has more than FIT_SUB cells, so the
    subsample decides the result. Deriving the seed from the names (not from a running counter)
    means `python step2_normalise.py UPMC` gives byte-identical output to a full 5-cohort run.
    crc32, not hash(), because Python's hash() of a string changes between processes.
    """
    return zlib.crc32(f"{cohort}|{marker}|{image_id}".encode()) & 0xFFFFFFFF


def gmm_positive(x, seed):
    """x: 1-D array for one (image, marker). Returns (p_pos, pct, mode) aligned to x."""
    n = len(x)
    # percentile rank (average ties) -> [0,1]
    order = x.argsort(kind='mergesort')
    ranks = np.empty(n); ranks[order] = np.arange(n)
    pct = (ranks + 0.5) / n

    if n < MIN_CELLS or np.nanstd(x) == 0:
        return pct.astype('float32'), pct.astype('float32'), 'fallback'

    lo, hi = np.percentile(x, [0.1, 99.9])
    xw = np.clip(x, lo, hi)
    fit = xw if n <= FIT_SUB else xw[np.random.default_rng(seed).choice(n, FIT_SUB, replace=False)]
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
    chatty = len(X) > 1_000_000      # the big cohorts take ~30 min - show progress
    t0 = time.time()
    for j, m in enumerate(markers, 1):
        xm = X[m].values.astype('float64')
        modes = {'bimodal':0, 'unimodal':0, 'fallback':0}
        for im, idx in idx_by_img.items():
            xi = xm[idx]
            p, pc, mode = gmm_positive(xi, seed_for(cohort, m, im))
            modes[mode] += 1
            if p is None:                                          # unimodal soft-flat
                p = np.full(len(idx), 0.85 if np.mean(xi) > global_med[m] else 0.15, 'float32')
            P[m][idx] = p; PC[m][idx] = pc
        audit.append(dict(marker=m, display=DISPLAY.get(m, m), n_images=len(idx_by_img), **modes,
                          pct_bimodal=round(100*modes['bimodal']/len(idx_by_img), 1),
                          mean_Ppos=round(float(P[m].mean()), 3)))
        if chatty:
            print(f"    [{cohort}] {j:>2}/{len(markers)} {m:<12} "
                  f"{modes['bimodal']}/{len(idx_by_img)} images bimodal  "
                  f"({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame({'cell_id': X.cell_id.values})
    for m in markers:
        out[m] = P[m]
    for m in markers:
        out['pct_' + m] = PC[m]
    out.to_parquet(os.path.join(OUT, f"{cohort}_expr.parquet"), index=False)
    ad = pd.DataFrame(audit)
    ad.to_csv(os.path.join(AUDIT, f"step2_{cohort}_marker_audit.csv"), index=False)
    return len(X), markers, ad

def write_report():
    """Rebuild step2_report.md from the audit CSVs already on disk.

    Reads the finished audit files instead of the cohorts just processed, so running
    `step2_normalise.py UPMC` still leaves a report covering all 5 cohorts instead of
    silently shrinking it to one.
    """
    import pyarrow.parquet as pq
    rep = ["# STEP 2 - Value normalisation report\n",
           "Per (image, marker): percentile + 2-component GMM P(positive). Output = "
           "`{cohort}_expr.parquet` (P(positive) columns + `pct_` percentile columns).\n",
           "Built from the audit CSVs on disk, so it stays complete after a partial re-run.\n"]
    for c in COHORTS:
        f = os.path.join(AUDIT, f"step2_{c}_marker_audit.csv")
        pqf = os.path.join(OUT, f"{c}_expr.parquet")
        if not (os.path.exists(f) and os.path.exists(pqf)):
            rep.append(f"## {c}\n- _not built yet_\n")
            continue
        ad = pd.read_csv(f)
        n = pq.ParquetFile(pqf).metadata.num_rows          # metadata only, no data read
        flat = ad[ad.pct_bimodal < 50]
        names = ', '.join(f'{r.marker} ({r.display})' if r.display != r.marker else r.marker
                          for r in flat.itertuples()) if len(flat) else 'none'
        rep.append(f"## {c}\n- cells {n:,} x {len(ad)} markers\n"
                   f"- median share of images where a marker is bimodal (splits pos/neg): "
                   f"**{ad.pct_bimodal.median():.0f}%**\n"
                   f"- markers rarely bimodal (<50% of images): {names}\n")
    return rep


def main(cohorts):
    for c in cohorts:
        t = time.time(); n, mk, ad = process(c)
        print(f"[{c:8s}] {n:>9,} cells x {len(mk)} markers  "
              f"median %bimodal={ad.pct_bimodal.median():.0f}%  ({time.time()-t:.0f}s)")
    rep = write_report()
    open(os.path.join(AUDIT, "step2_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("wrote {cohort}_expr.parquet + _audit/step2_*")

if __name__ == "__main__":
    cohorts = sys.argv[1:] or COHORTS
    main(cohorts)

"""
STEP 6 - Spatial features (all label-free).

Input : {cohort}_expr.parquet (P(positive)), {cohort}_graph_r30.parquet, {cohort}_cells.parquet
Output: {cohort}_spatial_r30.parquet   per-cell spatial feature block
        _audit/step6_report.md

Two passes:
  6a (per cohort): neighbourhood mean & std of P(positive) over the radius graph; local
     density; image-level mean profile and %-positive.  Uses a sparse adjacency matmul.
  6b (pooled):     one shared MiniBatchKMeans on backbone neighbourhood-means from ALL
     cohorts -> micro_env id that means the same thing in every cohort (A19).

Nothing here uses cell-type labels -> safe as direct model input.
"""
import numpy as np, pandas as pd, os, json, sys
import scipy.sparse as sp
from sklearn.cluster import MiniBatchKMeans
from common import COHORTS, OUT, AUDIT

BACKBONE = json.load(open(os.path.join(AUDIT, "panel.json")))["backbone"]
K_MICROENV = 15

def markers_of(cohort):
    cols = pd.read_parquet(os.path.join(OUT, f"{cohort}_expr.parquet")).columns
    return [c for c in cols if c != 'cell_id' and not c.startswith('pct_')]

def pass6a(cohort):
    ex = pd.read_parquet(os.path.join(OUT, f"{cohort}_expr.parquet"))
    mk = [c for c in ex.columns if c != 'cell_id' and not c.startswith('pct_')]
    cells = pd.read_parquet(os.path.join(OUT, f"{cohort}_cells.parquet"),
                            columns=['cell_id', 'image_id', 'n_nbr_30um'])
    g = pd.read_parquet(os.path.join(OUT, f"{cohort}_graph_r30.parquet"))
    N = len(ex)
    X = ex[mk].to_numpy('float32')

    # symmetric adjacency (both directions), row-normalised by degree -> neighbourhood MEAN
    s = np.concatenate([g.src.values, g.dst.values])
    d = np.concatenate([g.dst.values, g.src.values])
    A = sp.csr_matrix((np.ones(len(s), 'float32'), (s, d)), shape=(N, N))
    deg = np.asarray(A.sum(1)).ravel(); deg[deg == 0] = 1.0
    Dinv = sp.diags((1.0 / deg).astype('float32'))
    W = Dinv @ A                                         # row-stochastic

    nbhd_mean = W @ X
    nbhd_sq   = W @ (X * X)
    nbhd_std  = np.sqrt(np.clip(nbhd_sq - nbhd_mean**2, 0, None)).astype('float32')

    # image-level mean profile + %-positive (broadcast to cells)
    tmp = pd.DataFrame(X, columns=mk); tmp['image_id'] = cells.image_id.values
    img_mean = tmp.groupby('image_id')[mk].transform('mean').to_numpy('float32')
    pos = (X > 0.5).astype('float32')
    tmp2 = pd.DataFrame(pos, columns=mk); tmp2['image_id'] = cells.image_id.values
    img_pos = tmp2.groupby('image_id')[mk].transform('mean').to_numpy('float32')

    cols = {'cell_id': ex.cell_id.values}
    cols.update({'nb_mean_' + m: nbhd_mean[:, i] for i, m in enumerate(mk)})
    cols.update({'nb_std_' + m: nbhd_std[:, i] for i, m in enumerate(mk) if m in BACKBONE})
    cols['density_30um'] = cells.n_nbr_30um.values.astype('float32')
    cols.update({'img_mean_' + m: img_mean[:, i] for i, m in enumerate(mk)})
    cols.update({'img_pos_' + m: img_pos[:, i] for i, m in enumerate(mk)})
    out = pd.DataFrame(cols)
    out.to_parquet(os.path.join(OUT, f"{cohort}_spatial_r30.parquet"), index=False)

    # return backbone neighbourhood-means for the pooled k-means
    bb = [m for m in BACKBONE if m in mk]
    nb_bb = pd.DataFrame(nbhd_mean[:, [mk.index(m) for m in bb]], columns=bb)
    nb_bb['cohort'] = cohort; nb_bb['cell_id'] = ex.cell_id.values
    return nb_bb, len(mk)

def pass6b(nb_frames):
    """One shared k-means on backbone neighbourhood-means; assign micro_env to every cell."""
    allbb = pd.concat(nb_frames, ignore_index=True)
    bb = [c for c in allbb.columns if c not in ('cohort', 'cell_id')]
    Xall = allbb[bb].fillna(allbb[bb].median()).to_numpy('float32')
    km = MiniBatchKMeans(n_clusters=K_MICROENV, random_state=0, n_init=5, batch_size=10000)
    lab = km.fit_predict(Xall)
    allbb['micro_env'] = lab.astype('int16')
    # write micro_env to a SEPARATE small file (avoid rewriting the big mmapped spatial file);
    # Step 7 merges it in.
    for c in allbb.cohort.unique():
        sub = allbb[allbb.cohort == c][['cell_id', 'micro_env']].reset_index(drop=True)
        sub.to_parquet(os.path.join(OUT, f"{c}_microenv.parquet"), index=False)
    return allbb.micro_env.value_counts().sort_index()

def main(cohorts):
    rep = ["# STEP 6 - Spatial features report\n",
           "Label-free. `nb_mean_*` neighbourhood mean P(positive), `nb_std_*` (backbone), "
           "`density_30um`, `img_mean_*`, `img_pos_*`, `micro_env` (shared k-means).\n"]
    nb_frames = []
    for c in cohorts:
        nb, nm = pass6a(c)
        nb_frames.append(nb)
        print(f"[6a {c:8s}] {len(nb):>9,} cells, {nm} markers -> spatial block written")
        rep.append(f"- **{c}**: {len(nb):,} cells, {nm} markers")
    if set(cohorts) == set(COHORTS):
        counts = pass6b(nb_frames)
        print(f"[6b] shared k-means k={K_MICROENV} assigned; sizes {counts.values.tolist()}")
        rep.append(f"\n## micro_env (shared k-means, k={K_MICROENV})\n"
                   f"cluster sizes: {counts.to_dict()}\n")
    else:
        rep.append("\n(6b micro_env skipped - needs all 5 cohorts)\n")
    open(os.path.join(AUDIT, "step6_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("wrote {cohort}_spatial_r30.parquet + step6_report.md")

if __name__ == "__main__":
    main(sys.argv[1:] or COHORTS)

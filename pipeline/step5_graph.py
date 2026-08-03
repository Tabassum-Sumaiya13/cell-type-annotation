"""
STEP 5 - Graph build.

Input : harmonised/{cohort}_cells.parquet   (cell_id, image_id, x_um, y_um)
Output: harmonised/{cohort}_graph_r30.parquet   radius graph, r = 30 um   (PRIMARY)
        harmonised/{cohort}_graph_k10.parquet    kNN graph, k = 10        (secondary)
        harmonised/_audit/step5_graph_report.md

Edges are UNDIRECTED and unique (src < dst), referencing global cell_id. Built PER IMAGE
(coordinates are image-local, so cross-image edges would be false). dist_um stored so a
later step can prune / weight without rebuilding.

Why radius primary, kNN secondary, not Delaunay: see PIPELINE / chat evidence. Delaunay is
available as an opt-in variant (--delaunay) pruned at 30 um.
"""
import numpy as np, pandas as pd, os, time
from scipy.spatial import cKDTree
from common import COHORTS, OUT, AUDIT

R_UM = 30.0
K    = 10

def radius_edges(xy, gid):
    tree = cKDTree(xy)
    pr = tree.query_pairs(r=R_UM, output_type='ndarray')      # local i<j
    if len(pr) == 0:
        return np.empty((0,2),'int64'), np.empty(0,'float32')
    d = np.linalg.norm(xy[pr[:,0]] - xy[pr[:,1]], axis=1).astype('float32')
    return gid[pr], d

def knn_edges(xy, gid):
    n = len(xy)
    tree = cKDTree(xy)
    d, nb = tree.query(xy, k=min(K+1, n))
    if nb.ndim == 1:
        nb = nb[:,None]; d = d[:,None]
    src = np.repeat(np.arange(n), nb.shape[1]-1)
    dst = nb[:,1:].ravel()
    dd  = d[:,1:].ravel().astype('float32')
    keep = src != dst                    # drop self-loops from duplicate-coordinate ties
    src, dst, dd = src[keep], dst[keep], dd[keep]
    lo = np.minimum(src, dst); hi = np.maximum(src, dst)        # undirected (gid monotone in image)
    key = lo.astype('int64') * n + hi
    _, uidx = np.unique(key, return_index=True)
    pr = np.stack([lo[uidx], hi[uidx]], 1)
    return gid[pr], dd[uidx]

def build(cohort, kind):
    cells = pd.read_parquet(os.path.join(OUT, f"{cohort}_cells.parquet"),
                            columns=['cell_id','image_id','x_um','y_um'])
    S=[]; Dd=[]; deg_sum=0
    fn = radius_edges if kind=='r30' else knn_edges
    for img, sub in cells.groupby('image_id', sort=False):
        if len(sub) < 3:
            continue
        xy  = sub[['x_um','y_um']].to_numpy('float64')
        gid = sub['cell_id'].to_numpy('int64')
        e, d = fn(xy, gid)
        if len(e):
            S.append(e); Dd.append(d)
    E = np.concatenate(S) if S else np.empty((0,2),'int64')
    Dd = np.concatenate(Dd) if Dd else np.empty(0,'float32')
    out = pd.DataFrame({'src':E[:,0].astype('int32'),
                        'dst':E[:,1].astype('int32'),
                        'dist_um':Dd})
    path = os.path.join(OUT, f"{cohort}_graph_{kind}.parquet")
    out.to_parquet(path, index=False)
    n = len(cells)
    return dict(cohort=cohort, kind=kind, n_cells=n, n_edges=len(out),
                mean_degree=round(2*len(out)/n, 2),
                med_dist_um=round(float(np.median(Dd)),2) if len(Dd) else None,
                max_dist_um=round(float(Dd.max()),2) if len(Dd) else None)

def main():
    rows=[]
    for c in COHORTS:
        for kind in ['r30','k10']:
            t=time.time(); r=build(c,kind); r['sec']=round(time.time()-t,1)
            rows.append(r)
            print(f"[{c:8s} {kind}]  edges {r['n_edges']:>10,}  mean_deg {r['mean_degree']:>5}  "
                  f"med {r['med_dist_um']}um  ({r['sec']}s)")
    t=pd.DataFrame(rows)
    rep=["# STEP 5 - Graph build report\n",
         f"Radius r={R_UM}um (primary) and kNN k={K} (secondary). Undirected, src<dst, global cell_id.",
         "Load with both directions for a GNN (add dst->src).\n",
         t.to_markdown(index=False)]
    open(os.path.join(AUDIT,"step5_graph_report.md"),"w",encoding="utf-8").write("\n".join(rep))
    print("\n"+t.to_string(index=False))
    print("\nwrote harmonised/{cohort}_graph_{r30,k10}.parquet + _audit/step5_graph_report.md")

if __name__ == "__main__":
    main()

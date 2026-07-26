"""
STEP 3 - Geometry + spatial QC.

Input : raw coordinate columns (via common.load_geometry)
Output: harmonised/{cohort}_cells.parquet
        harmonised/_audit/step3_geometry_report.md

Does:
  - pixels -> micrometres (per-cohort pixel size)
  - area in um^2 where a 2D cell area exists
  - spatial QC flags that need only geometry (bits 1,4,5). Expression-based bits (2 = no
    DNA, 3 = bright speck) are added later in step 2, which has the marker matrix.

qc_flag bitmask:
  bit 0 (1)  area outside [p1,p99] of cohort            segmentation size outlier
  bit 3 (8)  within 30 um of image bounding-box edge    truncated neighbourhood (border)
  bit 4 (16) zero neighbours within 30 um               isolated / debris
(bits 1=2 and 2=4 reserved for step 2: no-DNA, bright-speck)
"""
import numpy as np, pandas as pd, os
from scipy.spatial import cKDTree
from common import COHORTS, PIXEL_UM, OUT, AUDIT, load_geometry

R_UM = 30.0
BIT_AREA, BIT_BORDER, BIT_ISO = 1, 8, 16

def process(cohort):
    g = load_geometry(cohort)
    px = PIXEL_UM[cohort]
    g['x_um'] = g.x_px * px
    g['y_um'] = g.y_px * px
    g['area_um2'] = g.area_px2 * (px * px)

    qc = np.zeros(len(g), dtype='int32')

    # bit AREA: area outlier within cohort (only where area exists)
    a = g.area_um2.to_numpy('float64')
    fin = np.isfinite(a)
    if fin.any():
        lo, hi = np.nanpercentile(a[fin], [1, 99])
        bad = fin & ((a < lo) | (a > hi))
        qc[bad] |= BIT_AREA

    # per-image geometry flags: border + isolated
    nbr = np.zeros(len(g), dtype='int32')
    border = np.zeros(len(g), dtype=bool)
    for img, idx in g.groupby('image_id').indices.items():
        idx = np.asarray(idx)
        xy = g.loc[g.index[idx], ['x_um', 'y_um']].to_numpy('float64')
        if len(xy) < 3:
            continue
        tree = cKDTree(xy)
        cnt = tree.query_ball_point(xy, r=R_UM, return_length=True) - 1   # exclude self
        nbr[idx] = cnt
        lo = xy.min(0); hi = xy.max(0)
        near = ((xy - lo) < R_UM).any(1) | ((hi - xy) < R_UM).any(1)
        border[idx] = near
    qc[nbr == 0] |= BIT_ISO
    qc[border]  |= BIT_BORDER

    g['n_nbr_30um'] = nbr
    g['qc_flag'] = qc
    g['is_clean'] = (qc == 0)

    cols = ['cell_id','cohort','image_id','patient_id','x_um','y_um','area_um2',
            'n_nbr_30um','qc_flag','is_clean']
    g = g[cols]
    path = os.path.join(OUT, f"{cohort}_cells.parquet")
    g.to_parquet(path, index=False)
    return g

def main():
    rep = ["# STEP 3 - Geometry + QC report\n",
           "Coordinates in micrometres. qc_flag bits: 1=area outlier, 8=border(<30um), 16=isolated.",
           "(bits 2=no-DNA, 4=bright-speck added in step 2.)\n"]
    rows = []
    for c in COHORTS:
        g = process(c)
        rows.append(dict(cohort=c, cells=len(g), images=g.image_id.nunique(),
                         patients=g.patient_id.nunique(),
                         has_area=f"{g.area_um2.notna().mean()*100:.0f}%",
                         med_area_um2=round(np.nanmedian(g.area_um2),1) if g.area_um2.notna().any() else None,
                         pct_border=round((g.qc_flag & BIT_BORDER).astype(bool).mean()*100,1),
                         pct_isolated=round((g.qc_flag & BIT_ISO).astype(bool).mean()*100,2),
                         pct_area_out=round((g.qc_flag & 1).astype(bool).mean()*100,1),
                         pct_clean=round(g.is_clean.mean()*100,1)))
        print(f"[{c}] {len(g):>9,} cells  {g.image_id.nunique():>4} images  "
              f"clean {g.is_clean.mean()*100:4.1f}%  border {(g.qc_flag&BIT_BORDER).astype(bool).mean()*100:4.1f}%")
    t = pd.DataFrame(rows)
    rep.append(t.to_markdown(index=False))
    open(os.path.join(AUDIT, "step3_geometry_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("\n" + t.to_string(index=False))
    print("\nwrote harmonised/{cohort}_cells.parquet + _audit/step3_geometry_report.md")

if __name__ == "__main__":
    main()

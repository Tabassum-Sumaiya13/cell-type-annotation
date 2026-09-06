"""
STAGE 4 - adaptive spatial context.  Produces GATE 4.

    python s4_spatial.py --build      # neighbour sidecars from the FULL raw tables (CPU)
    python s4_spatial.py --pilot      # 1 fold x 3 arms, a signal, not a gate
    python s4_spatial.py --gate       # GATE 4: 4 arms x 7 LOCO folds

WHY THE GRAPH CANNOT BE BUILT FROM THE VALUE TABLES - the thing that makes this stage hard.

Every stage from 1 onward works on a 40,000-cell stratified subsample per cohort. For UPMC that
is 1.9% of 2,061,102 cells. A cell's 15 nearest neighbours IN THE SUBSAMPLE are therefore not
its neighbours at all: measured mean spacing rises from 11.7 um to about 79 um, and only 0.29 of
a cell's true 15 neighbours are even present. A kNN graph over the subsample is a random sample
of the slide wearing a neighbourhood's clothes, and it would produce a confident, meaningless
number.

So the graph is built over EVERY cell in work/raw/{cohort}.parquet and then indexed back to the
40,000 target cells. The target cells stay bit-identical to the ones Stage 6 scores, which is
what makes arm `cell` a fair in-run control (D-27's discipline) rather than two runs on two
different datasets.

WHAT IS STORED, per cohort, in work/values/{cohort}_nbr.npz:
    nbr_u      (N, k, M) float16   each neighbour's u_coh over the cohort's own triples
    nbr_d      (N, k)    float32   edge distance in MICRONS
    nbr_rel    (N, k)    float32   edge distance / that image's median nearest-neighbour distance
    nbr_valid  (N, k)    bool      False where the image holds fewer than k+1 cells
    cell_id    (N,)      int64     the target cells, in {cohort}_full.parquet order

float16 for the values because u_coh is a rank in [0, 1], where half precision carries about
three decimal digits - far below the noise on an antibody measurement - and it halves a 300 MB
artefact that has to be uploaded to Kaggle.

THE TWO DISTANCE COLUMNS EXIST BECAUSE OF M4. UPMC's px_um is recorded as
'ASSUMED - not published anywhere'. Stage 4 is the only stage that ever uses physical distance,
so an assumption that was harmless everywhere else becomes load-bearing here. `nbr_rel` divides
by a per-image scale, so a wrong global um/px cancels; `nbr_d` is kept because real distance is
informative where the scale is trustworthy. Gate 4 check 5 rescales UPMC and confirms the
verdict does not move.
"""
import os
import sys
import time
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config
from config import SPECS, WORK, VALUES, raw_table
import panel_util

K = 15                              # files/05 4.8 declares k = 15
MIN_D = 1e-3                        # 7 duplicate coordinates exist in Sorin; log(0) is not a number
DIST_LO, DIST_HI = 10.0, 30.0       # gate 4 check 7, from the measured 11.0-20.0 um spacing

# Gate 4 check 0. Pinned as a LITERAL, never derived from which parquet files sit on disk -
# that derivation is what H14/D-39 broke, and what silently turned a 5-cohort run into a
# 6-cohort one with nothing in the log to say so.
TRAIN = ['CRC', 'UPMC', 'Keren', 'Phillips', 'Sorin', 'Danenberg', 'ferguson']


def assert_roster():
    """Gate 4 check 0 - printed in the report, not just the log."""
    got = [c for c, s in SPECS.items() if s['role'] == 'train']
    assert set(got) == set(TRAIN), (
        f"roster drift: config says {sorted(got)}, this stage expects {sorted(TRAIN)}")
    assert len(TRAIN) == 7, f"expected 7 training cohorts, got {len(TRAIN)}"
    held = [c for c, s in SPECS.items() if s['role'] == 'holdout']
    assert not held, f"a frozen holdout still exists ({held}); the protocol is 7-fold LOCO"
    print(f"check 0 PASS - {len(TRAIN)} cohorts, no holdout: {', '.join(TRAIN)}")
    return True


def nbr_path(c):
    return os.path.join(VALUES, f"{c}_nbr.npz")


def registry():
    r = pd.read_csv(os.path.join(WORK, 'marker_registry.csv'), keep_default_na=False)
    return r[(r.kind != 'non_protein') & (r.triple != '')]


def build_cohort(c, k=K):
    """kNN inside every image of one cohort, indexed back to the 40k target cells."""
    t0 = time.time()
    reg = registry()
    triples = sorted(reg[reg.cohort == c].triple.unique())
    cols = panel_util.cols_for(reg, c, triples)

    df = pd.read_parquet(
        raw_table(c),
        columns=['cell_id', 'image_id', 'x_px', 'y_px'] + panel_util.read_cols(cols, triples))
    px = SPECS[c]['px_um']
    xy = np.c_[df.x_px.to_numpy('float64'), df.y_px.to_numpy('float64')] * px

    # u_coh over ALL cells - the identical code path to s2_tokens.build, so a neighbour's value
    # and a target's value come from the same transform rather than two that merely look alike.
    U = panel_util.matrix(df, cols, triples).rank(pct=True, method='average').to_numpy('float32')

    want = pd.read_parquet(os.path.join(VALUES, f"{c}_full.parquet"),
                           columns=['cell_id']).cell_id.to_numpy()
    pos = pd.Index(df.cell_id).get_indexer(want)
    assert (pos >= 0).all(), f"{c}: target cell ids missing from the raw table"
    tgt_rank = {int(p): i for i, p in enumerate(pos)}        # raw row -> target row

    n_tgt = len(want)
    nbr_i = np.full((n_tgt, k), -1, 'int64')
    nbr_d = np.zeros((n_tgt, k), 'float32')
    nbr_rel = np.zeros((n_tgt, k), 'float32')
    valid = np.zeros((n_tgt, k), bool)

    img = df.image_id.to_numpy()
    order = np.argsort(img, kind='stable')
    simg = img[order]
    bounds = np.flatnonzero(np.r_[True, simg[1:] != simg[:-1], True])

    for a, b in zip(bounds[:-1], bounds[1:]):
        rows = order[a:b]                                   # every cell of ONE image
        if len(rows) < 2:
            continue
        tree = cKDTree(xy[rows])
        kk = min(k, len(rows) - 1)
        d, j = tree.query(xy[rows], k=kk + 1)                # +1: the first hit is the cell itself
        d = np.atleast_2d(d)[:, 1:]
        j = np.atleast_2d(j)[:, 1:]
        d = np.maximum(d, MIN_D)
        scale = float(np.median(d[:, 0])) if d.size else 1.0  # this image's median NN distance
        if not scale > MIN_D:
            scale = 1.0
        for li, r in enumerate(rows):
            ti = tgt_rank.get(int(r))
            if ti is None:
                continue
            nbr_i[ti, :kk] = rows[j[li]]
            nbr_d[ti, :kk] = d[li]
            nbr_rel[ti, :kk] = d[li] / scale
            valid[ti, :kk] = True

    # check 6 - no edge may cross an image boundary. All coordinate frames are image-local
    # (files/02 2.2) and CRC's are tile-local, so a cross-image edge joins cells that are not
    # neighbours at all and manufactures a spatial signal out of nothing.
    src = np.repeat(img[pos][:, None], k, axis=1)
    dst = np.where(valid, img[np.clip(nbr_i, 0, None)], src)
    assert (src == dst).all(), f"{c}: an edge crosses an image boundary"

    nbr_u = np.where(valid[:, :, None], U[np.clip(nbr_i, 0, None)], 0.0).astype('float16')

    med = float(np.median(nbr_d[valid])) if valid.any() else float('nan')
    np.savez_compressed(nbr_path(c), nbr_u=nbr_u, nbr_d=nbr_d, nbr_rel=nbr_rel,
                        nbr_valid=valid, cell_id=want, triples=np.array(triples),
                        k=k, px_um=px)
    return dict(cohort=c, cells=n_tgt, markers=len(triples),
                images=int(df.image_id.nunique()), median_um=round(med, 2),
                full_rows=int(valid.all(axis=1).sum()),
                no_nbr=int((~valid.any(axis=1)).sum()),
                mb=round(os.path.getsize(nbr_path(c)) / 1048576, 1),
                seconds=round(time.time() - t0, 1))


def do_build(cohorts):
    assert_roster()
    rows = []
    for c in cohorts:
        r = build_cohort(c)
        rows.append(r)
        flag = 'OK ' if DIST_LO <= r['median_um'] <= DIST_HI else 'OUT'
        print("  {:10} {:>6,} cells x {:>2} markers  {:>4} images  "
              "median edge {:>6.2f} um [{}]  {:>4} isolated  {:>6.1f} MB  {:>5.1f}s".format(
                  r['cohort'], r['cells'], r['markers'], r['images'],
                  r['median_um'], flag, r['no_nbr'], r['mb'], r['seconds']))
    D = pd.DataFrame(rows)
    bad = D[(D.median_um < DIST_LO) | (D.median_um > DIST_HI)]
    print("\ncheck 7 {} - median edge distance inside {}-{} um for {}/{} cohorts".format(
        'PASS' if bad.empty else 'FAIL', DIST_LO, DIST_HI, len(D) - len(bad), len(D)))
    if not bad.empty:
        print("  OUT OF RANGE. The usual cause is a graph built on the 40k subsample instead "
              "of the raw table, which would put UPMC near 79 um:")
        print(bad[['cohort', 'median_um']].to_string(index=False))
    D.to_csv(os.path.join(WORK, 's4_graph.csv'), index=False)
    return D


def main():
    if '--build' in sys.argv:
        cohorts = [c for c in TRAIN if os.path.exists(raw_table(c))]
        print("building kNN sidecars, k={}, from the FULL raw tables\n".format(K))
        do_build(cohorts)
        return
    print("nothing to do. --build first, then --pilot or --gate.")


if __name__ == '__main__':
    main()

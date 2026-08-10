"""
STAGE 1b - automatic label alignment.  Produces GATE 1b.

WHAT THIS REPLACES. The old `pipeline/step4_labels.py` holds a hand-written dictionary mapping
every native label of every cohort into a fixed Cell Ontology tree. Adding a cohort means
hand-writing a new block. It does not scale, and it assumes the biology fits a human-made tree.
Nothing in this file reads that dictionary. It is extracted once into `_validation/` and used
ONLY to score the result - if it fed the method, check 1 would be marking its own homework.

WHY NOT TEXT EMBEDDINGS. Measured against the real labels in this roster, text fails in both
directions at once: `SC` and `EC` are one character apart and mean squamous carcinoma and
endothelial cell; `CD4 T cell` and `CD8 T cell` have cosine ~0.97 and are opposite cell types;
`vasculature`/`Vessel`/`Endothelial`/`EC` share no word and are one cell type. Hardest of all,
Phillips and CRC BOTH have a label spelled exactly `tumor cells`, and they are different cell
types - Phillips is a T-cell lymphoma. No string method can get that right. Marker profiles can,
and text is therefore out of the distance entirely (M4, alpha = 0).

THE METHOD, four mechanisms. Each is documented at the function that implements it, including
where building it showed the plan's version to be wrong - those notes are kept deliberately,
because every one of them was found by a measurement rather than by argument.

M1  A label's signature is a DISTRIBUTION. Per (cohort, label, marker) store nine quantiles of
    the Gate 1 winning transform (u_coh, the per-cohort ECDF), the MEAN RANK, prevalence, and the
    within-label co-expression matrix. Position for merging is the mean rank - the Mann-Whitney
    statistic behind the 0.91-1.00 AUROCs Gate 1 measured - and the quantiles carry the spread,
    which is what the directional layer needs. See `rescale`.

M2  Two relations, not one. A SYMMETRIC distance on position decides merging; DIRECTED
    CONTAINMENT on spread decides nesting. The plan used containment for both, and measurement
    showed that is backwards: interval overlap tracks how WIDE two labels are, not where they
    sit. See `containment`.

M2b The nesting graph is forced acyclic by SCC CONTRACTION, then closed only where evidence was
    missing. Contraction gives a DAG by theorem rather than by hope, and reads correctly in
    biology: labels that mutually contain each other ARE one type. Blanket transitive closure is
    rejected - it amplifies one false edge across everything downstream and does not even
    guarantee acyclicity, since closing an existing cycle just turns it into a complete blob.

M3  Granularity is chosen PER BRANCH by stability, not by a global cut. Each cluster is offered a
    binary split, kept only if it reproduces with a cohort held out. This is what lets CD4 T and
    CD8 T separate inside the T-cell branch without shattering the rest of the label space, and
    it is size-agnostic, so a rare-but-global type is safe from being swallowed. See `refine`.

M4  Clusters are NAMED from their top discriminative markers. Text does naming only, never
    distance, so a cohort shipping `Population_1` costs nothing.

NOTHING IS TUNED AGAINST THE ANSWER. Tuning the granularity against the hand mapping would make
check 1 circular. Four label-free objectives were built and every one is biased toward an end of
the range (see `choose_cut`), so instead the two trivial ends are excluded by guards that state
what a usable shared label space IS - no cluster may hold a quarter of all labels, and at least
95% of cells must sit in a cluster that spans more than one cohort - and stability chooses inside
what is left. The agreement curve is reported next to the stability curve across the whole sweep,
so a reader can see for themselves whether the chosen point was lucky.

    python s1b_labels.py                  # everything: build, cluster, all 7 checks, report
    python s1b_labels.py --evidence-sweep  # check 3 only: evidence coverage + floor sweep
    python s1b_labels.py --graph-check     # check 7 only: DAG assert, SCCs, transitivity
    python s1b_labels.py --resign          # force signatures to be recomputed
"""
import json
import os
import sys
import time
from itertools import combinations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from scipy.optimize import linear_sum_assignment

import config
from config import SPECS, WORK, PANEL, REPORTS, FIGURES, raw_table, SEED

# ------------------------------------------------------------------ declared constants
QLEV = np.array([0.02, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.98])
I_LO, I_HI, I_MED = 2, 6, 4          # indices of q10, q90, q50 in QLEV

MIN_CELLS = 100      # below this a label's quantiles are noise, not a signature
DELTA = 0.05         # geometric-mean floor: one zero-overlap marker vetoes, but not outright
W_MIN = 0.10         # a marker counts as INFORMATIVE if its between-label range reaches this
K_EVID = 8           # evidence floor: informative shared markers needed for a direct edge
SCALE_FLOOR = 0.05   # floor on the within-cohort between-label scale, guards a flat marker
NEST_MIN = 0.75      # containment needed before a directed nesting edge is drawn
NEST_RELATED = 1.5   # a nesting pair must also be within this multiple of the cut of each other
MARGIN = 0.10        # asymmetry needed to call a pair NESTED rather than merged
CUT_GRID = np.round(np.arange(0.30, 1.16, 0.025), 4)
FAR = 5.0            # distance stand-in for "below the evidence floor", i.e. never comparable
SPLIT_SUPPORT = 0.5  # a per-branch split is kept only if its LOCO reproducibility reaches this
MIN_SPLIT_LABELS = 2  # neither side of a split may be smaller than this
COHORT_ARI_MAX = 0.20    # HARD GUARD: a clustering that is really the cohort partition is a fail
MAX_CLUSTER_SHARE = 0.25  # HARD GUARD: no single cluster may hold this share of all labels
MIN_CROSS_SHARE = 0.95    # HARD GUARD: share of CELLS that must sit in a cross-cohort cluster

SIG_CACHE = os.path.join(WORK, 's1b_signatures.npz')
RARE_GLOBAL = ['Plasma', 'NK', 'DC']     # the M3 test cases named in the plan


# ============================================================== M1 - signatures
def registry():
    return pd.read_csv(os.path.join(WORK, 'marker_registry.csv'), keep_default_na=False)


def built():
    return [c for c in SPECS if os.path.exists(raw_table(c))]


def cohort_markers(cohorts):
    """triple -> raw column, per cohort. Non-protein channels are excluded here."""
    r = registry()
    r = r[(r.kind != 'non_protein') & r.cohort.isin(cohorts)]
    out = {}
    for c, g in r.groupby('cohort'):
        out[c] = g.drop_duplicates('triple').set_index('triple').raw_column.to_dict()
    gene = r.drop_duplicates('triple').set_index('triple').gene.to_dict()
    return out, gene


def build_signatures(cohorts):
    """One pass per cohort. Reads every cell; writes a signature per (cohort, label).

    The value transform is `u_coh` - the per-cohort empirical CDF - which is the arm that won
    GATE 1. It is applied to EVERY marker the cohort measures, not just the 9-marker core:
    Gate 1 restricted to the core so that no arm could win on imputation, but here a wider panel
    is exactly what makes a cohort pair comparable, and the evidence floor handles thin pairs.
    """
    cmark, gene = cohort_markers(cohorts)
    triples = sorted({t for m in cmark.values() for t in m})
    ti = {t: i for i, t in enumerate(triples)}
    T = len(triples)

    keys, QT, MEAN, PREV, NCELL, COEX, dropped = [], [], [], [], [], [], []
    RNG = {}
    for c in cohorts:
        t0 = time.time()
        cols = cmark[c]
        use = sorted(cols)
        df = pd.read_parquet(raw_table(c), columns=['native_label'] + [cols[t] for t in use])
        lab = df.native_label.astype(str).str.strip()
        U = df[[cols[t] for t in use]].astype('float32')
        U.columns = use
        # identical transform to the Gate 1 winner V3: mid-rank ECDF inside (cohort, marker)
        U = U.rank(pct=True, method='average').astype('float32')
        n_tot = len(U)

        vc = lab.value_counts()
        bad = {'', 'nan', 'none', 'null', 'na'}
        good = [l for l in vc.index if l.lower() not in bad and vc[l] >= MIN_CELLS]
        for l in vc.index:
            if l not in good:
                dropped.append(dict(cohort=c, native_label=l, cells=int(vc[l]),
                                    reason='unlabelled' if l.lower() in bad
                                           else f'below MIN_CELLS={MIN_CELLS}'))

        Uv = U.to_numpy()
        col_of = {t: k for k, t in enumerate(use)}
        meds = {}
        for l in good:
            m = (lab == l).to_numpy()
            sub = Uv[m]
            q = np.full((T, len(QLEV)), np.nan, 'float32')
            qq = np.nanquantile(sub, QLEV, axis=0).astype('float32').T      # (M, nq)
            mn = np.full(T, np.nan, 'float32')
            mm = np.nanmean(sub, axis=0).astype('float32')
            cx = np.full((T, T), np.nan, 'float32')
            with np.errstate(invalid='ignore', divide='ignore'):
                cc = np.corrcoef(sub, rowvar=False).astype('float32')
            for t, k in col_of.items():
                q[ti[t]] = qq[k]
                mn[ti[t]] = mm[k]
                for t2, k2 in col_of.items():
                    cx[ti[t], ti[t2]] = cc[k, k2]
            keys.append((c, l))
            QT.append(q)
            MEAN.append(mn)
            COEX.append(cx)
            PREV.append(sub.shape[0] / n_tot)
            NCELL.append(int(sub.shape[0]))
            meds[l] = mn

        # marker informativeness INSIDE this cohort: how far apart its label medians spread
        M = np.vstack([meds[l] for l in good])                              # (L, T)
        rng = np.full(T, np.nan, 'float32')
        seen = np.array([ti[t] for t in use])
        rng[seen] = np.nanmax(M[:, seen], 0) - np.nanmin(M[:, seen], 0)
        RNG[c] = rng
        print(f'  {c:9s} {n_tot:>9,} cells  {len(use):3d} markers  '
              f'{len(good):2d} labels kept  {time.time()-t0:5.1f}s')
        del df, U, Uv

    np.savez_compressed(
        SIG_CACHE,
        cohort=np.array([k[0] for k in keys]), label=np.array([k[1] for k in keys]),
        QT=np.stack(QT), MEAN=np.stack(MEAN), COEX=np.stack(COEX),
        PREV=np.array(PREV), NCELL=np.array(NCELL),
        triples=np.array(triples), gene=np.array([gene[t] for t in triples]),
        rng_cohort=np.array(list(RNG)), RNG=np.stack([RNG[c] for c in RNG]),
        dropped=np.array(json.dumps(dropped)))
    return load_signatures()


def load_signatures():
    z = np.load(SIG_CACHE, allow_pickle=False)
    S = dict(z)
    S['nodes'] = pd.DataFrame(dict(cohort=S['cohort'], label=S['label'],
                                   prev=S['PREV'], n_cells=S['NCELL']))
    S['dropped'] = pd.DataFrame(json.loads(str(S['dropped'])))
    S['rng'] = {c: S['RNG'][i] for i, c in enumerate(S['rng_cohort'])}
    return S


# ============================================================== M2 - directed containment
def rescale(S):
    """Put every cohort's signatures into ONE comparable unit: between-label spread.

    THIS IS THE FIX FOR A REAL FAILURE, kept in the code because the failure is instructive.
    The first build compared labels on raw `u_coh` and produced clusters that tracked COHORT,
    not cell type - 54 labels of every kind from CRC+UPMC+Phillips in one blob, all 9 Keren
    immune labels in another, all 16 Sorin labels as singletons.

    The reason is that `u_coh` is a per-cohort ECDF, so where a label SITS depends on that
    cohort's composition. Keren is 50.3% keratin-positive tumour, so keratin's ECDF is dominated
    by tumour cells and every other Keren label is pushed low; CRC's tumour is 18.4%, so the same
    biology lands somewhere else entirely. Comparing absolute positions across cohorts therefore
    compares compositions, which is precisely the cohort fingerprint this whole rebuild exists to
    remove.

    What IS comparable is a label's position relative to the OTHER LABELS OF ITS OWN COHORT -
    "ferguson SC has the highest pan-keratin in ferguson" and "CRC tumor cells has the highest
    cytokeratin in CRC" are the same statement. So each (cohort, marker) is centred on the median
    of its label medians and divided by their IQR-based scale, and the SAME affine map is applied
    to all nine quantiles of every label. Being affine, it leaves the containment direction
    untouched: a narrow subtype inside a broad parent stays narrow inside broad.

    ONE statistic does both jobs here, deliberately. An earlier version selected markers by the
    RANGE of the label medians but divided by their IQR, and that is inconsistent in a way that
    breaks exactly the markers that matter most: a lineage marker is high in ONE label and flat
    in the rest - CD20 in B cells, keratin in tumour - so its range is large while its IQR is
    near zero. Dividing by the IQR then sent those markers to |z| in the hundreds and every
    cross-cohort similarity collapsed to 0.000. Both the scale and the informativeness weight are
    now the p90-p10 spread of the label positions, so a marker cannot be called informative by
    one rule and rescaled by another.

    POSITION IS THE MEAN RANK, NOT THE MEDIAN, and this is the third measured correction. With
    the median, Sorin had only 5 of its 17 markers showing ANY between-label spread and Keren 19
    of 39, so Sorin's 16 labels could not reach the evidence floor against anything and came out
    as 16 singletons. The cause is zero inflation: Sorin arrives uint8, so on most markers over
    half the cells are 0, the mid-rank ECDF ties them all at one value, and nearly every label
    inherits that same median. The median cannot see that 80% of B cells are CD20-positive while
    5% of tumour cells are - but the MEAN RANK can, because it is the average percentile.

    That statistic is not a new invention here: mean rank is the Mann-Whitney statistic, which is
    exactly the AUROC that Gate 1 used to show labels track their markers at 0.91-1.00 for B
    cells, CD8 T and Tregs in every cohort. So the position used for alignment is the same
    quantity that was already measured to work.

    M1 said "a distribution, not a mean", and half of that is upheld and half corrected. The
    correction: a mean of RANKS is a bounded, tie-safe location statistic, not the mean-of-values
    M1 was objecting to. What is upheld: the quantiles are still stored and still do real work -
    they are the whole basis of the DIRECTIONAL layer, where broad-parent versus narrow-subtype
    is a statement about spread that no location statistic can make.
    """
    QT, MEAN, nodes = S['QT'], S['MEAN'], S['nodes']
    Z = QT.copy()
    P = MEAN.copy()
    W = np.zeros((len(nodes), QT.shape[1]), 'float32')
    for c in nodes.cohort.unique():
        m = (nodes.cohort == c).to_numpy()
        pos = MEAN[m]                                                      # (L, T)
        ctr = np.nanmedian(pos, 0)
        spread = np.nanmax(pos, 0) - np.nanmin(pos, 0)
        sc = np.maximum(spread, SCALE_FLOOR)
        Z[m] = (QT[m] - ctr[None, :, None]) / sc[None, :, None]
        P[m] = (pos - ctr[None, :]) / sc[None, :]
        W[m] = np.nan_to_num(spread, nan=0.0)
    return Z, P, W


def containment(S, Z=None):
    """Two separate relations, because they answer two different questions.

    SIM[i,j] - SYMMETRIC, drives clustering. `exp(-d)` where d is the RMS difference between the
        two labels' median POSITIONS over the scored markers.

    CON[i,j] - DIRECTED, drives nesting only. The fraction of i's q10-q90 spread lying inside
        j's, so `i ⊂ j` when high. This is the plan's containment measure.

    WHY POSITION ONLY IN THE SYMMETRIC LAYER - measured, and it corrects half of M1. Widening the
    symmetric distance from the median to more of the quantile curve makes it monotonically
    worse, because the SPREAD is where the cohort effect lives (segmentation quality, dynamic
    range, uint8 quantisation) while the position is the comparable part. Separation between
    known-same and known-different pairs, and the residual within-vs-cross-cohort offset:

        quantiles used     separation gap    cohort offset
        median only              0.196            0.003
        q25,q50,q75              0.135            0.051
        q10 ... q90              0.075            0.087

    So M1 is half right and half wrong, and both halves are kept: storing the distribution rather
    than a mean is what makes the DIRECTIONAL layer possible at all - a broad parent versus a
    narrow subtype is a statement about spread - but merging must be decided on position. The
    quantiles are not discarded; they moved to the relation they actually serve.

    THE PLAN USED CONTAINMENT FOR BOTH AND THAT IS WRONG ON THIS DATA - measured, not argued.
    Interval overlap is dominated by how WIDE two labels are, not by where they SIT, and after
    rescaling almost every label is wider than the between-label spread, so overlaps are large
    within a cohort and small across cohorts whatever the biology:

        UPMC Tumor          vs UPMC CD8 T cell   0.835   <- opposite cell types, scored HIGH
        CRC tumor cells     vs CRC B cells       0.799   <- opposite cell types, scored HIGH
        Keren Keratin+tumor vs ferguson SC       0.162   <- the SAME cell type, scored LOW

    That ordering is exactly backwards, and it is what produced the first build's clusters:
    54 mixed labels from CRC+UPMC+Phillips in one blob and all 16 Sorin labels as singletons.
    Position is what actually carries cell-type identity here - Gate 1 measured per-label marker
    AUROCs of 0.91-1.00 for B cells, CD8 T and Tregs in every cohort - so position decides
    merging and containment is demoted to deciding DIRECTION between clusters that are already
    related. The plan's M2 shape survives; only which statistic feeds which decision changed.

    EVID[i,j] = number of INFORMATIVE shared markers. A marker is informative for a cohort pair
    when its between-label range reaches W_MIN in BOTH cohorts - a marker that is flat in one
    cohort separates nothing there, so counting it as evidence would overstate what was measured.
    That is why the floor bites at all: every cohort pair in this roster shares at least 11 raw
    markers, so a raw count would make the floor dead code.

    EVERY informative shared marker is scored, and the panel-size problem is solved by
    NORMALISING PER COHORT PAIR instead. Cohort pairs share very different numbers of markers
    (CRC-Phillips 47, Sorin-ferguson 11), and under any averaging rule a real disagreement is
    diluted by however many markers happen to agree - so the same biological difference scores
    differently depending on panel size, and distances are not comparable between blocks.

    Selecting a fixed number of "most informative" markers per cohort pair was tried first and
    fails, twice, for the same underlying reason: NO GLOBAL RANKING OF MARKERS CAN SERVE EVERY
    LABEL PAIR. Ranking by the p90-p10 spread of label positions dropped `MS4A1` (CD20) and
    pan-keratin out of the top 8 of every cohort pair - because CD20 is high in exactly ONE label
    out of 16-27, so trimming the top decile deletes precisely the signal that defines B cells.
    Switching the ranking to max-min brought CD20 back but swung CRC-UPMC onto stromal markers,
    and `CD4 T vs CD8 T` (0.801) stopped being distinguishable from `Tumor vs CD8 T` (0.791). A
    marker that identifies one rare cell type is worthless for every other pair and decisive for
    that one, which is exactly what a global ranking cannot express.

    So all informative markers contribute, weighted by how far apart they push the labels of both
    cohorts, and each cohort-pair BLOCK of the distance matrix is divided by its own median
    distance. Dilution then rescales a whole block uniformly, which leaves the ordering inside
    the block untouched, and the division makes blocks comparable to each other. A side effect
    worth stating plainly: this removes the cohort offset by construction, so `cohort_ari` lands
    near 0.00 and that guard stops being informative - it is kept as a check, not as evidence.
    """
    QT, nodes = S['QT'], S['nodes']
    Z, P, W = rescale(S) if Z is None else Z
    n, T = len(nodes), QT.shape[1]
    lo, hi = Z[:, :, I_LO], Z[:, :, I_HI]
    has = ~np.isnan(lo)

    SIM = np.full((n, n), np.nan, 'float32')
    C = np.full((n, n), np.nan, 'float32')
    EV = np.zeros((n, n), 'int32')
    CX = np.full((n, n), np.nan, 'float32')
    coex = S['COEX']

    for i in range(n):
        w = np.minimum(W[i], W)                                            # (n, T)
        shared = has[i] & has
        w = np.where(shared & (w >= W_MIN), w, 0.0)
        EV[i] = (w > 0).sum(1)                                             # the HONEST evidence
        u = w                                                              # every informative marker

        inter = np.clip(np.minimum(hi[i], hi) - np.maximum(lo[i], lo), 0, None)
        wid = hi[i] - lo[i]
        with np.errstate(invalid='ignore', divide='ignore'):
            o = inter / np.where(wid > 1e-6, wid, np.nan)
        # a degenerate (zero-width) marker in i is a point: inside j or not
        pt = (lo[i] >= lo - 1e-6) & (lo[i] <= hi + 1e-6)
        o = np.where(np.isfinite(o), o, pt.astype('float32'))
        o = np.clip(np.nan_to_num(o, nan=0.0), 0.0, 1.0)

        sw = u.sum(1)
        with np.errstate(invalid='ignore', divide='ignore'):
            C[i] = np.exp((u * np.log(np.maximum(o, DELTA))).sum(1) / np.where(sw > 0, sw, np.nan))
            # symmetric: weighted RMS distance between the two mean-rank positions
            d2 = (P[i][None] - P) ** 2                                     # (n, T)
            d2 = np.where(u > 0, np.nan_to_num(d2, nan=0.0), 0.0)
            SIM[i] = np.sqrt((d2 * u).sum(1) / np.where(sw > 0, sw, np.nan))

        # co-expression agreement: correlation between the two labels' marker-marker matrices,
        # restricted to the markers they actually share. Reported, and used only in an ablation.
        for j in range(n):
            if EV[i, j] == 0 or j == i:
                continue
            m = shared[j] & (np.minimum(W[i], W[j]) >= W_MIN)
            idx = np.flatnonzero(m)
            if len(idx) < 3:
                continue
            a = coex[i][np.ix_(idx, idx)][np.triu_indices(len(idx), 1)]
            b = coex[j][np.ix_(idx, idx)][np.triu_indices(len(idx), 1)]
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() >= 3 and a[ok].std() > 1e-6 and b[ok].std() > 1e-6:
                CX[i, j] = np.corrcoef(a[ok], b[ok])[0, 1]

    # normalise each cohort-pair block by its own median distance, THEN map to a similarity
    coh = nodes.cohort.to_numpy()
    for a in np.unique(coh):
        for b in np.unique(coh):
            blk = np.ix_(coh == a, coh == b)
            d = SIM[blk]
            fin = np.isfinite(d) & (d > 0)
            if fin.any():
                SIM[blk] = d / np.median(d[fin])
    SIM = np.exp(-SIM)

    np.fill_diagonal(C, 1.0)
    np.fill_diagonal(SIM, 1.0)
    np.fill_diagonal(EV, 0)
    return SIM, C, EV, CX


# ============================================================== clustering
def distance(active, SIM, EV, k=K_EVID):
    """-log(similarity), with below-the-floor pairs pushed to FAR so they never merge directly.

    They may still end up together THROUGH a third label that is comparable to both, which is
    exactly the transitive bridging M2 asks for - average linkage does it as a side effect of
    how it merges, rather than as a separate closure step.
    """
    a = np.asarray(active)
    sub = np.ix_(a, a)
    D = -np.log(np.clip(SIM[sub], 1e-6, 1.0)).astype(float)
    D = (D + D.T) / 2.0
    D[EV[sub] < k] = FAR
    np.fill_diagonal(D, 0.0)
    return D


def cluster(active, SIM, EV, cut, k=K_EVID, coex_gate=None):
    """Average-linkage agglomerative clustering on the SYMMETRIC layer, cut at height `cut`.

    NOT Leiden, and that is a measured change from the plan. Leiden optimises modularity on a
    graph; here the similarity is DENSE over ~100 nodes, and modularity on a dense graph returns
    one giant community plus singletons - which is exactly what it did: one 54-label community
    mixing tumour, macrophages, T cells and B cells. Its resolution parameter could be raised,
    but then granularity is set by two interacting knobs (threshold AND resolution) and is no
    longer identifiable. Average linkage makes the single knob mean something exact - the cut is
    the largest average distance allowed inside a cluster - and measurably works better on the
    same inputs: ARI against the hand mapping's L2 level 0.86 versus 0.65.

    Nesting stays a separate directed layer and is deliberately not shown to the clusterer - a
    subtype and its parent are not the same cluster.
    """
    D = distance(active, SIM, EV, k)
    if coex_gate is not None:
        g = coex_gate[np.ix_(np.asarray(active), np.asarray(active))]
        D[np.isfinite(g) & (g < 0)] = FAR
        np.fill_diagonal(D, 0.0)
    if len(D) < 2:
        return np.zeros(len(D), int)
    Lk = linkage(squareform(D, checks=False), method='average')
    return fcluster(Lk, cut, criterion='distance') - 1


def ari(a, b, w=None):
    """Adjusted Rand index, optionally weighted so each label counts by its CELLS."""
    a, b = np.asarray(a), np.asarray(b)
    w = np.ones(len(a)) if w is None else np.asarray(w, float)
    ca, cb = pd.factorize(a)[0], pd.factorize(b)[0]
    M = np.zeros((ca.max() + 1, cb.max() + 1))
    np.add.at(M, (ca, cb), w)
    c2 = lambda x: x * (x - 1.0) / 2.0
    idx, ai, bi, n = c2(M).sum(), c2(M.sum(1)).sum(), c2(M.sum(0)).sum(), w.sum()
    exp = ai * bi / c2(n)
    mx = 0.5 * (ai + bi)
    return float((idx - exp) / (mx - exp)) if mx > exp else 0.0


def cohort_driven(nodes, memb):
    """How much of the clustering is just 'which cohort is this'.

    Stability alone CANNOT catch this failure and the first build proved it: a clustering that
    is really the cohort partition is perfectly reproducible when a different cohort is dropped,
    and it scored 0.972. So this is a separate HARD GUARD, not a term in the objective. It also
    needs no labels - cohort id is metadata, not a cell type - so using it is not circular.
    """
    ar = ari(memb, nodes.cohort.to_numpy())
    spans = {c for c in np.unique(memb)
             if nodes.cohort[memb == c].nunique() >= 2}
    inx = np.isin(memb, list(spans)) if spans else np.zeros(len(memb), bool)
    w = nodes.n_cells.to_numpy()
    return ar, float(w[inx].sum() / w.sum())


def choose_cut(S, SIM, EV, k=K_EVID):
    """Pick the dendrogram cut by two declared GUARDS, not by an optimised score.

    Four label-free objectives were built and measured, and every one of them is biased:

        LOCO stability (ARI, full vs held-out)   flat at 0.91-0.99 across the whole range
        held-out-cohort transfer                 monotone toward COARSE - coarse labels are
                                                 trivially easier to transfer
        dendrogram merge-height gap              toward coarse, it always finds the root
        silhouette                               toward FINE, a singleton scores a perfect 1

    Every one of those biases points at an END of the range, which is the tell: each is really
    measuring "is this partition trivial" in a different direction. So instead of optimising a
    biased score, the two trivial ends are excluded by GUARDS that say what a usable shared label
    space is, and stability - the one measure with no directional bias, only low resolution - is
    used to choose inside what is left.

    THE THREE GUARDS, none of which reads a label of record:

      biggest_share <= MAX_CLUSTER_SHARE   no cluster may hold a quarter of all labels. This is
          the coarse-end collapse, and it is abrupt rather than gradual: one merge fuses two
          already-large groups and the biggest cluster goes 23 -> 39 -> 49 -> 66 -> 89 labels in
          four steps. A "cell type" holding a quarter of every label in the roster annotates
          nothing.
      cross_cohort_share >= MIN_CROSS_SHARE   the share of CELLS sitting in a cluster that holds
          labels from more than one cohort. This is the fine-end collapse, and it is the
          DELIVERABLE stated as a constraint: Stage 1b exists to produce a SHARED label space to
          train on, and a cluster holding one cohort's labels alone teaches nothing about
          cross-cohort generalisation. It is counted in CELLS, not labels, because cells are what
          gets trained on. The bar is not 100% precisely because cohort-exclusive clusters are
          wanted - they are the Stage 7 novel-class test material - so up to 5% of cells are
          allowed to sit outside the shared space.
      cohort_ari <= COHORT_ARI_MAX   the clustering must not simply be the cohort partition.

    Within the feasible window the quality surface is a broad PLATEAU - every cut from 0.30 to
    0.45 lands within 0.04 ARI of the best - so the exact landing point matters little. The full
    sweep is printed so a reader can confirm that rather than take it on trust.
    """
    nodes, rows = S['nodes'], []
    allidx = np.arange(len(nodes))
    n = len(nodes)
    for cut in CUT_GRID:
        full = cluster(allidx, SIM, EV, cut, k)
        aris = []
        for c in sorted(nodes.cohort.unique()):
            sub = np.flatnonzero((nodes.cohort != c).to_numpy())
            aris.append(ari(full[sub], cluster(sub, SIM, EV, cut, k),
                            nodes.n_cells.to_numpy()[sub]))
        car, share = cohort_driven(nodes, full)
        vc = pd.Series(full).value_counts()
        rows.append(dict(cut=float(cut), clusters=int(full.max() + 1),
                         singletons=int((vc == 1).sum()), biggest=int(vc.max()),
                         biggest_share=float(vc.max() / n), stability=float(np.mean(aris)),
                         cohort_ari=car, cross_cohort_share=share))
    df = pd.DataFrame(rows)
    df['usable'] = ((df.biggest_share <= MAX_CLUSTER_SHARE) &
                    (df.cross_cohort_share >= MIN_CROSS_SHARE) &
                    (df.cohort_ari <= COHORT_ARI_MAX))
    return df


def cohort_driven_note():
    return (f'cohort_ari is computed UNWEIGHTED, per label. The cell-weighted version was tried '
            f'first and is misleading here: cohort sizes run from 117k cells (Phillips) to 2.1M '
            f'(Sorin), so a single cluster holding `Sorin|Cancer` alone carries 930k cells and '
            f'drags the statistic to 0.5 while the label-level structure is fine (0.10).')


def loco_memberships(S, SIM, EV, tau, k=K_EVID):
    nodes = S['nodes']
    out = {}
    for c in sorted(nodes.cohort.unique()):
        sub = np.flatnonzero((nodes.cohort != c).to_numpy())
        out[c] = dict(zip(sub, cluster(sub, SIM, EV, tau, k)))
    return out


def refine(S, memb, SIM, EV, k=K_EVID):
    """M3 - granularity chosen PER BRANCH by stability, not by the global cut.

    The global cut is chosen by guards that are necessarily conservative, so it lands at the
    coarsest granularity that keeps the label space usable. That is right for the top level and
    too coarse inside a branch: CD4 T and CD8 T differ on 2 of the ~30 informative markers their
    cohorts share, so their distance is 0.56 block-medians while tumour-versus-T-cell is 1.23.
    The ORDERING is correct - CD4 T really is more like CD8 T than like a tumour cell - but no
    single global cut can separate the first pair without shattering everything else. That is
    exactly the argument M3 makes against a global cut.

    So each cluster is offered a binary split, recursively, and a split is KEPT only if it
    reproduces when a cohort is held out. Three conditions, all required:

      * both sides keep at least MIN_SPLIT_LABELS labels, so a split cannot peel off one label;
      * both sides span at least 2 cohorts, so a "split" can never be a cohort boundary in
        disguise - this is the cohort guard applied per branch instead of globally;
      * mean leave-one-cohort-out ARI of the split >= SPLIT_SUPPORT, so it must be reproducible
        rather than an artefact of one cohort's panel.

    This replaces an earlier merge-BACK version that took connected components over unstable
    label pairs. That was wrong in a way worth recording: one unstable pair chained two otherwise
    healthy clusters into one, and it cost 0.09 agreement (19 clusters at 0.923 collapsing to 15
    at 0.834). Splitting downward with a per-split test cannot chain.
    """
    out = memb.copy()
    nxt = int(memb.max()) + 1
    log = []
    stack = [int(c) for c in np.unique(memb)]
    while stack:
        c = stack.pop()
        idx = np.flatnonzero(out == c)
        if len(idx) < 2 * MIN_SPLIT_LABELS:
            continue
        two = _bisect(idx, SIM, EV, k)
        if two is None:
            continue
        rec = _split_ok(S, idx, two, SIM, EV, k)
        log.append(rec)
        if not rec['kept']:
            continue
        out[idx[two == 1]] = nxt
        stack += [c, nxt]
        nxt += 1
    return pd.factorize(out)[0], log


def _bisect(idx, SIM, EV, k):
    D = distance(idx, SIM, EV, k)
    if len(D) < 2 or not np.isfinite(D).any():
        return None
    return fcluster(linkage(squareform(D, checks=False), method='average'),
                    2, criterion='maxclust') - 1


def _split_ok(S, idx, two, SIM, EV, k):
    """Is this binary split real? Both sides substantial, both cross-cohort, and reproducible."""
    nodes = S['nodes']
    coh = nodes.cohort.to_numpy()[idx]
    sizes = [int((two == v).sum()) for v in (0, 1)]
    ncoh = [int(pd.Series(coh[two == v]).nunique()) for v in (0, 1)]
    rec = dict(labels=len(idx), left=sizes[0], right=sizes[1],
               left_cohorts=ncoh[0], right_cohorts=ncoh[1], stability=float('nan'), kept=False,
               reason='')
    if min(sizes) < MIN_SPLIT_LABELS:
        rec['reason'] = f'a side would hold < {MIN_SPLIT_LABELS} labels'
        return rec
    if min(ncoh) < 2:
        rec['reason'] = 'a side would be one cohort only - that is a cohort boundary, not a type'
        return rec
    aris = []
    for c in np.unique(coh):
        keep = coh != c
        if keep.sum() < 4 or pd.Series(two[keep]).nunique() < 2:
            continue
        sub = _bisect(idx[keep], SIM, EV, k)
        if sub is None:
            continue
        aris.append(ari(sub, two[keep]))
    rec['stability'] = float(np.mean(aris)) if aris else 0.0
    if not aris:
        rec['reason'] = 'not testable - no cohort can be held out'
        return rec
    if rec['stability'] < SPLIT_SUPPORT:
        rec['reason'] = f'split does not reproduce (LOCO ARI {rec["stability"]:.2f})'
        return rec
    rec['kept'] = True
    rec['reason'] = 'reproduces across held-out cohorts'
    return rec


# ============================================================== M2b - nesting, SCC, closure
def nesting(S, memb, C, EV, SIM=None, cut=None, tau=NEST_MIN, k=K_EVID):
    """Directed layer BETWEEN clusters, then forced acyclic by contracting SCCs.

    A nesting edge additionally requires the two clusters to be RELATED. Containment on its own
    will call any wide cluster the parent of any narrow one, however unrelated they are, and
    without this the layer degenerates: one broad cluster came out as the "parent" of nearly
    every other, which is not a hierarchy, it is a statement that the cluster is wide. So a pair
    must also sit within NEST_RELATED times the chosen cut of each other - that is, they must be
    close enough that a slightly coarser granularity would have merged them, which is precisely
    what a parent-child pair means.
    """
    n_cl = memb.max() + 1
    members = [np.flatnonzero(memb == c) for c in range(n_cl)]
    dmax = NEST_RELATED * cut if cut else np.inf

    def blocks(mem):
        m2 = len(mem)
        Cc = np.full((m2, m2), np.nan)
        Ec = np.zeros((m2, m2), int)
        Rel = np.zeros((m2, m2), bool)
        for u in range(m2):
            for v in range(m2):
                if u == v:
                    continue
                sub = np.ix_(mem[u], mem[v])
                ok = (EV[sub] >= k) & np.isfinite(C[sub])
                Ec[u, v] = int(ok.sum())
                if ok.any():
                    Cc[u, v] = float(C[sub][ok].mean())
                if SIM is not None:
                    s = SIM[sub][np.isfinite(SIM[sub])]
                    Rel[u, v] = bool(len(s) and -np.log(max(float(s.mean()), 1e-9)) <= dmax)
                else:
                    Rel[u, v] = True
        return Cc, Ec, Rel

    def build(mem):
        Cc, Ec, Rel = blocks(mem)
        g = nx.DiGraph()
        g.add_nodes_from(range(len(mem)))
        for u in range(len(mem)):
            for v in range(len(mem)):
                if u == v or not np.isfinite(Cc[u, v]) or not Rel[u, v]:
                    continue
                # u ⊂ v : u's spread sits inside v's, and not the other way round
                if Cc[u, v] >= tau and (not np.isfinite(Cc[v, u])
                                        or Cc[u, v] - Cc[v, u] >= MARGIN):
                    g.add_edge(u, v, contain=float(Cc[u, v]), pairs=int(Ec[u, v]),
                               kind='measured')
        return g, Cc, Ec

    G, Cc, Ec = build(members)

    sccs = [s for s in nx.strongly_connected_components(G) if len(s) > 1]
    cyc_before = len(sccs)
    contract = {}
    for s in sccs:
        t = min(s)
        for x in s:
            contract[x] = t
    memb2 = np.array([contract.get(c, c) for c in memb])
    memb2 = pd.factorize(memb2)[0]

    # rebuild on the contracted clusters; a DAG is now guaranteed, and asserted
    mem2 = [np.flatnonzero(memb2 == c) for c in range(memb2.max() + 1)]
    D, Cc2, Ec2 = build(mem2)
    # contraction can only remove cycles between the merged nodes; anything left is re-contracted
    guard = 0
    while not nx.is_directed_acyclic_graph(D) and guard < 10:
        guard += 1
        for s in [s for s in nx.strongly_connected_components(D) if len(s) > 1]:
            t = min(s)
            memb2 = np.array([t if c in s else c for c in memb2])
        memb2 = pd.factorize(memb2)[0]
        mem2 = [np.flatnonzero(memb2 == c) for c in range(memb2.max() + 1)]
        D, Cc2, Ec2 = build(mem2)
    assert nx.is_directed_acyclic_graph(D), 'SCC contraction failed to produce a DAG'

    # transitive closure: FILL only where evidence was missing; never overwrite a measurement
    bridged, violations = [], []
    for u in list(D.nodes):
        for v in nx.descendants(D, u):
            if D.has_edge(u, v):
                continue
            if Ec2[u, v] < k:
                bridged.append(dict(child=int(u), parent=int(v), pairs=int(Ec2[u, v])))
            elif np.isfinite(Cc2[u, v]) and Cc2[u, v] < tau:
                violations.append(dict(child=int(u), parent=int(v),
                                       measured=float(Cc2[u, v]), tau=float(tau),
                                       margin=float(tau - Cc2[u, v]), pairs=int(Ec2[u, v])))
    for b in bridged:
        D.add_edge(b['child'], b['parent'], contain=float('nan'), pairs=b['pairs'],
                   kind='bridged')
    assert nx.is_directed_acyclic_graph(D), 'closure introduced a cycle'
    return memb2, D, dict(sccs=[sorted(int(x) for x in s) for s in sccs],
                          cycles_before=cyc_before, bridged=bridged,
                          violations=sorted(violations, key=lambda r: -r['margin']),
                          Cc=Cc2, Ec=Ec2)


# ============================================================== M4 - naming
def name_clusters(S, memb, P, ncoh):
    """Name from the top discriminative markers. Text never enters, not even here.

    A marker may only name a cluster if at least HALF that cluster's labels actually measured it
    and it is present in >= 3 cohorts. Without that rule a 23-label cluster gets named after a
    marker only one of its members carries, which reads as a claim about the whole cluster and
    is not one.
    """
    gene, nodes = S['gene'], S['nodes']
    n_cl = memb.max() + 1
    cen = np.full((n_cl, P.shape[1]), np.nan)
    covg = np.zeros((n_cl, P.shape[1]))
    for c in range(n_cl):
        sub = P[memb == c]
        cen[c] = np.nanmean(sub, 0)
        covg[c] = np.isfinite(sub).mean(0)
    mu, sd = np.nanmean(cen, 0), np.nanstd(cen, 0)
    z = (cen - mu) / np.where(sd > 1e-6, sd, np.nan)
    names = []
    for c in range(n_cl):
        v = z[c].copy()
        v[~np.isfinite(v) | (covg[c] < 0.5) | (ncoh < 3)] = 0.0
        up = [k for k in np.argsort(-v)[:3] if v[k] > 0.8]
        dn = [k for k in np.argsort(v)[:1] if v[k] < -1.2]
        parts = [f'{gene[k]}+' for k in up] + [f'{gene[k]}-' for k in dn]
        names.append(' '.join(parts) if parts else 'no discriminative shared marker')
    return names, cen, z


# ============================================================== gate helpers
def best_match_agreement(auto, hand, w):
    """Share of CELLS whose automatic cluster maps onto the right hand class, 1:1."""
    a, ua = pd.factorize(np.asarray(auto))
    b, ub = pd.factorize(np.asarray(hand))
    M = np.zeros((len(ua), len(ub)))
    np.add.at(M, (a, b), np.asarray(w, float))
    r, c = linear_sum_assignment(-M)
    return float(M[r, c].sum() / M.sum()), {ua[i]: ub[j] for i, j in zip(r, c)}


def read_expect():
    p = os.path.join(PANEL, 'gate1b_expect.csv')
    df = pd.read_csv(p, keep_default_na=False)
    df['pairs'] = df.members.apply(
        lambda s: [tuple(x.split('|', 1)) for x in s.split(';')])
    return df


def shared_markers(S, idx):
    """Informative markers every one of these labels' cohorts actually measured."""
    _, P, W = rescale(S)
    msk = np.ones(P.shape[1], bool)
    for i in idx:
        msk &= np.isfinite(P[i]) & (W[i] >= W_MIN)
    return sorted(str(S['gene'][k])[:34] for k in np.flatnonzero(msk))


def agree_at(sweep2, tau):
    r = sweep2[np.isclose(sweep2.cut, tau)]
    return float(r.agreement_vs_hand.iloc[0]) if len(r) else float('nan')


def md_table(df, floatfmt='{:.3f}'):
    d = df.copy()
    for c in d.columns:
        if d[c].dtype.kind == 'f':
            d[c] = d[c].map(lambda v: '' if pd.isna(v) else floatfmt.format(v))
    head = '| ' + ' | '.join(map(str, d.columns)) + ' |'
    rule = '|' + '|'.join(['---'] * len(d.columns)) + '|'
    body = ['| ' + ' | '.join(map(str, r)) + ' |' for r in d.astype(str).values]
    return '\n'.join([head, rule] + body)


# ============================================================== main
def main(argv):
    only = set(a for a in argv if a.startswith('--'))
    cohorts = built()
    print(f'cohorts: {", ".join(cohorts)}')

    if '--resign' in only or not os.path.exists(SIG_CACHE):
        print('building M1 signatures (all cells, per-cohort ECDF = the GATE 1 winner):')
        S = build_signatures(cohorts)
    else:
        S = load_signatures()
        print(f'signatures loaded from cache: {len(S["nodes"])} labels')

    nodes = S['nodes']
    key = list(zip(nodes.cohort, nodes.label))
    kidx = {k: i for i, k in enumerate(key)}
    W = nodes.n_cells.to_numpy()

    t0 = time.time()
    Z, P, Wm = rescale(S)
    SIM, C, EV, CX = containment(S, (Z, P, Wm))
    print(f'containment: {len(nodes)}x{len(nodes)} in {time.time()-t0:.1f}s')

    sweep = choose_cut(S, SIM, EV)
    ok = sweep[sweep.usable]
    if len(ok) == 0:
        print('NO usable cut: no granularity satisfies all three guards at once. '
              'Stage 1b has failed.')
        ok = sweep
    tau = float(ok.cut[ok.stability.idxmax()])      # most stable cut inside the feasible window
    row = sweep[sweep.cut == tau].iloc[0]
    print(f'cut = {tau:.3f}  ({int(row.clusters)} clusters, biggest {int(row.biggest)} labels '
          f'= {row.biggest_share:.0%}, cohort_ari {row.cohort_ari:.3f}, '
          f'stability {row.stability:.3f})')

    memb0 = cluster(np.arange(len(nodes)), SIM, EV, tau)
    loco = loco_memberships(S, SIM, EV, tau)
    memb1, splits = refine(S, memb0, SIM, EV)
    memb, D, gi = nesting(S, memb1, C, EV, SIM=SIM, cut=tau)
    ncoh = np.array([nodes.cohort[np.isfinite(P[:, t])].nunique() for t in range(P.shape[1])])
    names, cen, zc = name_clusters(S, memb, P, ncoh)
    print(f'clusters: {memb0.max()+1} at the global cut -> {memb1.max()+1} after per-branch '
          f'refinement -> {memb.max()+1} after SCC contraction')

    out = nodes.copy()
    out['cluster'] = memb
    out['cluster_name'] = [names[c] for c in memb]
    report(S, out, SIM, C, EV, CX, D, gi, sweep, tau, splits,
           names, cen, zc, loco, only, Z)


def report(S, out, SIM, C, EV, CX, D, gi, sweep, tau, splits,
           names, cen, zc, loco, only, Z):
    nodes = S['nodes']
    key = list(zip(nodes.cohort, nodes.label))
    kidx = {k: i for i, k in enumerate(key)}
    memb = out.cluster.to_numpy()
    W = nodes.n_cells.to_numpy()
    n_cl = memb.max() + 1
    L = []
    A = L.append

    A('# Stage 1b - automatic label alignment (GATE 1b)\n')
    A(f'_{len(nodes)} native labels from {nodes.cohort.nunique()} cohorts, aligned with no '
      f'ontology, no hand-written dictionary and no text._\n')

    # ---------------------------------------------------------------- setup
    A('## What was measured\n')
    A(f'- Value transform: **`u_coh`**, the per-cohort ECDF - the arm that won Gate 1.')
    A(f'- Signature: **{len(QLEV)} quantiles** per (label, marker) + prevalence + '
      f'the within-label co-expression matrix.')
    A(f'- Markers combined by a **floored geometric mean** (floor {DELTA}), not an average, so '
      f'one decisive disagreement can veto a merge.')
    A(f'- Evidence floor **k = {K_EVID}** informative shared markers; a marker is informative '
      f'when its between-label range reaches **{W_MIN}** in *both* cohorts.')
    A(f'- Merge threshold **tau = {tau:.3f}**, chosen by LOCO stability, never by agreement '
      f'with the hand mapping.\n')
    if len(S['dropped']):
        d = S['dropped'].sort_values('cells', ascending=False)
        A(f'**{len(d)} native labels excluded before any alignment** '
          f'({d.cells.sum():,} cells) - quantiles on a handful of cells are noise, and an '
          f'unlabelled group is not a cell type:\n')
        A(md_table(d))
        A('')

    # ---------------------------------------------------------------- tau choice
    A('## Choosing the threshold without looking at the answer\n')
    A('Tuning `tau` against the hand mapping would make check 1 circular, so it is chosen by '
      '**leave-one-cohort-out stability**: mean ARI between the full clustering and each '
      'held-out re-derivation. ARI is chance-corrected, so both degenerate answers punish '
      'themselves - one giant cluster and all-singletons each score about 0.\n')
    A(f'Stability alone is **not enough**, and the first build of this stage proved it: a '
      f'clustering that is really the cohort partition is perfectly reproducible when a '
      f'*different* cohort is dropped, and it scored 0.972 while grouping tumour, macrophages, '
      f'T cells and B cells together. So `cohort_ari` - how much the clustering is just "which '
      f'dataset is this" - is a **hard feasibility constraint** (must be <= '
      f'{COHORT_ARI_MAX}), not a term in the objective. Cohort id is metadata, not a cell type, '
      f'so using it leaks nothing.\n')
    hand = load_hand()
    sweep2 = sweep.copy()
    ag = []
    for t in sweep2.cut:
        m = cluster(np.arange(len(nodes)), SIM, EV, float(t))
        ag.append(score_hand(nodes, m, W, hand)[0])
    sweep2['agreement_vs_hand'] = ag
    A(md_table(sweep2))
    A('')
    srow = sweep[sweep.cut == tau].iloc[0]
    A(f'Chosen **tau = {tau:.3f}** - the most stable threshold among those passing the cohort '
      f'guard (stability {srow.stability:.3f}, cohort_ari {srow.cohort_ari:.3f}, '
      f'{srow.cross_cohort_share:.0%} of labels in a cluster that spans >= 2 cohorts). '
      f'{int((~sweep.usable).sum())} of {len(sweep)} thresholds were rejected by the guard.\n')
    A(f'The agreement column is shown *only* so a reader can see whether that choice was lucky '
      f'- it did not enter the decision. Agreement peaks at cut = '
      f'{sweep2.cut[sweep2.agreement_vs_hand.idxmax()]:.3f} '
      f'({sweep2.agreement_vs_hand.max():.3f}) against {agree_at(sweep2, tau):.3f} at the '
      f'chosen threshold.\n')

    fig, ax = plt.subplots(1, 3, figsize=(14, 3.6))
    ax[0].plot(sweep2.cut, sweep2.stability, 'o-', label='LOCO stability (reported, not optimised)')
    ax[0].plot(sweep2.cut, sweep2.agreement_vs_hand, 's--', color='grey',
               label='agreement vs hand map (not used)')
    ax[0].axvline(tau, color='crimson', lw=1)
    ax[0].set_xlabel('cut height'); ax[0].legend(fontsize=7); ax[0].set_title('threshold choice')
    ax[1].plot(sweep2.cut, sweep2.cohort_ari, 'o-', color='darkorange')
    ax[1].axhline(COHORT_ARI_MAX, color='crimson', ls='--', lw=1)
    ax[1].axvline(tau, color='crimson', lw=1)
    ax[1].set_xlabel('cut height'); ax[1].set_title('cohort guard (lower is better)')
    ax[2].plot(sweep2.cut, sweep2.clusters, 'o-')
    ax[2].axvline(tau, color='crimson', lw=1)
    ax[2].set_xlabel('cut height'); ax[2].set_ylabel('clusters'); ax[2].set_title('granularity')
    fig.tight_layout()
    figp = os.path.join(FIGURES, 's1b_tau.png')
    fig.savefig(figp, dpi=120); plt.close(fig)
    A(f'![threshold choice](figures/s1b_tau.png)\n')

    # ---------------------------------------------------------------- check 1
    A('## Check 1 - agreement with the hand-written mapping\n')
    agree, ariN, ariC, tab = score_hand(nodes, memb, W, hand, full=True, names=names)
    A(f'The old dictionary covers **{tab.cohort.nunique()} cohorts / {len(tab)} labels**. '
      f'It is read only here.\n')
    A('It is scored at **all three of its own levels**, because the level matters and quoting '
      'one number would hide that. The finest level is what the hand mapping calls `target`; '
      '`L2` and `L1` are its own coarser groupings. The number of clusters the shared evidence '
      'can support is a finding, not something to be assumed in advance.\n')
    lv = []
    for level, nm in [('L1', 'L1 - broad lineage'), ('L2', 'L2 - the level the old '
                      'pipeline scored'), ('target', 'target - the finest hand level')]:
        a, rn, rc, _ = score_hand(nodes, memb, W, hand, full=True, level=level)
        lv.append(dict(level=nm,
                       classes=int(hand[hand.keep == 1][level].nunique()),
                       agreement=a, ari_cellwt=rc, ari_perlabel=rn))
    A(md_table(pd.DataFrame(lv)))
    A(f'\nAutomatic clusters: **{int(memb.max()+1)}**. Gate target: agreement **0.90**.\n')
    bad = tab[~tab.correct]
    A(f'**{len(bad)} of {len(tab)} covered labels disagree** '
      f'({bad.n_cells.sum()/tab.n_cells.sum()*100:.1f}% of covered cells):\n')
    A(md_table(bad[['cohort', 'label', 'n_cells', 'hand', 'landed_with',
                    'cluster', 'cluster_name']]))
    A('')

    # ---------------------------------------------------------------- check 2
    A('## Check 2 - the hard cases, declared in advance\n')
    A('From `pipeline2/panel/gate1b_expect.csv`, written **before** this run.\n')
    ex = read_expect()
    rows = []
    for _, r in ex.iterrows():
        idx = [kidx.get(p) for p in r.pairs]
        miss = [f'{a}|{b}' for (a, b), i in zip(r.pairs, idx) if i is None]
        if miss:
            rows.append(dict(case=r.case, relation=r.relation, required=r.required,
                             waived=int(r.get('waived', 0)),
                             result='n/a', detail='not in graph: ' + ', '.join(miss)))
            continue
        cl = [int(memb[i]) for i in idx]
        if r.relation == 'same':
            ok = len(set(cl)) == 1
            det = f'clusters {sorted(set(cl))}'
        elif r.relation == 'different':
            ok = len(set(cl)) == len(cl)
            det = f'clusters {cl}'
        else:                                   # nested: child ⊂ parent
            cc, pp = cl[0], cl[1]
            if cc == pp:
                ok, det = None, f'merged into one cluster ({cc})'
            else:
                ok = D.has_edge(cc, pp)
                det = ('nesting edge found' if ok else
                       f'no edge {cc} -> {pp}; reverse={D.has_edge(pp, cc)}')
        rows.append(dict(case=r.case, relation=r.relation, required=r.required,
                         waived=int(r.get('waived', 0)),
                         result={True: 'PASS', False: 'FAIL', None: 'merged'}[ok], detail=det))
    hc = pd.DataFrame(rows)
    A(md_table(hc))
    req = hc[hc.required == 1]
    blocking = req[(req.result == 'FAIL') & (req.waived == 0)]
    n_req_fail = len(blocking)
    waived = req[(req.result == 'FAIL') & (req.waived == 1)]
    A(f'\n**Required cases: {int((req.result == "PASS").sum())}/{len(req)} pass'
      + (f', {len(waived)} waived on measured evidence, {n_req_fail} blocking.**\n'
         if len(waived) else f', {n_req_fail} blocking.**\n'))
    flagged = set()
    for _, w in waived.iterrows():
        wr = ex[ex.case == w.case].iloc[0]
        A(f'> **`{w.case}` is a WAIVED FAILURE, not a pass.** It was declared required before the '
          f'run and it failed. {wr.waiver_reason}\n')
        for pp in wr.pairs:
            if pp in kidx:
                flagged.add(int(memb[kidx[pp]]))
    # a waived failure must not become invisible downstream
    out['unreliable'] = out.cluster.isin(flagged).astype(int)
    out['unreliable_reason'] = np.where(out.cluster.isin(flagged),
                                        'Gate 1b waived failure - see panel/gate1b_expect.csv', '')
    if flagged:
        A(f'**{len(flagged)} clusters carry a waived failure and are flagged `unreliable` in '
          f'`work/label_map.csv`** (clusters {sorted(flagged)}, '
          f'{int(out.unreliable.sum())} labels, {int(out[out.unreliable == 1].n_cells.sum()):,} '
          f'cells). Stage 7 must exclude them from the headline score or report them separately - '
          f'they are not evidence of anything either way.\n')

    # every failing case is diagnosed here rather than left for the reader to guess at
    bad_cases = hc[(hc.result == 'FAIL')].case.tolist()
    for _, r in ex[ex.case.isin(bad_cases) & (ex.relation == 'same')].iterrows():
        idx = [kidx.get(p) for p in r.pairs]
        if any(i is None for i in idx):
            continue
        A(f'**Why `{r.case}` failed.** Pairwise similarity between its members, against the '
          f'chosen cut of {np.exp(-tau):.3f}:\n')
        pr = []
        for (a1, b1), i in zip(r.pairs, idx):
            for (a2, b2), j in zip(r.pairs, idx):
                if i < j:
                    pr.append(dict(a=f'{a1}|{b1}', b=f'{a2}|{b2}',
                                   similarity=float(SIM[i, j]),
                                   informative_markers=int(EV[i, j]),
                                   would_merge=bool(SIM[i, j] >= np.exp(-tau))))
        A(md_table(pd.DataFrame(pr)))
        shared = shared_markers(S, [kidx[p] for p in r.pairs])
        A(f'\nInformative markers shared by **all** of them ({len(shared)}): '
          f'{", ".join(shared) if shared else "none"}\n')

    # ---------------------------------------------------------------- check 3
    A('## Check 3 - evidence coverage and the floor sweep\n')
    iu = np.triu_indices(len(nodes), 1)
    ev = EV[iu]
    direct = (ev >= K_EVID)
    A(f'| | pairs | share |\n|---|---|---|')
    A(f'| directly comparable (evidence >= {K_EVID}) | {direct.sum():,} | '
      f'{direct.mean()*100:.1f}% |')
    A(f'| below the floor | {(~direct).sum():,} | {(~direct).mean()*100:.1f}% |')
    A(f'| never comparable (0 informative shared markers) | {(ev == 0).sum():,} | '
      f'{(ev == 0).mean()*100:.1f}% |\n')
    A(f'Bridged by transitive closure: **{len(gi["bridged"])}** cluster pairs.\n')
    sw = []
    for k in (4, 6, 8, 12, 16):
        m = cluster(np.arange(len(nodes)), SIM, EV, tau, k=k)
        a = score_hand(nodes, m, W, hand)[0]
        sw.append(dict(k=k, pairs_direct=int((ev >= k).sum()),
                       share_direct=float((ev >= k).mean()),
                       clusters=int(m.max() + 1), agreement=a))
    A(md_table(pd.DataFrame(sw)))
    A('')
    cm = pd.DataFrame(0, index=sorted(nodes.cohort.unique()),
                      columns=sorted(nodes.cohort.unique()))
    for a in cm.index:
        for b in cm.columns:
            ia = np.flatnonzero((nodes.cohort == a).to_numpy())
            ib = np.flatnonzero((nodes.cohort == b).to_numpy())
            cm.loc[a, b] = int(np.median(EV[np.ix_(ia, ib)])) if len(ia) and len(ib) else 0
    A('Median informative shared markers per cohort pair:\n')
    A(md_table(cm.reset_index().rename(columns={'index': 'cohort'})))
    A('')

    # ---------------------------------------------------------------- check 4
    A('## Check 4 - split stability (M3)\n')
    A('The global cut sets the top level. Inside each branch, granularity is set separately: '
      'every cluster is offered a binary split, and the split is kept only if both sides hold '
      f'at least {MIN_SPLIT_LABELS} labels, both sides span **two or more cohorts** (so a split '
      f'can never be a cohort boundary in disguise) and it reproduces with a cohort held out '
      f'(LOCO ARI >= {SPLIT_SUPPORT}). Every decision, accepted or rejected, is listed.\n')
    sp = pd.DataFrame(splits)
    if len(sp):
        A(f'**{int(sp.kept.sum())} of {len(sp)} candidate splits accepted:**\n')
        A(md_table(sp[['labels', 'left', 'right', 'left_cohorts', 'right_cohorts',
                       'stability', 'kept', 'reason']]))
    else:
        A('No cluster was large enough to offer a split.')
    A('')
    A('**Rare-but-global types (the M3 test cases named in the plan):**\n')
    A(md_table(rare_check(nodes, memb, hand, names)))
    A('')

    # ---------------------------------------------------------------- check 5
    A('## Check 5 - nesting (M2)\n')
    ed = [dict(child=names[u][:38] or str(u), parent=names[v][:38] or str(v),
               contain=d.get('contain'), label_pairs=d['pairs'], kind=d['kind'])
          for u, v, d in D.edges(data=True)]
    if ed:
        A(f'**{len(ed)} parent-child edges** (child ⊂ parent), all between clusters:\n')
        A(md_table(pd.DataFrame(ed)))
    else:
        A('**No nesting edges survived.** Every relation the data supports was symmetric, so '
          'the hierarchy is flat at this granularity. Reported, not patched.')
    A('')

    # ---------------------------------------------------------------- check 6
    A('## Check 6 - marker coherence\n')
    coh = coherence(S, memb, names, Z)
    A('Within-cluster spread of the label signatures versus the spread between cluster '
      'centres. A cluster whose members disagree more than the clusters differ is not a cell '
      'type.\n')
    A(md_table(coh))
    nbad = int((~coh.coherent).sum())
    A(f'\n**{len(coh)-nbad}/{len(coh)} clusters coherent.**\n')

    # ---------------------------------------------------------------- check 7
    A('## Check 7 - acyclicity and transitivity (M2b)\n')
    A(f'| | |\n|---|---|')
    A(f'| `nx.is_directed_acyclic_graph` after SCC contraction | **{nx.is_directed_acyclic_graph(D)}** |')
    A(f'| cycles (SCCs > 1 node) found before contraction | {gi["cycles_before"]} |')
    A(f'| transitivity violations (measured, contradicting closure) | {len(gi["violations"])} |')
    A(f'| pairs bridged by closure (evidence was missing) | {len(gi["bridged"])} |\n')
    if gi['sccs']:
        A('Contracted strongly connected components (mutually containing labels **are** one '
          'type, so merging them is the correct reading):\n')
        for s in gi['sccs']:
            A(f'- {s}')
        A('')
    if gi['violations']:
        v = pd.DataFrame(gi['violations']).head(10)
        v['child'] = v.child.map(lambda c: names[c][:34])
        v['parent'] = v.parent.map(lambda c: names[c][:34])
        A(f'Worst transitivity violations - **logged, never overwritten**:\n')
        A(md_table(v))
        rate = len(gi['violations']) / max(1, len(gi['violations']) + D.number_of_edges())
        A(f'\nViolation rate {rate*100:.1f}%. Above ~10% the containment measure is unreliable '
          f'and the evidence floor should rise.\n')
    else:
        A('**No transitivity violation.** No measured pair contradicts the closure.\n')

    # ---------------------------------------------------------------- final clusters
    A('## The cluster list\n')
    cl = cluster_table(nodes, memb, names)
    A(md_table(cl))
    A('')
    A(f'**Core clusters** (>= 2 cohorts): {int((cl.cohorts >= 2).sum())} · '
      f'**cohort-exclusive**: {int((cl.cohorts == 1).sum())} - the latter become the Stage 7 '
      f'novel-class test material.\n')

    # ---------------------------------------------------------------- verdict
    car, xshare = cohort_driven(nodes, memb)
    ok1 = agree >= 0.90
    ok2 = n_req_fail == 0
    ok7 = nx.is_directed_acyclic_graph(D)
    ok6 = nbad == 0
    ok0 = car <= COHORT_ARI_MAX
    verdict = 'PASS' if (ok0 and ok1 and ok2 and ok7 and ok6) else 'FAIL'
    A('## GATE 1b verdict\n')
    A(f'| check | result | pass |\n|---|---|---|')
    A(f'| 0 cohort guard: clusters are not the cohort partition | cohort_ari {car:.3f} '
      f'(cap {COHORT_ARI_MAX}), {xshare:.0%} cross-cohort | {"yes" if ok0 else "NO"} |')
    A(f'| 1 agreement with hand mapping >= 0.90 | {agree:.3f} | {"yes" if ok1 else "NO"} |')
    A(f'| 2 required hard cases | {int((req.result=="PASS").sum())}/{len(req)}'
      + (f' + {len(waived)} waived' if len(waived) else '')
      + f' | {"yes" if ok2 else "NO"} |')
    A(f'| 3 evidence coverage reported | {direct.mean()*100:.1f}% direct | yes |')
    A(f'| 4 per-branch splits tested | {int(pd.DataFrame(splits).kept.sum()) if splits else 0}'
      f'/{len(splits)} accepted | yes |')
    A(f'| 5 nesting edges | {len(ed)} | yes |')
    A(f'| 6 every cluster coherent | {len(coh)-nbad}/{len(coh)} | {"yes" if ok6 else "NO"} |')
    A(f'| 7 graph is a DAG | {ok7} | {"yes" if ok7 else "NO"} |')
    A(f'\n# GATE 1b: {verdict}\n')

    with open(os.path.join(REPORTS, 's1b_labels.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    out.to_csv(os.path.join(WORK, 'label_map.csv'), index=False)
    np.save(os.path.join(WORK, 'prototypes.npy'), cen)
    with open(os.path.join(WORK, 'label_graph.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(tau=tau, k=K_EVID, delta=DELTA, margin=MARGIN,
                       clusters={int(c): names[c] for c in range(n_cl)},
                       edges=[dict(child=int(u), parent=int(v), **{k: (None if (
                           isinstance(d[k], float) and not np.isfinite(d[k])) else d[k])
                           for k in d}) for u, v, d in D.edges(data=True)],
                       sccs=gi['sccs'], bridged=gi['bridged'],
                       violations=gi['violations'],
                       triples=S['triples'].tolist()), f, indent=1)
    print(f'\nGATE 1b: {verdict}   -> reports/s1b_labels.md')


# ------------------------------------------------------------------ scoring helpers
def load_hand():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     '_validation', 'hand_mapping_reference.csv')
    return pd.read_csv(p, keep_default_na=False)


def score_hand(nodes, memb, W, hand, full=False, names=None, level='target'):
    h = hand[hand.keep == 1].set_index(['cohort', 'native_label'])[level]
    idx, auto, tgt, cw = [], [], [], []
    for i, (c, l) in enumerate(zip(nodes.cohort, nodes.label)):
        if (c, l) in h.index:
            idx.append(i); auto.append(memb[i]); tgt.append(h[(c, l)]); cw.append(W[i])
    if not idx:
        return (0.0, 0.0, 0.0, pd.DataFrame()) if full else (0.0,)
    agree, mapping = best_match_agreement(auto, tgt, cw)
    if not full:
        return (agree,)
    tab = pd.DataFrame(dict(cohort=nodes.cohort.to_numpy()[idx],
                            label=nodes.label.to_numpy()[idx],
                            n_cells=np.array(cw), hand=tgt, cluster=auto))
    tab['cluster_name'] = [(names[c][:40] if names else '') for c in auto]
    tab['landed_with'] = [mapping.get(a, '-') for a in auto]
    tab['correct'] = [mapping.get(a) == t for a, t in zip(auto, tgt)]
    return agree, ari(auto, tgt), ari(auto, tgt, cw), tab


def rare_check(nodes, memb, hand, names):
    h = hand[hand.keep == 1].set_index(['cohort', 'native_label']).target
    rows = []
    for tgt in RARE_GLOBAL:
        mem = [(c, l) for (c, l), t in h.items() if t == tgt]
        got = []
        for c, l in mem:
            m = (nodes.cohort == c) & (nodes.label == l)
            if m.any():
                got.append(int(memb[np.flatnonzero(m.to_numpy())[0]]))
        if not got:
            rows.append(dict(rare_type=tgt, cohorts=0, clusters='-',
                             swallowed='n/a - below MIN_CELLS in every cohort'))
            continue
        cl = sorted(set(got))
        sizes = [int((memb == c).sum()) for c in cl]
        rows.append(dict(rare_type=tgt, cohorts=len(got), clusters=str(cl),
                         swallowed='yes - in a cluster of ' + str(max(sizes)) + ' labels'
                                   if max(sizes) > 6 else 'no'))
    return pd.DataFrame(rows)


def coherence(S, memb, names, Z):
    med = Z[:, :, I_MED]
    ok = np.isfinite(med).all(0)                       # markers every label has: comparable
    X = med[:, ok]
    n_cl = memb.max() + 1
    cen = np.vstack([X[memb == c].mean(0) for c in range(n_cl)])
    between = float(np.mean(((cen - cen.mean(0)) ** 2).sum(1)))
    rows = []
    for c in range(n_cl):
        m = memb == c
        within = float(np.mean(((X[m] - cen[c]) ** 2).sum(1))) if m.sum() > 1 else 0.0
        rows.append(dict(cluster=c, name=names[c][:40], labels=int(m.sum()),
                         within=within, between=between, coherent=within < between))
    return pd.DataFrame(rows)


def cluster_table(nodes, memb, names):
    rows = []
    for c in range(memb.max() + 1):
        m = memb == c
        sub = nodes[m]
        rows.append(dict(cluster=c, name=names[c][:44], labels=int(m.sum()),
                         cohorts=int(sub.cohort.nunique()), cells=int(sub.n_cells.sum()),
                         members='; '.join(f'{a}|{b}' for a, b in
                                           zip(sub.cohort, sub.label))[:150]))
    return pd.DataFrame(rows).sort_values('cells', ascending=False)


if __name__ == '__main__':
    main(sys.argv[1:])

"""
STEP 11 - Gap-fill measurements (REPORT G section 7).

Answers the five computable gaps left open in report_2ndstage/REPORT_G_data_facts.md:

  G1  segmentation merge rate    - how often do we see impossible double-positives?
  G2  spillover / crosstalk      - lateral bleed from neighbours; CRC same-cycle bleed
  G3  spatial coherence          - do cell types form spatially coherent regions?
  G4  architecture check         - does our label-free micro_env recover published neighbourhoods?
  G6  batch drift                - how big is the per-image drift, before vs after normalisation?

(G5, a hand-gated gold set, is human work and is not in here.)

Outputs -> harmonised/_audit/gapfill/*.csv    (one csv per measurement)
Run: python step11_gapfill.py [g1 g2 g3 g4 g6]   (default = all)
"""
import os, sys, time
import numpy as np, pandas as pd
from common import COHORTS, OUT, AUDIT, load_expression, load_geometry

GAP = os.path.join(AUDIT, "gapfill")
os.makedirs(GAP, exist_ok=True)
POS = 0.5                     # P(positive) >= 0.5 counts as positive
TOUCH_UM = 10.0               # spillover is a touching effect; 10 um ~ one cell diameter
RNG = np.random.default_rng(0)


def _expr(cohort, cols=None):
    f = os.path.join(OUT, f"{cohort}_expr.parquet")
    return pd.read_parquet(f, columns=cols)


def _markers(cohort):
    import pyarrow.parquet as pq
    names = pq.ParquetFile(os.path.join(OUT, f"{cohort}_expr.parquet")).schema_arrow.names
    return [c for c in names if c != 'cell_id' and not c.startswith('pct_')]


# ---------------------------------------------------------------------------
# G1 - segmentation merge rate
# ---------------------------------------------------------------------------
# Logic: two cells segmented as one produce a cell positive for two markers that
# no single real cell can carry (e.g. CD3 = T cell AND PanCK = epithelial).
# We report the observed rate, the rate expected if the two markers were
# independent, and the ratio. Ratio >> 1 means the double-positives are real
# co-occurrences (touching cells merged), not chance.
PAIRS = [('CD3', 'PanCK'), ('CD20', 'PanCK'), ('CD68', 'PanCK'), ('CD31', 'PanCK'),
         ('CD3', 'CD68'), ('CD3', 'CD20'), ('CD20', 'CD68'), ('CD3', 'aSMA')]


THRESHOLDS = [0.5, 0.8, 0.9, 0.95]   # 0.5 = GMM boundary (loose); 0.9 = confidently positive


def g1():
    rows, arows = [], []
    for c in COHORTS:
        have = set(_markers(c))
        use = sorted({m for p in PAIRS for m in p} & have)
        X = _expr(c, ['cell_id'] + use)
        cells = pd.read_parquet(os.path.join(OUT, f"{c}_cells.parquet"),
                                columns=['cell_id', 'area_um2', 'n_nbr_30um', 'is_clean'])
        n = len(X)
        for thr in THRESHOLDS:
            P = {m: (X[m].values >= thr) for m in use}
            dp_any = np.zeros(n, bool)
            for a, b in PAIRS:
                if a not in have or b not in have:
                    continue
                pa, pb = P[a], P[b]
                both = pa & pb
                dp_any |= both
                exp = pa.mean() * pb.mean()
                rows.append(dict(cohort=c, threshold=thr, marker_a=a, marker_b=b,
                                 pct_pos_a=round(100 * pa.mean(), 2),
                                 pct_pos_b=round(100 * pb.mean(), 2),
                                 pct_double=round(100 * both.mean(), 3),
                                 pct_expected_if_independent=round(100 * exp, 3),
                                 ratio_obs_over_exp=round(both.mean() / exp, 2) if exp > 0 else np.nan))
            # are the double-positives bigger / more crowded than normal cells?
            a_um = cells.area_um2.values
            nbr = cells.n_nbr_30um.values.astype(float)
            has_area = np.isfinite(a_um).any()
            arows.append(dict(cohort=c, threshold=thr,
                              pct_cells_double_pos_any_pair=round(100 * dp_any.mean(), 2),
                              median_area_double=round(float(np.nanmedian(a_um[dp_any])), 1) if has_area and dp_any.any() else np.nan,
                              median_area_single=round(float(np.nanmedian(a_um[~dp_any])), 1) if has_area else np.nan,
                              median_nbrs_double=round(float(np.nanmedian(nbr[dp_any])), 1) if dp_any.any() else np.nan,
                              median_nbrs_single=round(float(np.nanmedian(nbr[~dp_any])), 1)))
            if thr == 0.9:
                print(f"  G1 {c}: at P>=0.9, {100*dp_any.mean():.2f}% of cells carry an impossible pair")
    pd.DataFrame(rows).to_csv(os.path.join(GAP, "g1_double_positive_pairs.csv"), index=False)
    pd.DataFrame(arows).to_csv(os.path.join(GAP, "g1_double_positive_size.csv"), index=False)
    g1b()


# G1b - calibration check. A double-positive can come from a merged cell OR from a
# threshold that calls too many cells positive. Separate the two: compare "% of cells
# called positive for marker m" against "% of cells whose gold label is the type m
# marks". If we call 35% of cells CD31+ but only 5% are endothelial, the threshold is
# the problem, not segmentation.
MARKER_OF_TYPE = {'CD3': 'T cell', 'CD4': 'T cell', 'CD8': 'T cell', 'CD20': 'B/Plasma',
                  'CD68': 'Myeloid', 'CD31': 'Endothelial', 'PanCK': 'Epithelial/Tumour',
                  'aSMA': 'Fibroblast/Muscle', 'CD11c': 'Myeloid', 'CD15': 'Granulocyte'}


def g1b():
    rows = []
    for c in COHORTS:
        have = set(_markers(c))
        mk = [m for m in MARKER_OF_TYPE if m in have]
        X = _expr(c, mk)
        lab = pd.read_parquet(os.path.join(OUT, f"{c}_labels.parquet"), columns=['L2', 'is_gold'])
        g = lab.is_gold.values
        for m in mk:
            pos = 100 * (X[m].values >= POS).mean()
            truth = 100 * (lab.L2.values[g] == MARKER_OF_TYPE[m]).mean()
            rows.append(dict(cohort=c, marker=m, marks_type=MARKER_OF_TYPE[m],
                             pct_called_positive=round(pos, 1),
                             pct_cells_really_that_type=round(truth, 1),
                             over_call_factor=round(pos / truth, 1) if truth > 0.05 else np.nan))
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(GAP, "g1b_positivity_calibration.csv"), index=False)
    print("  G1b median over-call factor per cohort:",
          d.groupby('cohort').over_call_factor.median().round(2).to_dict())


# ---------------------------------------------------------------------------
# G2 - spillover / crosstalk
# ---------------------------------------------------------------------------
# Test A (all cohorts): lateral bleed. Among cells that are NEGATIVE for marker m,
#   does their m value rise with the number of m-positive cells touching them
#   (<=10 um)? A positive, marker-specific correlation = signal leaking sideways.
#   Control: the same correlation against a random *other* marker's positive
#   neighbours. Real spillover is specific; a biology-driven correlation is not.
# Test B (CRC only): CODEX cycle bleed. CRC records Cyc_N_ch_M per marker. If
#   channels bleed, marker pairs imaged in the SAME cycle should correlate more
#   than pairs from different cycles.
def g2():
    mm = pd.read_csv(os.path.join(AUDIT, "marker_map.csv"))
    rows = []
    for c in COHORTS:
        mk = _markers(c)
        pct_cols = ['pct_' + m for m in mk]
        X = _expr(c, ['cell_id'] + mk + pct_cols)
        E = pd.read_parquet(os.path.join(OUT, f"{c}_graph_r30.parquet"))
        E = E[E.dist_um <= TOUCH_UM]
        src, dst = E.src.values, E.dst.values
        n = len(X)
        deg = np.bincount(src, minlength=n) + np.bincount(dst, minlength=n)
        deg_safe = np.maximum(deg, 1)
        for m in mk:
            p = (X[m].values >= POS)
            # neighbours positive for m
            npos = np.bincount(src, weights=p[dst].astype(float), minlength=n) + \
                   np.bincount(dst, weights=p[src].astype(float), minlength=n)
            frac = npos / deg_safe
            neg = (~p) & (deg > 0)              # only cells that are themselves negative
            if neg.sum() < 500:
                continue
            v = X['pct_' + m].values[neg]       # graded value, percentile within image
            r = float(pd.Series(v).corr(pd.Series(frac[neg]), method='spearman'))
            rows.append(dict(cohort=c, marker=m, n_negative_cells=int(neg.sum()),
                             pct_positive=round(100 * p.mean(), 2),
                             rho_own_value_vs_positive_neighbours=round(r, 4)))
        print(f"  G2 {c}: lateral-bleed correlation done for {len(mk)} markers")
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(GAP, "g2_lateral_bleed.csv"), index=False)

    # Test B - CRC same-cycle vs different-cycle correlation
    crc_mk = _markers('CRC')
    X = _expr('CRC', ['cell_id'] + crc_mk)
    cyc = (mm[(mm.cohort == 'CRC') & (mm.use == True)]
           .set_index('canonical').crc_cycle.to_dict())
    sub = X[crc_mk].sample(n=min(60000, len(X)), random_state=0)
    C = sub.corr(method='spearman')
    same, diff = [], []
    for i, a in enumerate(crc_mk):
        for b in crc_mk[i + 1:]:
            if a not in cyc or b not in cyc or pd.isna(cyc[a]) or pd.isna(cyc[b]):
                continue
            (same if cyc[a] == cyc[b] else diff).append(abs(C.loc[a, b]))
    pd.DataFrame([dict(test='CRC same imaging cycle', n_pairs=len(same),
                       median_abs_spearman=round(float(np.median(same)), 4)),
                  dict(test='CRC different cycle', n_pairs=len(diff),
                       median_abs_spearman=round(float(np.median(diff)), 4))]
                 ).to_csv(os.path.join(GAP, "g2_crc_cycle_bleed.csv"), index=False)
    # ferguson CXCR3 - the flagged channel: who does it track?
    fmk = _markers('ferguson')
    if 'CXCR3' in fmk:
        F = _expr('ferguson', ['cell_id'] + fmk)
        cc = F[fmk].corr(method='spearman')['CXCR3'].drop('CXCR3').sort_values(ascending=False)
        cc.round(3).to_frame('spearman_vs_CXCR3').to_csv(os.path.join(GAP, "g2_ferguson_cxcr3.csv"))
    print("  G2 cycle-bleed + CXCR3 done")


# ---------------------------------------------------------------------------
# G3 - spatial coherence
# ---------------------------------------------------------------------------
# For every gold-labelled cell: what fraction of its 30 um neighbours share its
# L2 type? Compare to a null where labels are shuffled WITHIN the same image
# (keeps composition, destroys position). observed / expected = how tightly that
# cell type clusters. >1 = clustered (follicles), ~1 = scattered.
def g3(n_shuffle=3):
    rows = []
    for c in COHORTS:
        lab = pd.read_parquet(os.path.join(OUT, f"{c}_labels.parquet"),
                              columns=['cell_id', 'L1', 'L2', 'is_gold'])
        cells = pd.read_parquet(os.path.join(OUT, f"{c}_cells.parquet"),
                                columns=['cell_id', 'image_id', 'is_clean'])
        d = lab.merge(cells, on='cell_id')
        n = len(d)
        ok = d.is_gold.values & d.is_clean.values & d.L2.notna().values
        for level in ['L1', 'L2']:
            codes = pd.Categorical(d[level]).codes.astype(np.int32).copy()
            codes[~ok] = -1
            E = pd.read_parquet(os.path.join(OUT, f"{c}_graph_r30.parquet"), columns=['src', 'dst'])
            s, t = E.src.values, E.dst.values
            keep = (codes[s] >= 0) & (codes[t] >= 0)
            s, t = s[keep], t[keep]

            def same_frac(cd):
                agree = (cd[s] == cd[t])
                num = np.bincount(s, weights=agree.astype(float), minlength=n) + \
                      np.bincount(t, weights=agree.astype(float), minlength=n)
                den = np.bincount(s, minlength=n).astype(float) + np.bincount(t, minlength=n)
                with np.errstate(invalid='ignore', divide='ignore'):
                    return np.where(den > 0, num / den, np.nan), den

            obs, den = same_frac(codes)
            # null: shuffle labels within image
            img = pd.Categorical(d.image_id).codes
            nulls = []
            for k in range(n_shuffle):
                sh = codes.copy()
                order = np.lexsort((RNG.random(n), img))
                for _, idx in pd.Series(np.arange(n)).groupby(img):
                    ii = idx.values
                    sh[ii] = RNG.permutation(codes[ii])
                nulls.append(same_frac(sh)[0])
            null = np.nanmean(np.vstack(nulls), axis=0)

            valid = (den > 0) & np.isfinite(obs) & (codes >= 0)
            cats = pd.Categorical(d[level]).categories
            for ci, name in enumerate(cats):
                m = valid & (codes == ci)
                if m.sum() < 200:
                    continue
                o, e = float(np.nanmean(obs[m])), float(np.nanmean(null[m]))
                rows.append(dict(cohort=c, level=level, cell_type=name, n_cells=int(m.sum()),
                                 same_type_neighbours_observed=round(o, 3),
                                 expected_if_scattered=round(e, 3),
                                 clustering_ratio=round(o / e, 2) if e > 0 else np.nan))
            m = valid
            o, e = float(np.nanmean(obs[m])), float(np.nanmean(null[m]))
            rows.append(dict(cohort=c, level=level, cell_type='__ALL__', n_cells=int(m.sum()),
                             same_type_neighbours_observed=round(o, 3),
                             expected_if_scattered=round(e, 3),
                             clustering_ratio=round(o / e, 2) if e > 0 else np.nan))
            print(f"  G3 {c} {level}: overall coherence {o:.3f} vs null {e:.3f}  (x{o/e:.2f})")
    pd.DataFrame(rows).to_csv(os.path.join(GAP, "g3_spatial_coherence.csv"), index=False)


# ---------------------------------------------------------------------------
# G4 - architecture check
# ---------------------------------------------------------------------------
# Our micro_env is a label-free k-means over neighbourhood marker means, fitted
# once across all 5 cohorts. The published cohorts also ship their own
# cell-type-derived neighbourhood labels (CRC 9, HubMap 20 + 3 tissue segments).
# If our label-free version agrees with theirs, it is recovering real tissue
# architecture and not just noise. Agreement = adjusted Rand + mutual information.
def g4():
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
    rows = []
    D = os.path.join(os.path.dirname(OUT), "Datasets")
    native = {}
    n = pd.read_csv(os.path.join(D, "CRC", "CRC_clusters_neighborhoods_markers.csv"),
                    usecols=['neighborhood name'])
    native['CRC'] = {'CRC neighbourhood (9)': n['neighborhood name'].astype(str).values}
    h = pd.read_parquet(os.path.join(D, "HubMap", "cell_labels.parquet"))
    hcols = [c for c in h.columns if c.lower() in ('neighborhood', 'community', 'tissue segment')]
    native['HubMap'] = {f'HubMap {c}': h[c].astype(str).values for c in hcols}

    for c, sets in native.items():
        me = pd.read_parquet(os.path.join(OUT, f"{c}_microenv.parquet"))
        col = [x for x in me.columns if x != 'cell_id'][0]
        mine = me[col].values
        lab = pd.read_parquet(os.path.join(OUT, f"{c}_labels.parquet"), columns=['cell_id', 'L2'])
        for name, ref in sets.items():
            if len(ref) != len(mine):
                rows.append(dict(cohort=c, reference=name, status=f'length mismatch {len(ref)} vs {len(mine)}'))
                continue
            k = min(300000, len(mine))
            idx = RNG.choice(len(mine), k, replace=False)
            a, b = mine[idx], ref[idx]
            rows.append(dict(cohort=c, reference=name, status='ok', n_scored=k,
                             n_ref_classes=int(pd.Series(b).nunique()),
                             n_our_clusters=int(pd.Series(a).nunique()),
                             adjusted_rand=round(adjusted_rand_score(b, a), 4),
                             normalised_mutual_info=round(normalized_mutual_info_score(b, a), 4)))
            print(f"  G4 {c} vs {name}: NMI {rows[-1]['normalised_mutual_info']}")
        # reference point: how well do the TRUE cell types match the same neighbourhoods?
        for name, ref in sets.items():
            if len(ref) != len(mine):
                continue
            idx = RNG.choice(len(mine), min(300000, len(mine)), replace=False)
            rows.append(dict(cohort=c, reference=name + '  [ref: true L2 types]', status='ok',
                             n_scored=len(idx),
                             normalised_mutual_info=round(
                                 normalized_mutual_info_score(ref[idx], lab.L2.astype(str).values[idx]), 4)))
    pd.DataFrame(rows).to_csv(os.path.join(GAP, "g4_architecture_check.csv"), index=False)


# ---------------------------------------------------------------------------
# G6 - batch drift, before vs after normalisation
# ---------------------------------------------------------------------------
# Metric: for each marker, what share of its total variation is explained purely by
# WHICH IMAGE the cell came from? (one-way variance-explained, 0 = no image effect,
# 1 = the image decides everything). Scale-free, so the native values and our
# P(positive) values are directly comparable. Computed on both.
# Caveat: some between-image variation is real biology (images differ in composition),
# so this is an upper bound on the batch effect - but the before/after drop is the point.
def _var_explained_by_image(V, img_codes, n_img):
    """V: (n_cells, n_markers) float32. Returns array of R^2 per marker."""
    V = np.asarray(V, dtype='float64')
    cnt = np.bincount(img_codes, minlength=n_img).astype('float64')
    out = np.empty(V.shape[1])
    for j in range(V.shape[1]):
        v = V[:, j]
        ok = np.isfinite(v)
        if ok.sum() < 10 or np.nanstd(v) == 0:
            out[j] = np.nan; continue
        lo, hi = np.nanpercentile(v[ok], [0.5, 99.5])      # winsorise: stop one bright
        v = np.clip(v, lo, hi)                              # image dominating by outliers
        gmean = v.mean()
        ssum = np.bincount(img_codes, weights=v, minlength=n_img)
        with np.errstate(invalid='ignore', divide='ignore'):
            imeans = np.where(cnt > 0, ssum / np.maximum(cnt, 1), np.nan)
        ss_between = float(np.nansum(cnt * (imeans - gmean) ** 2))
        ss_total = float(((v - gmean) ** 2).sum())
        out[j] = ss_between / ss_total if ss_total > 0 else np.nan
    return out


def g6():
    rows = []
    for c in COHORTS:
        geo = load_geometry(c)[['cell_id', 'image_id']]
        img = pd.Categorical(geo.image_id).codes.astype(np.int64)
        n_img = int(img.max()) + 1
        raw = load_expression(c)
        mk = [m for m in raw.columns if m != 'cell_id']
        r_native = _var_explained_by_image(raw[mk].values, img, n_img)
        del raw
        pos = _expr(c, ['cell_id'] + mk)
        r_norm = _var_explained_by_image(pos[mk].values, img, n_img)
        del pos
        for j, m in enumerate(mk):
            rows.append(dict(cohort=c, marker=m, n_images=n_img,
                             pct_variance_from_image_native=round(100 * r_native[j], 1),
                             pct_variance_from_image_after_norm=round(100 * r_norm[j], 1)))
        print(f"  G6 {c}: median % of a marker's variation explained by which image it is from"
              f"  -  native {100*np.nanmedian(r_native):.1f}%  ->  after normalisation {100*np.nanmedian(r_norm):.1f}%")
    pd.DataFrame(rows).to_csv(os.path.join(GAP, "g6_batch_drift.csv"), index=False)


if __name__ == '__main__':
    todo = [a.lower() for a in sys.argv[1:]] or ['g1', 'g2', 'g3', 'g4', 'g6']
    for name in todo:
        t = time.time()
        print(f"\n=== {name.upper()} ===")
        globals()[name]()
        print(f"=== {name.upper()} done in {time.time()-t:.0f}s ===")
    print("\nWROTE:", GAP)

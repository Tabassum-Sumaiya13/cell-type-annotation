4.4 Stage 1 — Continuous value harmonisation ✅ GATE 1: PASS, winner V3
Purpose. Put CRC's raw fluorescence, UPMC's arcsinh, Keren's z-scores and Sorin's uint8 onto one comparable footing without hard bins.

Input. work/raw/*.parquet + work/marker_registry.csv.
Output. work/values/{cohort}.parquet (stratified 40k), work/values/{cohort}_rand.parquet (unstratified), work/values/{cohort}_slidestats.parquet, work/s1_folds.pt, reports/s1_normalisation.md, pipeline2/nn/marker_encoder.py.

Value-table schema (Stage 1, 9 core markers only):
cell_id, cohort, image_id, patient_id, native_label + u_img::<triple> × 9 + u_coh::<triple> × 9 + raw::<triple> × 9 = 32 columns.

Core idea — rank before the MLP. A per-group percentile rank (empirical CDF) is monotone, continuous, has no bins, and puts every cohort on the same footing in one step. LayerNorm only shifts and scales — it cannot undo a nonlinearity.

Implementation notes that matter:

method='average' (mid-rank) splits ties down the middle. Critical because Sorin is uint8, so ties are everywhere and a left- or right-rank would bias every quantised marker.
References (cohort ECDF, per-image ECDF, slide statistics) are computed on every cell; only the written table is subsampled. The Kaggle run sets n_sub=None and takes the identical code path.
Stratified subsample is round-robin over (patient × native label), so a rare label is kept whole and a huge stratum cannot swamp the draw.
The six-arm bake-off (a ladder, so each comparison isolates one decision):

arm	channel 1	channel 2	FiLM
V1	u_img	—	—
V3	u_coh	—	—
V2a	u_coh	—	scalar, 4 params/marker
V2b	u_coh	—	MLP over the whole slide-stats vector
V1+V3	u_img	u_coh	—
V2a+V1	u_coh	u_img	scalar
comparison	question
V1 vs V3	is per-image grouping harmful on its own?
V3 vs V2a/V2b	is a learned slide correction worth anything at all?
V2a vs V2b	is the extra capacity worth anything?
V3 vs V1+V3	does the image rank add to the cohort rank rather than replace it?
V1+V3 vs V2a+V1	does FiLM beat simply handing over the image rank?
Check 4 — the decision. LOCO masked-marker transfer R²:

CRC	UPMC	Keren	Phillips	Sorin	mean
V1 (per-image)	.106	.112	.068	.177	.148	.122
V3 (per-cohort)	.155	.165	.139	.201	.183	.169 ← winner
V2a (FiLM, 4 params)	.149	.176	.127	.190	.180	.165
V2b (FiLM, MLP)	.161	.178	.118	.196	.142	.159
V1+V3	.144	.165	.128	.184	.178	.160
V2a+V1	.135	.184	.101	.177	.141	.147
FiLM is dropped, and the measurement is airtight. FiLM is zero-initialised, so at epoch 0 V2a is V3 exactly. Any drop below V3 is therefore not a different model class — it is purely measured overfitting. It scales monotonically with capacity, in the wrong direction: V2a −0.004 (worse on 4/5 folds), V2b −0.010. On Keren, the 40-slide cohort, degradation is monotone in capacity: V3 .139 → V2a .127 → V2b .118. That is the reviewer's prediction, confirmed on the cohort it was made about. The bounded-output design (±30%) is what kept this measurable rather than catastrophic.

Check 2 — composition skew (the check that condemns V1). Within-label contrast: the same label's median marker value on the most skewed 10% of slides minus its median on the most balanced slides. Only the neighbours change.

arm	mean Δ	spread	negative in
V1	−0.135	0.302	6 / 6 cohorts
V3	−0.041	0.185	4 / 6
V2a	−0.043	0.251	4 / 6
V2b	−0.046	0.655	4 / 6
V1 is negative in every cohort — the "invented negative population" is real and universal, worst on Keren (−0.336), which is 50.3% keratin-positive tumour. V3 has the smallest spread; V2b's 0.655 spread (Sorin −0.366, ferguson +0.289) is instability consistent with its overfitting.

Labels track markers well — direct evidence Stage 1b could work, measured before building it. Median best-core-marker AUROC per cohort: CRC 0.677 · UPMC 0.865 · Keren 0.832 · ferguson 0.852 · Phillips 0.828 · Sorin 0.942. Immune lineages near-perfect: CD8 T 0.95–0.99, Tregs 0.96–1.00, B cells 0.91–0.99.

Gate 1 restricts to the 9 all-cohort core markers so no arm can win on imputation instead of normalisation.

6 of 40 declared assertions still fail under V3, all explained, none silently:

3 × panCK on tumour labels (CRC .669, UPMC .586, ferguson .626) — sibling tumour/epithelial classes sit in the negative set, so vs-all-others AUROC is diluted.
2 × CD4 (CRC .716, Phillips .660) — CD4 is also carried by monocytes and macrophages. CD3 separates the same labels at 0.80–0.92.
1 × a real data defect that matters: ferguson EC → CD31 scores exactly 0.500. ferguson's endothelium is marked by CD13/ANPEP (0.83), not CD31, even though its CD31 column is not degenerate. ferguson is the frozen holdout and CD31 is one of the 9 core markers, so zero-shot endothelium on ferguson will fail for a data reason. Recorded before the final test so it cannot later be mistaken for a model failure.
Known weaknesses.

Value tables carry only the 9 core markers. Stage 2 must rebuild wide.
slidestats files exist but FiLM lost, so they are now unused by the accepted path.
4.5 Stage 1b — Automatic label alignment ✅ GATE 1b: PASS
This is the stage that earns the right to drop the ontology. It is the project's central experiment.

Purpose. Map 106 native labels from 6 cohorts into a shared label space with no ontology, no dictionary, and no text.

Input. work/raw/*.parquet (for signatures), work/marker_registry.csv.
Output. work/label_map.csv, work/label_graph.json, work/prototypes.npy, work/s1b_signatures.npz, reports/s1b_labels.md, reports/figures/s1b_tau.png.
Code: pipeline2/s1b_labels.py (~1,250 lines).

Result: 106 native labels from 6 cohorts → 25 clusters.

check	result	pass
0 clusters are not the cohort partition	cohort_ari 0.011, 100% of cells cross-cohort	✅
1 agreement with the hand mapping ≥ 0.90	0.928 (ARI 0.962)	✅
2 required hard cases	4/5 + 1 waived on measured evidence	✅
3 evidence coverage	100% of label pairs directly comparable	✅
4 per-branch splits	6 of 15 candidates accepted, all listed	✅
5 nesting edges	22	✅
6 every cluster coherent	25/25	✅
7 graph is a DAG	asserted True; 0 cycles, 0 transitivity violations	✅
Agreement scored at all three levels of the hand mapping, because the level is the finding:
target (25 classes) 0.928 · L2 (10) 0.855 · L1 (3) 0.629.

The strongest single result: Phillips tumor cells and CRC tumor cells — identical strings, different cell types — are correctly separated (clusters 5 and 0). No string method can do that. B cells came out as exactly 6 labels from 6 cohorts in one cluster.

4.5.1 Declared constants (the tuned surface of the method)

QLEV = np.array([0.02, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.98])
I_LO, I_HI, I_MED = 2, 6, 4     # indices into QLEV used for the containment interval
MIN_CELLS   = 100               # a label needs this many cells to get a signature
DELTA       = 0.05              # floor inside the log-mean overlap, avoids log(0)
W_MIN       = 0.10              # a marker is "informative" above this between-label spread
K_EVID      = 8                 # evidence floor: shared informative markers per pair
SCALE_FLOOR = 0.05              # floor on the per-cohort rescale denominator
NEST_MIN    = 0.75              # containment needed to call a nesting edge
NEST_RELATED= 1.5               # the pair must also be this close, or no nesting edge
MARGIN      = 0.10              # asymmetry needed to call direction rather than merge
CUT_GRID    = np.round(np.arange(0.30, 1.16, 0.025), 4)
FAR         = 5.0               # distance assigned to evidence-poor pairs
SPLIT_SUPPORT   = 0.5           # mean LOCO ARI a split must reach to be kept
MIN_SPLIT_LABELS= 2             # both sides of a split need this many labels
COHORT_ARI_MAX  = 0.20          # guard: partition must not be the cohort partition
MAX_CLUSTER_SHARE = 0.25        # guard: no cluster over 25% of labels
MIN_CROSS_SHARE   = 0.95        # guard: ≥95% of CELLS in a cross-cohort cluster
FAR / SIG_CACHE = work/s1b_signatures.npz
RARE_GLOBAL = ['Plasma', 'NK', 'DC']
4.5.2 The four mechanisms, as built
M1 — Signature. For each (cohort, native label) and each marker: quantiles at QLEV plus a position statistic.

AS BUILT, corrected from the plan: position is the mean rank (the Mann-Whitney statistic behind AUROC), not the median. Quantiles are kept and do real work, but only in the directional layer. Log-prevalence and the co-expression vector are stored but not used by anything — see §7 gap 1.

rescale(S) puts every cohort into one comparable unit (between-label spread):


QT, MEAN, nodes = S['QT'], S['MEAN'], S['nodes']
Z = QT.copy(); P = MEAN.copy()
W = np.zeros((len(nodes), QT.shape[1]), 'float32')
for c in nodes.cohort.unique():
    m = (nodes.cohort == c).to_numpy()
    pos = MEAN[m]
    ctr = np.nanmedian(pos, 0)
    spread = np.nanmax(pos, 0) - np.nanmin(pos, 0)
    sc = np.maximum(spread, SCALE_FLOOR)
    Z[m] = (QT[m] - ctr[None, :, None]) / sc[None, :, None]
    P[m] = (pos - ctr[None, :]) / sc[None, :]
    W[m] = np.nan_to_num(spread, nan=0.0)
return Z, P, W
M2 — Two separate relations, not one. containment(S, Z=None) returns SIM, C, EV, CX:

SIM — symmetric position distance → decides merging.
C — directed containment (interval overlap) → decides direction/nesting only.
EV — count of shared informative markers → the honest evidence; below K_EVID the pair gets distance FAR and may only be joined transitively.
Inner loop per row i:


w = np.minimum(W[i], W)
shared = has[i] & has
w = np.where(shared & (w >= W_MIN), w, 0.0)
EV[i] = (w > 0).sum(1)          # the HONEST evidence
u = w                            # every informative marker
inter = np.clip(np.minimum(hi[i], hi) - np.maximum(lo[i], lo), 0, None)
wid = hi[i] - lo[i]
o = inter / np.where(wid > 1e-6, wid, np.nan)
pt = (lo[i] >= lo - 1e-6) & (lo[i] <= hi + 1e-6)
o = np.where(np.isfinite(o), o, pt.astype('float32'))
o = np.clip(np.nan_to_num(o, nan=0.0), 0.0, 1.0)
sw = u.sum(1)
C[i] = np.exp((u * np.log(np.maximum(o, DELTA))).sum(1) / np.where(sw > 0, sw, np.nan))
d2 = (P[i][None] - P) ** 2
d2 = np.where(u > 0, np.nan_to_num(d2, nan=0.0), 0.0)
SIM[i] = np.sqrt((d2 * u).sum(1) / np.where(sw > 0, sw, np.nan))
Then, after the loop (placement was a bug fix — it was originally mid-loop and caused an IndentationError), per-cohort-pair block normalisation removes panel-size bias:


coh = nodes.cohort.to_numpy()
for a in np.unique(coh):
    for b in np.unique(coh):
        blk = np.ix_(coh == a, coh == b)
        d = SIM[blk]
        fin = np.isfinite(d) & (d > 0)
        if fin.any():
            SIM[blk] = d / np.median(d[fin])
SIM = np.exp(-SIM)
Clustering — average linkage, NOT Leiden:


def distance(active, SIM, EV, k=K_EVID):
    a = np.asarray(active); sub = np.ix_(a, a)
    D = -np.log(np.clip(SIM[sub], 1e-6, 1.0)).astype(float)
    D = (D + D.T) / 2.0
    D[EV[sub] < k] = FAR
    np.fill_diagonal(D, 0.0)
    return D

def cluster(active, SIM, EV, cut, k=K_EVID, coex_gate=None):
    D = distance(active, SIM, EV, k)
    Lk = linkage(squareform(D, checks=False), method='average')
    return fcluster(Lk, cut, criterion='distance') - 1
M2b — Nesting forced acyclic. nesting(S, memb, C, EV, SIM=None, cut=None, tau=NEST_MIN, k=K_EVID) with nested blocks()/build() closures: directed edges only where EV ≥ k; mutual containment without margin → merge; contract strongly connected components (DAG by theorem, and correct biology — mutually-containing labels are one type); assert is_directed_acyclic_graph; transitive closure only on evidence-missing pairs. Measured contradictions are logged as transitivity violations, never overwritten.

M3 — Per-branch top-down bisection. refine(S, memb, SIM, EV, k) plus _bisect and _split_ok. A split is kept only if both sides hold ≥MIN_SPLIT_LABELS, both sides span ≥2 cohorts, and mean LOCO ARI ≥ SPLIT_SUPPORT. Size-agnostic by construction, so rare types are safe.

M4 — Text removed entirely, α = 0. name_clusters(S, memb, P, ncoh) — a marker may only name a cluster if ≥half its labels measured it and it is in ≥3 cohorts.

Granularity selection. choose_cut(S, SIM, EV, k) sweeps CUT_GRID, computes stability / cohort_ari / biggest_share / cross_cohort_share, and sets:


df['usable'] = ((df.biggest_share <= MAX_CLUSTER_SHARE) &
                (df.cross_cohort_share >= MIN_CROSS_SHARE) &
                (df.cohort_ari <= COHORT_ARI_MAX))
tau = float(ok.cut[ok.stability.idxmax()])     # max stability INSIDE the usable window
Other functions: cohort_driven(nodes, memb) (unweighted ARI vs cohort + cell-weighted cross-cohort share), shared_markers(S, idx), ari(a, b, w=None), best_match_agreement (Hungarian assignment via scipy.optimize.linear_sum_assignment), score_hand(..., level='target'), coherence, rare_check, cluster_table, md_table, agree_at, cohort_driven_note.

4.5.3 Declared hard cases — pipeline2/panel/gate1b_expect.csv
13 rows, columns case, relation, members, required, reason, note, waived, waiver_reason.

case	relation	required	outcome
tumour_epithelial (ferguson SC · CRC tumor cells · UPMC Tumor · Keren Keratin_positive_tumor)	same	1	✅ pass
endothelium (CRC vasculature · UPMC Vessel · Keren Endothelial)	same	1	✅ pass
endothelium_ferguson (adds ferguson EC)	same	0	❌ fails as predicted before the run
stroma (CRC stroma · UPMC Stromal/Fibroblast · Keren Mesenchymal_like)	same	1	❌ FAILED → WAIVED
cd4_vs_cd8 (UPMC CD4 T vs CD8 T)	different	1	✅ pass
same_name_different_type (Phillips tumor cells vs CRC tumor cells)	different	1	✅ pass
b_cells (6 labels, 6 cohorts)	same	0	✅ pass
macrophages (6 labels)	same	0	✅ pass
cd8_t (6 labels)	same	0	✅ pass
tumour_vs_tcell (UPMC Tumor vs UPMC CD8 T)	different	0	✅ pass
nest_tcell (CRC CD8+ T ⊂ CRC CD3+ T)	nested	0	❌ no edge
nest_tumour_ki67 (UPMC Tumor Ki67+ ⊂ UPMC Tumor)	nested	0	❌ merged instead
nest_treg (Keren Tregs ⊂ Keren CD4_T)	nested	0	❌ no edge
Two changes to the declared gate, both made BEFORE the run, both visible in the CSV:

Harder: a fifth required case was added — same_name_different_type. The plan declared four.
Narrower: the plan's hard case 2 listed ferguson|EC inside the endothelium merge. It was split into endothelium (three members, required) and endothelium_ferguson (four members, not required), because Gate 1 had already measured ferguson's CD31 as flat. As the plan originally wrote it, hard case 2 would have failed.
4.5.4 The one required failure, fully diagnosed: stroma
CRC stroma · UPMC Stromal / Fibroblast · Keren Mesenchymal_like land in three clusters. Measured similarities 0.42–0.58 against a merge threshold of 0.449.

Cause is the panel, not the method. Of the 17 informative markers those three cohorts share, the only fibroblast-associated one is VIM, which is not fibroblast-specific. Stroma is a negative-definition class in this panel — CRC stroma's nearest cross-cohort neighbours are Sorin monocytes (0.813), which are also negative for every lineage marker.

Disposition (user decision, 2026-08-10): WAIVED, not passed.

gate1b_expect.csv keeps required=1 and adds waived=1 plus the full measured reason, so the declaration history stays visible and nobody can later read this as a case that passed.
The report prints it as a "WAIVED FAILURE, not a pass".
work/label_map.csv has an unreliable column. The 3 clusters the case runs through — 23 labels, 420,862 cells (8.5% of the roster) — are flagged.
Stage 7 must exclude them from the headline number or report them separately.
Re-test if a cohort carrying a fibroblast-specific marker is ever added.
Side observation worth keeping: the same negative-definition cluster (cluster 2) also absorbed CRC dirt, CRC undefined and Keren Unidentified. Junk labels collecting in the "negative for everything" cluster is expected behaviour and a useful signal — Stage 0's decision not to hand-drop them was right, and the coherence check now locates them on evidence.

4.5.5 _validation/ retention decision
_validation/ is NOT deleted, deliberately, and this is a departure from the plan's "delete after the gate passes". Rationale at the time was that Danenberg would be built and Gate 1b re-scored on 7 cohorts. Note: with D-24 (Danenberg repurposed as an arrival test), that rationale weakens — but retaining it is still correct, because the arrival test itself will want a re-score. It still never enters the method — only score_hand reads it, and only inside the report.

_validation/extract_hand_mapping.py reads T and NAT from git show HEAD:pipeline/step4_labels.py via ast.literal_eval (not import — the old module pulls old pipeline paths). Skips HubMap. Writes _validation/hand_mapping_reference.csv: 71 labels, 4 cohorts, 26 targets, 10 L2, 4 L1, 5 dropped.


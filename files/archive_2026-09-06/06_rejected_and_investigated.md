5. Rejected Designs
5.1 The old pipeline (git HEAD:pipeline/) — replaced wholesale
Reached 0.630 mean L1 macro-F1 cross-cohort with gradient boosting on a fixed 19-marker feature table. Four things capped it:

#	Cap	Measured cost	Replacement
1	Hard bins. step2_normalise.py turns each marker into a positive/negative call; on a unimodal image it returns a flat 0.85/0.15 — a cliff, not a measurement	—	Continuous ECDF value encoding (Stage 1)
2	Fixed feature table. Adding markers hurt marker-poor cohorts	ferguson −0.085	Masked-token input so any panel fits (Stage 2)
3	Cohort fingerprinting. Image-level features let the model recognise which dataset it saw	−0.032 mean, Keren −0.125 (step 8b)	Domain-adversarial encoder on slide id (Stage 3)
4	Hand-written label dictionary. step4_labels.py maps every native label into a fixed Cell Ontology tree by hand; adding a cohort means writing a new block	—	Automatic label alignment (Stage 1b) ✅ done, 0.928 agreement
Old files (now deleted from the working tree, still in git HEAD): pipeline/common.py, pipeline/r2common.py, pipeline/step1..step10c, pipeline/panel/*, kaggle/kaggle_full_run.py.

5.2 Text embeddings as a replacement for the ontology — REJECTED before building
Checked against real labels in git show HEAD:pipeline/step4_labels.py:

Failure	Real example	What a text encoder does
Codes carry no text meaning	ferguson: SC EP GC MC BC EC	SC and EC are one character apart and both meaningless. 6 of ferguson's 9 labels break. UPMC's APC is also a gene name and a company
Wrong merge	CD4 T cell vs CD8 T cell	cosine ≈ 0.97 → merged. Opposite cell types
Wrong split	vasculature/Vessel/Endothelial/EC	zero shared words → 4 clusters. One cell type
Wrong split	stroma/Stromal / Fibroblast/Mesenchymal_like	zero shared words → 3 clusters. One cell type
Identical strings, different types	Phillips tumor cells vs CRC tumor cells	scores them identical; must merge. Stage 1b split them correctly
Marker profiles get right exactly what text gets wrong, in both directions. sentence-transformers remains an optional dependency for friendlier naming only; the pipeline runs correctly without it.

5.3 Other rejected ideas (with reasons)
Idea	Verdict	Reason
ESM2 protein-sequence embeddings for thin marker overlap	REJECTED	Sequence similarity is not cell-type similarity. It would repeat text's exact error.
Adaptive α (raise text weight when markers are thin)	REJECTED	It raises text weight exactly where text is most broken — coded, low-overlap cohorts.
Global α knob	DISSOLVED	M4 sets α = 0, so there is no knob to tune.
Bray-Curtis for rare-type protection	REJECTED	It scores abundance composition, not split validity.
6-way cohort adversary instead of slide	REJECTED	Cohort is confounded with tissue; 17% cohort accuracy means the model cannot tell colon from lung.
Blanket transitive closure on the nesting graph	REJECTED	Error amplifier — one false A⊃B propagates to everything under B, and afterwards nothing distinguishes a measured edge from a manufactured one. Closure also does not guarantee acyclicity: closing a graph that already has a cycle turns that cycle into a complete blob. Replaced by SCC contraction (DAG by theorem) + closure on evidence-missing pairs only.
HubMap as a cohort	REJECTED	Healthy tissue, different label space, 2.6M cells would swamp the rest.
Risom 2022	REJECTED	No X/Y centroids, no per-cell label mask. Unrecoverable.
6. Already Investigated (prevents repeating work)
6.1 Stage 1 — the lvl second channel
What was tested. A second per-cell channel holding "the value relative to a cohort-level reference" — tanh of a robust z-score — to stop ranking from destroying prevalence (the plan's answer to Cap 7).
Why. A rank forces a uniform 0–1 spread inside every group, so if 60% of a slide's cells are genuinely CD20+, the level is lost.
Result — it failed three ways:
It saturates. 5.5–17.5% of cells land at |lvl| > 0.99, worst on Sorin (uint8, most markers median 0 and near-zero IQR). Sorin's channel was measured entirely one-sided (min −0.00).
Redundant by construction. Any per-cell function of the raw value computed from cohort statistics is a monotone transform of that value, so it carries what u_coh already carries. Measured correlation with u_coh: 0.89–0.97.
It would have rigged the gate. An arm holding {u_img, lvl} strictly contains an arm holding {u_coh, lvl}, so V1 could not have lost whatever the data said.
Decision. Dropped. The second channel is the other grouping itself, which is genuinely independent information. Cap 7 is answered by the choice of grouping, not by a bolt-on channel.
Revisit? No. Reason 2 is a mathematical argument, not an empirical one.
6.2 Stage 1 — three of my own gate checks were defective
Check	Defect	Fix
Check 3 (label–marker consistency)	Threshold "median rank ≥ 0.75" is mathematically impossible for a label of prevalence > 50%: the ceiling is 1 − p/2. ferguson SC is 56.0% (ceiling 0.720); Keren Keratin_positive_tumor is 50.3% (ceiling 0.748) and "passed" at 0.751 — the check was scoring base rate, not biology	Replaced with AUROC, which is prevalence-invariant
Check 1 (cross-cohort KS)	Confounded by the class-balanced subsample. It appeared to rank V1 best and V3 worst. A per-group ECDF forces each group's marginal uniform by construction, so between-cohort KS must be ~0 on a representative draw. Measured |mean(u_coh) − 0.5| = 0.0009 on a random draw of Keren vs 0.0475 on the stratified one	Distribution checks now use a separate unstratified draw ({cohort}_rand.parquet), and check 1 is explicitly demoted: it confirms raw → transformed (0.720 → ~0.19–0.30) but cannot rank arms
Check 5 / lvl channel	See §6.1	Dropped
Revisit? No — all three are structural errors with proofs, not bad luck.

6.3 Stage 1b — nine substantive method defects, each found by a measurement
#	Defect	Evidence	Fix
1	Clustering tracked COHORT, not cell type. Agreement 0.417; 54 mixed labels from CRC+UPMC+Phillips in one blob; all 16 Sorin labels singletons	Per-cohort ECDF makes a label's position depend on its cohort's composition — Keren is 50.3% keratin+ tumour, CRC 18.4%, so the same biology lands elsewhere	rescale() — divide each (cohort, marker) by its own between-label spread, so position means "relative to the other labels of my cohort"
2	Containment is the wrong statistic for merging — it tracks how WIDE two labels are, not where they sit	UPMC Tumor vs UPMC CD8 T = 0.835; Keren Keratin+ tumour vs ferguson SC = 0.162 — exactly backwards	Split into SIM (symmetric position → merging) and C (directed containment → nesting only). M2's shape survives; which statistic feeds which decision changed
3	The median cannot see a zero-inflated marker. Sorin arrives uint8, over half its cells are 0, the mid-rank ECDF ties them	Only 5 of 17 Sorin markers showed any between-label spread; Keren 19 of 39. Sorin detached entirely	Position becomes the mean rank — the Mann-Whitney statistic behind the 0.91–1.00 AUROCs Gate 1 already measured. Sorin 5 → 8, Keren 19 → 25
4	No global marker ranking can serve every label pair. Top-N selection per cohort pair dropped MS4A1 (CD20) and pan-keratin from the top 8 of every cohort pair (p90−p10 trims the single-high-label signal); switching to max−min swung CRC-UPMC to stromal markers and made CD4 vs CD8 (0.801) indistinguishable from Tumor vs CD8 (0.791)	CD20 is high in exactly one label out of 16–27, so trimming the top decile deletes precisely what defines B cells	Use every informative shared marker, with per-cohort-pair block normalisation by that block's median distance. Also removes the cohort offset by construction (cohort_ari → 0.00)
5	Cross-cohort SIM collapsed to 0.000	Markers selected by range but divided by IQR; a lineage marker has large range and near-zero IQR, sending |z| into the hundreds	Use one statistic for both selection and scaling
6	Adding quantiles to the symmetric distance hurt monotonically	gap 0.196 → 0.135 → 0.075; cohort offset 0.003 → 0.051 → 0.087	Symmetric distance uses position only; quantiles stay in the directional layer
7	Stability could not detect cohort clustering — a pure cohort partition scored 0.972	Stability is invariant to what the partition means	Added cohort_driven() as a hard guard, not an objective term
8	Cell-weighted cohort_ari was misleading (0.23–0.58)	Sorin|Cancer alone is 930k cells and dominates; unweighted was 0.02–0.10	The cohort guard is unweighted; the cross-cohort cell share stays cell-weighted
9	Four label-free objectives are all biased toward an END of the range — stability flat (0.91–1.00), transfer and dendrogram merge-gap run coarse, silhouette runs fine	No single objective can pick granularity honestly	Guards exclude the two trivial ends (no cluster > 25% of labels; ≥95% of cells cross-cohort; not the cohort partition) and stability chooses inside the window. Full sweep including the agreement column is printed so the choice can be checked rather than trusted
Two more that are structural rather than statistical:

#	Defect	Evidence	Fix
10	Leiden gives one giant community plus singletons on a dense similarity over ~100 nodes; its resolution parameter would be a second knob interacting with the threshold, making granularity unidentifiable	ARI at L2 0.86 (average linkage) vs 0.65 (Leiden) on identical inputs	Average linkage replaces Leiden
11	stabilise merge-back chain-merged clusters. Connected components over unstable label pairs let one unstable pair fuse two healthy clusters	Cost 0.09 agreement — 19 clusters at 0.923 → 15 at 0.834	Replaced with refine, a per-branch top-down splitter that cannot chain. This is what lets CD4 T separate from CD8 T inside the T-cell branch without shattering the rest
12	Guard direction was wrong — the first version picked the largest feasible cut	Both quality measures favour the finer end	Changed to max stability in-window
13	Nesting layer degenerate — one broad cluster was "parent" of nearly everything	—	Added NEST_RELATED = 1.5, requiring the pair to also be close, not merely contained
6.4 Stage 1b — the stroma case (do not re-attempt without new data)
What was tested. Whether CRC stroma, UPMC Stromal / Fibroblast and Keren Mesenchymal_like merge on marker evidence.
Result. They do not. Three clusters. Similarities 0.42–0.58 vs a 0.449 threshold.
Root cause, measured. No fibroblast-specific marker exists in the roster (§2.2). Stroma is a negative-definition class; its nearest cross-cohort neighbours are Sorin monocytes (0.813).
Decision. WAIVED, not passed. Declaration history preserved. 3 clusters / 23 labels / 420,862 cells flagged unreliable.
Revisit? Only if a cohort carrying a fibroblast-specific marker (PDGFRB, FAP, COL1A1, DCN, LUM, POSTN, S100A4, TAGLN) is added. Do not retune thresholds to force this merge — the method declining on this evidence is the correct abstention behaviour.
6.5 Stage 1b — implementation bugs already fixed (do not re-introduce)
Bug	Fix
KeyError: "['cluster_name'] not in index" in the report	score_hand's table lacked cluster_name / landed_with; added, and names=names passed through
pd.factorize FutureWarnings on lists	Wrapped in np.asarray
IndentationError — per-cohort-pair normalisation inserted mid-loop	Moved after the loop
SyntaxError: unterminated f-string	A bash heredoc expanded \\n into real newlines. Use a direct Edit, not a heredoc, for Python containing f-strings. Also moved the flagging before the report write so the note appears in the report
6.6 Downloads and acquisition
Item	Result	Revisit?
Danenberg Zenodo 6036188, 6.65 GB	Throttled to ~0.3 MB/s by Zenodo, confirmed on a fresh connection and against record 5850952 — not a local problem	No. Download is done.
Risom Zenodo 5945388	Wrong record — it is the MIBI-TOF tonsil reproducibility paper, not DCIS	No. Do not re-download.
Risom real dataset	No centroids, no per-cell mask	No. Rejected permanently.
Sorin	No cell table at all; feature extraction written (acquire/sorin_extract.py)	Done. 536 images, 0 skipped, 278 s.

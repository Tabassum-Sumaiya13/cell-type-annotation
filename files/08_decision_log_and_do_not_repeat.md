9. Decision Log
Chronological. All entries are currently valid unless marked otherwise.

#	Decision	Reason	Evidence	When	Valid?
D-1	Rebuild in a fresh pipeline2/ rather than patch the old pipeline	Four independent caps, three of them architectural	Old pipeline 0.630 L1 macro-F1; ferguson −0.085; step 8b −0.032/−0.125	project start	✅
D-2	7 cohorts for training + ferguson frozen as test-only	A real final exam needs an unseen machine and unseen tissue	—	project start	✅ (now 5 train + ferguson; see D-24)
D-3	Build + validate locally on a subsample; final full run on Kaggle GPU	13.8 GB RAM, no CUDA locally	—	project start	✅
D-4	No fixed ontology. Labels aligned automatically from marker profiles; the hand mapping survives only as a test set	Hand-writing a block per cohort does not scale and assumes the biology fits a human tree	§5.2 text-encoder failure table	project start	✅ proven at 0.928
D-5	Every stage has a gate. Nothing moves on until it passes	—	—	project start	✅
D-6	Reject Risom	No X/Y centroids, no per-cell label mask	Zip directory range-read	2026-08-09	✅
D-7	Do not use HubMap	Healthy tissue, different label space, would swamp the roster	—	project start	✅
D-8	Stage 0 keeps every column and every cell; dirt/undefined are not hand-dropped	Those calls should be made on evidence downstream	Vindicated: junk labels collected correctly in Stage 1b's negative-definition cluster	2026-08-09	✅
D-9	Marker identity is a triple (gene_or_complex, epitope, modification), not a name	Gene-alone would merge CD45/CD45RA/CD45RO and phospho-/total-RPS6 — exactly the never_merge pairs	9/9 never_merge distinct; 5/5 must_merge unified	2026-08-10	✅
D-10	Field-scoped API queries only; top-hit-wins is banned; require spellings to agree	Free-text PD-1 ranks the right answer 3rd	Measured API calls	2026-08-10	✅
D-11	CD3 ≡ CD3e	UPMC names it CD3e; five cohorts name it CD3; no cohort carries both. Pan-CD3 reagent is in practice anti-CD3ε. Keeping them apart would strand UPMC's only pan-T-cell marker	—	2026-08-10	✅ judgement call, visible in complexes.csv
D-12	CD16 → COMPLEX:CD16 (FCGR3A|FCGR3B)	UniProt returns both; the antibody generally does not separate NK from neutrophil forms	—	2026-08-10	✅
D-13	keep_default_na=False on every registry read + a permanent gate check 3c	pd.read_csv parsed the literal string "NA" (sodium) as missing, so it fell through to HGNC where XK's previous symbol is literally NA	Measured leak	2026-08-10	✅ critical, do not regress
D-14	FiLM input standardised within cohort; output bounded to ±30%; V2a raced against V2b; scored LOCO	FiLM sees 1,137 points, not 4.9M (every cell in a slide feeds the same statistics vector). Keren contributes 40. Unconstrained FiLM could learn a cohort transform, re-injecting what Stage 3 removes	Reviewer critique + arithmetic correction (Keren has 40 slides, 4,942 cells/slide — 2nd highest)	2026-08-10	✅ — and FiLM lost anyway
D-15	Gate 3 metric replaced: retained bits from a fresh held-out-slide probe, decision on LOCO F1	"Accuracy must fall toward chance" is unreachable (0.09% on 1,137 slides) and thresholdless — it could fail a working adversary	Reviewer critique, accepted	2026-08-10	✅
D-16	Domain stays slide, not cohort	Cohort is confounded with tissue; 17% cohort accuracy means the model cannot tell colon from lung	Old pipeline: cohort info cost −0.032 mean, −0.125 Keren	2026-08-10	✅
D-17	M2b: SCC contraction then closure on evidence-missing pairs only	Blanket closure is an error amplifier and does not guarantee acyclicity. SCC contraction gives a DAG by theorem and reads correctly in biology	Reviewer critique, diagnosis corrected (A→B, B→C, A↛C is a DAG, not a cycle)	2026-08-10	✅
D-18	Stage 4 deferred	Nothing depends on it; z_neigh absent = Gate 4's z_cell only arm. No rework cost	User decision	2026-08-10	✅
D-19	Stage 5 dropped	Measured −0.032 mean / −0.125 Keren in the old pipeline	step 8b	project start	✅
D-20	Ship V3 (per-cohort ECDF, no FiLM, one channel)	Highest LOCO R² (0.169), smallest composition-skew spread; FiLM degrades monotonically with capacity	Full bake-off table §4.4	2026-08-10	✅ The plan predicted V2 would win. It did not, and the plan was wrong.
D-21	Drop the lvl second channel	Saturates, redundant by construction (r 0.89–0.97), and would have rigged the gate so V1 could not lose	§6.1	2026-08-10	✅
D-22	Average linkage, not Leiden	Leiden gives one giant community plus singletons on a dense ~100-node similarity, and its resolution is a second knob	ARI at L2 0.86 vs 0.65	2026-08-10	✅
D-23	stroma WAIVED, not passed; 3 clusters flagged unreliable for Stage 7	The cause is the panel, not the method — no fibroblast-specific marker exists in the roster. Declaring it passed would hide a real limitation	Similarities 0.42–0.58 vs 0.449; nearest neighbour is Sorin monocytes 0.813	2026-08-10	✅ explicit user decision
D-24	Danenberg is NOT added to the training roster. It becomes the "new cohort arrives later" test	It is the strongest possible demonstration that adding a cohort needs no code change	—	2026-08-10 (latest)	✅ user decision — supersedes the earlier "build Danenberg next" plan
D-25	_validation/ retained rather than deleted after Gate 1b	Gate 1b must be re-scorable when the arrival test runs. It still never enters the method — only score_hand reads it, inside the report	—	2026-08-10	✅ deliberate deviation from the plan
10. Do Not Repeat
Consult this before proposing anything.

10.1 Failed ideas — do not rebuild
Text embeddings for label alignment. Fails in both directions on this exact data (§5.2). Text is naming-only, α = 0.
ESM2 protein sequence embeddings for thin marker overlap. Sequence similarity ≠ cell-type similarity.
Adaptive α. Raises text weight exactly where text is most broken.
The lvl second channel (tanh robust z-score). Saturates; redundant by construction; would rig the gate.
FiLM (both V2a and V2b). Measured worse than V3, monotonically in capacity, worst on the cohort the reviewer predicted.
Per-image ranking (V1) as the default. Negative composition skew in 6/6 cohorts. It is the old GMM-cliff bug in a new costume.
Leiden on the label similarity graph. One giant community plus singletons; ARI at L2 0.65 vs 0.86.
Merge-back stabilisation (stabilise). Chain-merges healthy clusters through one unstable pair. Cost 0.09 agreement.
Top-N marker selection per cohort pair. Deletes exactly the single-high-label markers (CD20, pan-keratin) that define rare types.
Median as the position statistic. Cannot see a zero-inflated marker. Use mean rank.
Containment as the merging statistic. Measured exactly backwards.
Adding quantiles to the symmetric distance. Hurts monotonically.
Blanket transitive closure on the nesting graph. Error amplifier; does not even give acyclicity.
A 6-way cohort adversary. Destroys tissue biology.
Bray-Curtis for rare-type protection. Wrong quantity.
Forcing the stroma merge by retuning. The abstention is correct on this evidence.
10.2 Disproven assumptions
"V2 (FiLM) will win Gate 1." It lost. The plan was wrong and says so.
"Keren has 43 slides." It has 40, with 4,942 cells/slide — the 2nd highest. Cells-per-slide is not the binding number; distinct FiLM training points is.
"A→B, B→C, A↛C is a cycle." It is a DAG. And narrow-inside-broad containment goes up, not down — it is the easy direction.
"Class imbalance lets a 1,137-way discriminator cheat." Mean slide share is 0.09%; even a slide 3× the mean reaches ~0.4%.
"A high-scoring slide probe means it is fitting noise." Slide identity is genuinely present in the values — that is real signal.
"Stage 0b computes a dynamic-range score." It does not. Stage 2 must build it.
"Stability can detect a cohort-driven partition." A pure cohort partition scored 0.972. Guards are required.
"Zenodo 5945388 is Risom DCIS." It is the tonsil reproducibility paper.
10.3 Implementation mistakes — do not regress
pd.read_csv without keep_default_na=False turns sodium ("NA") into a missing value → resolves to gene XK.
Scoring an unresolved member of must_merge as a pass. Unresolved counts as failure.
Using a stratified subsample for any check on a distribution. Use the _rand draw.
A "median rank ≥ threshold" check on a label whose prevalence exceeds 50% — the ceiling is 1 − p/2, so the check scores base rate.
Selecting markers by one statistic and scaling by another (range vs IQR) → |z| in the hundreds.
Putting the per-cohort-pair normalisation inside the containment loop.
Writing Python containing f-strings through a bash heredoc — \\n expands into real newlines. Use Edit.
Cell-weighting a cohort-identity guard — one 930k-cell label (Sorin|Cancer) dominates it.
10.4 Reviewer objections already addressed — do not re-litigate
FiLM overfitting on Keren → D-14, and FiLM lost anyway.
Containment non-transitivity → D-17 (SCC contraction).
Unreachable adversary accuracy → D-15 (retained bits + LOCO F1).
10.5 Unnecessary complexity, already removed
Leiden's resolution parameter (a second knob interacting with the cut threshold).
The global α knob (dissolved by α = 0).
Four label-free granularity objectives (all biased toward an end; replaced by guards + stability inside the window).

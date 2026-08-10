4.6 Stage 2 — Tokenisation + masking ⚪ DESIGNED, NOT BUILT
This is the next stage to build. The design below was worked out but never confirmed by the user and no code was written.

Purpose. One token per marker so that any panel fits, and a self-supervised objective (predict a hidden marker) that needs no labels.

Input. work/raw/*.parquet + work/marker_registry.csv + the Stage 1 winner (V3, per-cohort ECDF).
Planned output. pipeline2/nn/tokens.py, pipeline2/s2_tokens.py, work/values/{cohort}_full.parquet, work/panel.json (token vocabulary), work/ckpt/s2_*.pt, reports/s2_masking.md.

Step 2.1 — wide value tables. Rebuild per-cohort value tables over the full panel (all non-non_protein triples that cohort measures), using u_coh only (FiLM lost, so slidestats are not needed). Reuse the exact cell ids from the existing work/values/{cohort}.parquet so the subsample stays aligned and reproducible.

Step 2.2 — dynamic-range score (must be built here; Stage 0b never computed it).
The naive measure fails: u_coh is a rank, so its IQR is 0.5 by construction across the cohort. Raw IQR is not comparable across cohorts with different scales. Two scale-free measures instead:

tie_mass(c, m) = the share of cells sharing the single most common raw value. Directly captures Sorin's uint8 zero-inflation and UPMC's flat markers, and directly predicts "median wins".
robust dispersion = raw IQR / (p99 − p01), scale-free within a marker.
Declared exclusion rule (declared before the run, per project convention): exclude a (cohort, marker) pair from the mask loss if tie_mass ≥ 0.5 — over half the cells share one value, so the median predictor is right at least half the time by construction and R² is meaningless. Report a sweep over {0.3, 0.4, 0.5, 0.6, 0.7} with counts per cohort, so the choice is checkable rather than trusted.

Motivating evidence from the plan: UPMC's CD152, PDL1, PD1, CD134 and CD47 have an interquartile range of about 0.05 — predicting the median wins, so the loss looks great and teaches nothing.

Step 2.3 — the token model (pipeline2/nn/tokens.py).

Vocabulary: 99 triples, index 0..98. Learned identity embedding E[99, d].
Value embedding: shared MLP on the u_coh scalar → d (reuses the MarkerEncoder design — the value MLP is shared across markers and identity is added separately, so a never-seen panel still gets encoded).
Token = value_emb + ident_emb. Masked token = mask_emb + ident_emb — identity is kept so the model knows which marker is hidden. This is critical and was already proven necessary in Stage 1 (MaskedMarkerProbe passes query = self.enc.ident(mask_idx)).
Encoder: set transformer, 2 blocks of multi-head self-attention (4 heads) with a key-padding mask.
Masking: 15% of measured markers per cell, at least 1.
Head: per masked token, Linear(d → 1) → predicted u_coh.
The one genuine architectural fork — [ABSENT] tokens. The plan says "Absent markers get a learned [ABSENT] token, never a zero." There is a strong argument against this, and it was to be settled by measurement, not by opinion:

The set of markers a cohort measures is a near-perfect cohort identifier (union panel 99; per-cohort panels 17–57; 43 triples are cohort-exclusive). Feeding [ABSENT] tokens hands the model a panel fingerprint = cohort fingerprint, which is exactly what Stage 3's adversary then has to erase. Absent slots add no biological information — absence is a property of the panel, not of the cell. A Sorin cell would be 17 measured and 82 absent (83% wasted tokens).

Counter-consideration: the identity embeddings of the present markers already leak the panel, and that cannot be avoided because the model must use the markers it has. The difference is that [ABSENT] tokens add only panel information.

Decision method (project style — measure, don't assume): build both arms.

Arm A (set): tokens = only the cohort's measured markers; padding mask hides the rest.
Arm B (absent): all 99 slots; unmeasured slots get absent_emb + ident_emb and attend normally. This is the plan's design.
Step 2.4 — GATE 2, four declared checks:

Per-marker masked reconstruction R² on held-out cells, held out by slide so it is not trivially memorised, against the training-median baseline (R² = 1 − MSE_model / MSE_median). PASS: every kept marker has R² > 0, and median kept-marker R² ≥ 0.10.
Flat-marker exclusion is auditable. Full table of every excluded (cohort, marker) with tie_mass, robust dispersion, and baseline MSE, plus the threshold sweep. PASS: excluded markers must show higher R² than kept markers if they were included — proving they inflate the score rather than being hidden inconveniences.
Dynamic tokens must beat the fixed 9-marker core. LOCO masked-marker R² on the same 9 core markers, full panel vs Gate 1's V3 number. PASS: full-panel LOCO R² ≥ 0.169. This is the check that says Stage 2's complexity was earned.
[ABSENT] ablation + panel fingerprint. Arm A vs Arm B on reconstruction R², plus a cohort probe (logistic regression on pooled z_cell predicting cohort, 6-way). Decision rule: ship the arm with better R²; if tied, ship A. Report cohort-probe accuracy for both — if B is much higher, that confirms the absent tokens are a panel fingerprint.
Compute budget (estimated, not measured). d_model=64, 2 blocks, subsample ~15k cells/cohort (~90k total), early stopping patience 4. Roughly 20–40 s/epoch, ~10 min per run. 2 arms (held-out cells) + 5 LOCO folds = 7 runs ≈ 70–80 min on the 8-core CPU. d_model=128 with 40k cells/cohort was estimated at ~270 s/epoch — too slow, hence the reduction.

Known weaknesses of the design. LOCO folds are over the 5 training cohorts only (ferguson stays frozen). The tie_mass ≥ 0.5 threshold is a declared judgement, not a derived optimum.

4.7 Stage 3 — Cell encoder + adversarial ⚪ PLANNED
Purpose. Produce z_cell (128-d) that carries biology but not batch.

Design. Set Transformer over the marker tokens → z_cell. A gradient reversal layer feeds two heads: slide id (1,137-way on the current roster, high weight) and cohort (6-way, low weight). λ ramps 0 → cap over the first epochs.

Why the domain stays slide, not cohort. Swapping to a 6-way cohort adversary is achievable precisely because it is destructive: cohort is confounded with tissue (colorectal · head&neck · breast · lung · skin ×2), so driving cohort accuracy to 17% means the embedding can no longer tell colon from lung — and colon and lung tumour cells genuinely differ. The old pipeline already priced this: cohort-level information cost −0.032 mean, −0.125 on Keren. Slide-to-slide variation inside one cohort is near-pure batch effect — same tissue, same machine, same disease — so erasing it is safe. Achievability is not the goal; not destroying biology is.

The metric was rewritten because the original was defective. "The discriminator's accuracy must fall toward chance" is unusable: chance on 1,137 slides is 0.09%, no run will reach it, and no threshold was given — so the gate could fail an adversary that works perfectly.

Two replacements:

Retained bits. retained_bits = log2(N_slides) − CE_bits. At chance this is 0. Scale-free, comparable across λ. Report absolutely and as a fraction of the λ=0 value.
Score it with a fresh probe on held-out slides. Adversarial training can hide information from the co-trained discriminator without removing it — the discriminator settles into a bad optimum and the encoder exploits it. So: freeze the encoder, train a new discriminator from scratch, score on slides it never saw.
GATE 3 — decided on F1, explained by bits. Sweep λ over at least {0, 0.01, 0.03, 0.1, 0.3}, four columns per λ:

LOCO L2 macro-F1 — this alone decides. Pick the λ that maximises it.
Retained slide bits from a freshly trained held-out-slide probe, absolute and as a fraction of λ=0. Expect a monotone fall. Diagnostic, never the decision.
Cohort-head accuracy — an inverted guard. If it falls near chance (1/6 ≈ 17%), that is a warning that tissue identity is being erased, not a success.
Co-trained vs fresh-probe bits side by side. A large gap means the adversary is hiding rather than removing slide information.
Fallback: if no λ beats λ=0 on F1, ship λ=0 and say so plainly. A working model beats a broken idea.

Two claims from the review that do NOT hold, recorded so they are not re-litigated:

With 1,137 classes, always guessing the largest slide scores well under 0.5% (mean slide share 0.09%; even a slide 3× the mean reaches ~0.4%). Class imbalance buys the discriminator almost nothing.
A probe scoring high is not "because of noise" — slide identity is genuinely present in the input values, which is real signal.
4.8 Stage 4 — Adaptive spatial ❌ DEFERRED (user decision, 2026-08-10)
Not built. Design kept intact so it can be picked up unchanged. Stages 1 → 1b → 2 → 3 → 6 → 7 run without it: z_neigh is simply absent from the encoder input, which is the same as the z_cell only arm of Gate 4. Nothing upstream or downstream depends on it, so deferring costs no rework.

Design if resumed. k = 15 nearest neighbours, built inside one image only (all coordinate frames are image-local). Edge feature = distance in µm and log-distance. Message passing with plain scatter ops so it needs no torch_geometric (not installed, and not available by default on Kaggle either).

GATE 4 — must include the shuffle control. Three numbers per fold: z_cell only · z_cell + z_neigh · z_cell + z_neigh with neighbours permuted inside the image. The middle must beat the first, and the third must fall back toward the first. If shuffling does not hurt, the "spatial" gain is not spatial — it is leakage.

Expectation set in advance: the old pipeline's k10-vs-r30 test was a wash (−0.001 mean). Any gain must come from the learned distance weighting, not from switching to kNN.

4.9 Stage 5 — Global slide branch ❌ DROPPED
Not built. Measured cost in the old pipeline: −0.032 mean, Keren −0.125. Revisit only as a final ablation after Stage 7 works. If reintroduced, it ships only if it improves LOCO L2 macro-F1 on ≥5 of 7 folds.

4.10 Stage 6 — Losses and training ⚪ PLANNED
Cell type: weight fixed at 1.0. Implemented as a prototype loss — each Stage 1b cluster has a prototype vector in z_cell space, initialised from its marker signature (work/prototypes.npy). Cells are pulled toward their cluster's prototype. Prototypes are learnable, so the protein data may correct the Stage 1b clustering during training.
The loss must respect nesting, or M2 was pointless. A cell labelled at a parent node must not be punished for being predicted as any of its descendants. Use a descendant-tolerant cross-entropy: the target is the set of leaves under the labelled node, not a single leaf. This is how a cohort that only says T cell can still train a model that outputs CD8 T. The old pipeline already scored this way at L1, so the idea is proven — it moves from scoring into the loss.
⚠️ Blocked-ish dependency: the Stage 1b nesting layer missed all three declared cases (§7 gap 2). Do not rely on descendant-tolerant loss until nesting is re-tested.

Collapse guard (what makes learnable prototypes safe): track pairwise prototype distances every epoch. If any pair falls below a floor, two classes are silently merging — log it, freeze that pair, report it. Without this guard a class can vanish and F1 still looks fine.
Learnable σ (Kendall uncertainty weighting) on auxiliary heads only: masked-marker reconstruction · neighbourhood context prediction · VICReg. Why the cell-type σ is pinned: Kendall weighting is free to drive the cell-type loss toward zero because noisy labels look "uncertain" — and that is the one task that matters.
Cells weighted by label confidence where it exists (UPMC ships kNN.prob, 0.14–1.0).
Class-balanced sampling — imbalance runs to 1,253:1 in CRC.
GATE 6 — three checks:

σ trajectory plot. If any auxiliary σ runs away, that loss is being switched off — say so.
Prototype drift plot. Minimum pairwise prototype distance over epochs and any frozen pairs. Re-score agreement with Gate 1b's clustering after training — if the model moved prototypes a lot, report which labels it disagreed with. That disagreement is a finding, not a bug.
Loss ablation. Train with 2 losses (cell type + masked marker) and with all 4. Keep the extra two only if they improve validation macro-F1.
4.11 Stage 7 — Zero-shot inference + abstain ⚪ PLANNED
LOCO over the training cohorts: train on n−1, test on the nth, rotate.
Within-cohort by-patient split as the ceiling, so the cross-cohort penalty is measurable.
The frozen ferguson run: load the final model, predict, never retrain. One number, once.
Abstain: distance to the nearest prototype in z_cell space, plus temperature-scaled max-softmax, calibrated on held-out slides from the training cohorts. Report an accuracy-versus-coverage curve, not a single threshold.
Novel-class test uses the cohort-exclusive clusters found in Gate 1b. Detection is in embedding space, not text space — measuring novelty by text distance needs the new cohort to have labels; measuring it by distance to prototypes in z_cell works on a cohort with no labels at all, which is the real deployment case.
MUST honour the stroma waiver: exclude or separately report the 3 flagged clusters (23 labels, 420,862 cells, 8.5%).
GATE 7 — the final result:

LOCO macro-F1 on the core clusters, all folds, vs the old 0.630 baseline and the published MAPS cross-dataset baseline of 0.5–0.6. State the cluster count next to the number — the class set is now data-derived, so the comparison is indicative, not exact.
The ferguson zero-shot number, stated plainly whatever it is.
Accuracy-vs-coverage curve for the abstain head.
Novel-class detection AUROC on the cohort-exclusive clusters.

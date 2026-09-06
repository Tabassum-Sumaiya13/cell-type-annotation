4.6 Stage 2 — Tokenisation + masking ❌ BUILT AND RUN — GATE 2 FAIL (2026-08-11)

RESULT, recorded before the design text below. The design was built as written except where a
dated decision says otherwise; the original wording is kept so the changes stay auditable.

  check 1  per-marker reconstruction R²        FAIL   median 0.5122 (floor 0.10) but 1 kept pair
                                                      below zero: Keren MKI67, R² −0.0117
  check 2  flat-marker exclusion auditable     PASS   14 pairs; median R² differs by −0.4391
  check 3  dynamic tokens beat the fixed core  PASS   full 0.1963 · core-9 control 0.1707 ·
                                                      Gate 1 0.169  ← this is H3, and it holds
  check 4  [ABSENT] ablation                   decided  Arm B ships (D-30)

The FAIL is accepted and recorded, not repaired (D-34). The `rank_spread` floor was NOT moved to
catch Keren MKI67 at 0.2621, because moving a threshold after seeing which marker failed is what
declaring thresholds in advance exists to prevent. The mechanism is understood: Keren's held-out
slides collapse the R² denominator (split_spread 0.2621 against 0.9543 in CRC and 0.9131 in UPMC,
where the same marker scores 0.3706 and 0.2405). Keren has 40 slides, the fewest on the roster.

Four rules in this stage were replaced after being declared — D-26 (mean not median baseline),
D-28 (rank_spread not tie_mass), D-29 (floor applied to the scored split too), D-30 (arm chosen
cross-cohort, not within-cohort) — plus D-27 (core-9 control added) and D-33 (check 3 reported in
two columns). All are in file 08 and in pipeline2/panel/gate2_expect.csv, where the superseded
rows are marked REPLACED and kept beside their replacements.

Built: pipeline2/nn/tokens.py · pipeline2/s2_tokens.py · pipeline2/panel/gate2_expect.csv ·
work/values/{cohort}_full.parquet (6) · work/panel.json · work/s2_dynrange.csv ·
work/ckpt/s2_*.pt (18) · reports/s2_masking.md.

--- the design as originally written, below this line ---

Purpose. One token per marker so that any panel fits, and a self-supervised objective (predict a hidden marker) that needs no labels.

Input. work/raw/*.parquet + work/marker_registry.csv + the Stage 1 winner (V3, per-cohort ECDF).
Planned output. pipeline2/nn/tokens.py, pipeline2/s2_tokens.py, work/values/{cohort}_full.parquet, work/panel.json (token vocabulary), work/ckpt/s2_*.pt, reports/s2_masking.md.

Step 2.1 — wide value tables. Rebuild per-cohort value tables over the full panel (all non-non_protein triples that cohort measures), using u_coh only (FiLM lost, so slidestats are not needed). Reuse the exact cell ids from the existing work/values/{cohort}.parquet so the subsample stays aligned and reproducible.

Step 2.2 — dynamic-range score (must be built here; Stage 0b never computed it).
The naive measure fails: u_coh is a rank, so its IQR is 0.5 by construction across the cohort. Raw IQR is not comparable across cohorts with different scales. Two scale-free measures instead:

tie_mass(c, m) = the share of cells sharing the single most common raw value. Directly captures Sorin's uint8 zero-inflation and UPMC's flat markers, and directly predicts "median wins".
robust dispersion = raw IQR / (p99 − p01), scale-free within a marker.
[REPLACED by D-28 before any training run — see the result block at the top of this section. The rule below catches none of the five UPMC cases it was written for and would delete 16 of 17 Sorin markers. Replaced by rank_spread = Var(u_coh)/(1/12) < 0.20. The original text is kept unchanged:]
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

4.7 Stage 3 — Cell encoder + adversarial ✅ GATE 3 PASS, ships λ = 0 (2026-08-11)

RESULT. 25/25 folds, 39.8 min on a Kaggle T4. Cross-cohort macro-F1 **0.3642** over the 22
reliable clusters, against a majority-class baseline of 0.0078 and random 0.0466 computed on the
same folds. λ = 0 ships — the plan's own declared fallback (D-36).

  λ        0      0.01     0.03      0.1      0.3
  F1     0.3642  0.3460   0.3588   0.3425   0.2949    fold sd 0.06-0.07
  fresh  3.504   3.450    3.377    3.121    2.654     retained slide bits
  cotr   2.204   1.419   -0.846   -3.285   -2.020     co-trained discriminator
  coh    0.775   0.551    0.382    0.231    0.264     cohort guard, chance 0.25

THE ADVERSARY DOES NOT HELP, and two findings explain why — both more interesting than the
verdict:

  D-37  It HIDES rather than REMOVES. The co-trained discriminator is driven below chance
        (−3.29) while a fresh probe still recovers 89% of the slide information. Scored on the
        co-trained number alone this would have been reported as a total success. The likely
        cause is a design defect: the adversary is a single nn.Linear while the probe judging it
        is a 2-hidden-layer MLP, so the encoder only had to make slide identity NON-LINEARLY
        separable — cheap, and it removes nothing.
  D-38  The DOMAIN is misspecified. In 4 of 5 folds the majority of the adversary's classes are
        individual PATIENTS, not batches: Keren has 1.00 slides/patient and Sorin 1.13, against
        CRC 4.00, UPMC 3.80, Phillips 4.93. Erasing them erases tumour biology. Predicted from
        the acquisition design and then confirmed: the one fold whose adversary is genuinely
        about batch (held-out Sorin, 7.1% patients) gains +0.0752, more than 3x any other.
        n=5, p≈0.07 — suggestive, not significant.

Also note the original motivation is moot. The old pipeline's −0.032/−0.125 came from FEEDING
image-level features to the model; this pipeline never does (FiLM lost Gate 1, D-20, and Stage 2
dropped u_img). Stage 3 reads only u_coh columns.

STAGE 3b — DONE, and it closes the argument (D-43). 45 runs, 3 arms x 3 lambdas x 5 folds,
80.2 min on a T4. Both rescue hypotheses FAIL, so lambda = 0 stands:

  H5  the discriminator was too weak?   NO. Matching its capacity to the probe made hiding WORSE:
      fresh bits at lambda=0.3 ROSE to 2.92 (from 2.65 with the linear head) while the co-trained
      head fell further, to -4.53 (from -2.02). A stronger critic bought a better hiding place.
  H6  the domain was wrong?             NO, and this was MY hypothesis (D-38). The nested
      slide-within-patient domain is worse at every lambda (-0.0183, -0.0306, -0.0857), and the
      Sorin gain that motivated it did not replicate: +0.0752 became +0.0070 under nesting while
      persisting at +0.0743 in the arm that does NOT nest. The n=5, p~0.07 correlation did not
      survive its own test, exactly as that caveat warned it might not.

Best challenger: arm A at lambda=0.03, +0.0063 over baseline - inside the +/-0.06 fold noise.

The finding that survives is stronger than the verdict. Arm B removed the MOST slide information
proportionally (26.4% retained against 38.0% at lambda=0) and scored the WORST macro-F1 (0.2785)
with the cohort guard breached at 0.228. Removing batch signal more successfully made transfer
WORSE. Batch is not the bottleneck on this roster.

NOTE ON COMPARING BITS ACROSS ARMS: nesting cuts the slide vocabulary from 594 to 319, so
log2(N) falls from 9.21 to 8.32 and raw retained-bit values are not comparable between arms. The
percentages above are the comparable quantity.

Built: pipeline2/nn/encoder.py · pipeline2/s3_encoder.py · pipeline2/panel/gate3_expect.csv ·
pipeline2/kaggle/ (make_upload.py, kaggle_stage3.py, stage3.ipynb, README.md) ·
work/ckpt/s3_lam*_*.pt (25, weights included) · reports/s3_encoder.md. Runs on CPU or CUDA from
one code path.

TWO CHANGES TO THE DECLARED GATE, both settled before any scored run and both in file 08:
  D-31  the decision metric is LOCO macro-F1 over Stage 1b's 25 CLUSTERS, not the hand mapping's
        L2. L2 covers 3 of the 5 training cohorts — Phillips and Sorin have none — so the
        declared metric is not computable on this roster. L2 is still reported as a secondary.
  D-35  the fresh probe is scored on held-out CELLS OF THE SAME SLIDES, not on held-out slides.
        The declared rule is structurally impossible: a slide classifier cannot predict a class
        it has no training example of. Measured under the old rule — accuracy exactly 0.000000,
        retained bits −28.5 against a ceiling of log2(751) = 9.55. The co-trained column had the
        same defect. Both now score on the same held-out cells, so their gap compares like with
        like. Note this is the SECOND rewrite of this measurement; D-15 was the first.

Also added, because the stage as designed had no way to pass or fail: check 1 compares the shipped
lambda against a MAJORITY-CLASS and a RANDOM-UNIFORM predictor computed inside the same run on the
same folds under the same waiver — a measured reference rather than a guessed threshold.

Not yet run: the 25-fold sweep. ~18 h locally, ~1–2 h on a Kaggle T4. See pipeline2/kaggle/README.md.

--- the design as originally written, below this line ---

Purpose. Produce z_cell (128-d) that carries biology but not batch.

Design. Set Transformer over the marker tokens → z_cell. A gradient reversal layer feeds two heads: slide id (1,137-way on the current roster, high weight) and cohort (6-way, low weight). λ ramps 0 → cap over the first epochs.

Why the domain stays slide, not cohort. Swapping to a 6-way cohort adversary is achievable precisely because it is destructive: cohort is confounded with tissue (colorectal · head&neck · breast · lung · skin ×2), so driving cohort accuracy to 17% means the embedding can no longer tell colon from lung — and colon and lung tumour cells genuinely differ. The old pipeline already priced this: cohort-level information cost −0.032 mean, −0.125 on Keren. Slide-to-slide variation inside one cohort is near-pure batch effect — same tissue, same machine, same disease — so erasing it is safe. Achievability is not the goal; not destroying biology is.

The metric was rewritten because the original was defective. "The discriminator's accuracy must fall toward chance" is unusable: chance on 1,137 slides is 0.09%, no run will reach it, and no threshold was given — so the gate could fail an adversary that works perfectly.

Two replacements:

Retained bits. retained_bits = log2(N_slides) − CE_bits. At chance this is 0. Scale-free, comparable across λ. Report absolutely and as a fraction of the λ=0 value.
Score it with a fresh probe on held-out slides. [REPLACED by D-35 — impossible as written, see the result block at the top of this section. The replacement scores on held-out CELLS of the same slides. Original text kept:] Adversarial training can hide information from the co-trained discriminator without removing it — the discriminator settles into a bad optimum and the encoder exploits it. So: freeze the encoder, train a new discriminator from scratch, score on slides it never saw.
GATE 3 — decided on F1, explained by bits. Sweep λ over at least {0, 0.01, 0.03, 0.1, 0.3}, four columns per λ:

LOCO L2 macro-F1 — this alone decides. Pick the λ that maximises it. [REPLACED by D-31 — not computable on this roster; Phillips and Sorin have no L2 truth. Replaced by macro-F1 over Stage 1b's 25 clusters with the stroma waiver honoured (D-32). L2 kept as a secondary column at 3-of-5 coverage.]
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

4.10 Stage 6 — Losses and training ✅ BUILT AND RUN — GATE 6 PASS (2026-08-11)
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

RESULT — GATE 6 PASS, 16 fits, 73.5 min on a Kaggle T4. Ships the PROTOTYPE head with 2 LOSSES at LOCO macro-F1 0.3901 over the 22 reliable clusters. Report: reports/s6_train.md.
Check 1 PASS — largest log-sigma move 1.142 against a cap of 3.0. No auxiliary loss was switched off.
Check 2 PASS — minimum pairwise prototype distance floor 0.0359, no pair ever frozen. The plan feared merging; the opposite happened. Prototypes SPREAD, minimum 0.0717 → 0.9571 and median nearest-neighbour 0.1288 → 1.1040, about 13x. The 10 largest drifts are listed in the report and are the model disagreeing with Stage 1b, which the design says to read as a finding.
Check 3 — VICReg is DROPPED. 2 losses 0.3901 vs 3 losses 0.3788. ⚠️ the honest reading is "the ablation cannot separate them on 5 folds" (p = 0.191), NOT "VICReg hurts".
Check 4 PASS by +0.0209 against a declared +0.02 — but READ D-44 BEFORE QUOTING IT. Paired over the 5 folds the margin is p = 0.460, 95% CI [-0.0501, +0.0919], and ALL of it comes from held-out Sorin (+0.1211) while the prototype head loses 3 of 5 folds. The gate passes on its declared rule; it does not show that the prototype loss improves transfer. The head still ships, on the design argument that Stage 7's abstain rule needs prototype distances.
Check 6 ❌ NO-OP, UNSCORED — a design error of mine. Confidence weighting was tested on the held-out-UPMC fold, the one fold where UPMC (the only cohort with a confidence) is excluded from training, so both arms ran the same computation and printed identical scores. Repair: hold out CRC instead, 2 fits (D-45).
NOT BUILT, each declared in panel/gate6_expect.csv before any code: descendant-tolerant CE (D-41, blocked by the untrusted nesting graph), the neighbourhood loss (D-40, needs deferred Stage 4 — so the "2 vs 4" ablation is a 2 vs 3), and the adversary (D-36, Gate 3 shipped lambda=0).
The stage was aimed at H7 — CRC being the worst fold despite the largest cohort and second-richest panel — and it did NOT fix it. CRC is still worst at 0.2983, and it carries the largest generalisation gap on the roster: val 0.7866 in-distribution against test 0.2983 cross-cohort, +0.4883. H7 stays open.
Class-balanced sampling was specified above and IS in the shipped fit; its contribution was never ablated separately, so no claim is made for it.

4.11 Stage 7 — Zero-shot inference + abstain ✅ GATE 7 RUN (2026-08-11) — Stage 7a AND 7b both run
STAGE 7b RESULT (D-52, reports/s7b_abstain.md): the abstain rule WORKS - macro-F1 0.3309 at full coverage rises to a PEAK of 0.4204 at 35% coverage, and all 8 scored classes survive at every coverage down to 10%, so it declines cells rather than cell types. Novel-class detection FAILS at AUROC 0.578 on a genuinely novel type (ferguson EP, admitted by no cluster in space B2). gate7b_expect.csv check 6 declared in advance that an AUROC near chance is a reportable FAILURE of the deliverable, not a null result, and it is reported as one. ⚠️ READ THE TWO CURVE COLUMNS TOGETHER: accuracy rises monotonically to 0.7120 at 10% coverage while macro-F1 turns over after 35% - accuracy alone picks the WORST operating point on the curve
RESULT: **ferguson zero-shot macro-F1 0.3309** over 22 reliable clusters, majority 0.0237, random 0.0562. 3 fits, 20.0 min on a T4. A 0.3309 (25 clusters, shipped) · B1 0.3080 (37, clean) · B2 0.4240 (22, clean, matched cut). Report: reports/s7_eval.md, decisions D-50/D-51.
THE HEADLINE AVERAGE HIDES TWO REGIMES AND THE WRITE-UP MUST SPLIT THEM. Labels whose target cluster is carried by >= 3 training cohorts: TC_CD8 0.8131, TC_CD4 0.5192, BC 0.5091, MC 0.4372, SC 0.3671 - mean 0.5291. Labels whose cluster is carried by <= 2: EC 0.0039, GC 0.0016, EP 0.0000, DC 0.0000 - mean 0.0014. r = 0.798 against log training cells, 0.843 against the number of contributing cohorts. Gate 6 measured the same law at r = 0.709 across the LOCO folds; it now replicates on an unseen machine and tissue, in all three label spaces.
ALSO MEASURED: generalisation gap validation 0.7150 → ferguson 0.3309, +0.3841, against the +0.3179 LOCO mean. All three runs hit the 30-epoch ceiling, so the numbers are a LOWER BOUND.
Original design text below, unchanged.
WAS: 🟡 CODE COMPLETE, CPU SMOKE-TESTED, NOT YET SCORED (2026-08-11)
BUILT: pipeline2/s7_spaces.py (label spaces) + pipeline2/s7_eval.py (the run) + panel/gate7_expect.csv (10 declared checks incl. a predicted range) + kaggle/stage7.ipynb. Trains on ALL FIVE training cohorts, not LOCO, with Gate 6's shipped arm and nothing re-tuned. THREE label spaces per D-48 - A shipped 25, B1 clean 37, B2 clean 22 - because the H10 control showed A is not blind to the holdout. NOT YET BUILT and deliberately separated as Stage 7b: the abstain curve and the novel-class AUROC, both of which reuse Stage 7a's fitted models with no retraining.
Original design text below, unchanged.
WAS: ⚪ PLANNED, NOT BUILT — and it holds the ONLY untested row of the claim (file 10 §14)
⚠️ TWO THINGS ESTABLISHED 2026-08-11 THAT CHANGE HOW THIS STAGE IS READ.
(a) The ferguson class set is FRIENDLIER than the LOCO folds, not harder. Stage 7 trains on all 5 cohorts, so nothing is held out; ferguson's 9 labels map to 9 clusters and every one has training-cohort support (cluster 0/1/4/6 all five cohorts, 5 three, 21 two, 20 Keren only, 22 two). The 10-single-cohort-clusters problem that drags the LOCO macro-F1 down does not apply. Minus cluster 18, which is flagged unreliable, that is an 8-class problem with no unlearnable classes — so expect a HIGHER number than the LOCO 0.3901, and do not read a higher number as the pipeline suddenly working better.
(b) The label space is not blind to ferguson. Stage 1b clustered all 6 cohorts together (§7 gap 4 / H10). Run the 5-cohort re-clustering control BEFORE this fit, never after.
Implementation note: reuses s6_train.py's model and fit() almost unchanged. The new code is a ferguson-as-pure-test loader (no train/val/test split — every cell is test) plus the abstain and novelty scoring below. Declare thresholds AND a predicted range in panel/gate7_expect.csv first.
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

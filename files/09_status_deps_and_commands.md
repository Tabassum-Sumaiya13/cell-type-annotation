11. Implementation Status Checklist
Item	Status
✅	pipeline2/config.py — declarative registry, 6 cohorts + Danenberg spec	done
✅	pipeline2/loaders.py — one generic loader, no cohort branching	done
✅	pipeline2/acquire/ — download + extraction scripts, incl. sorin_extract.py	done
✅	Stage 0 s0_audit.py → GATE 0 PASS	done
✅	Stage 0b s0b_markers.py + panel/*.csv → GATE 0b PASS (5/5 checks)	done
✅	Stage 1 s1_values.py + nn/marker_encoder.py → GATE 1 PASS, winner V3	done
✅	Stage 1b s1b_labels.py + panel/gate1b_expect.csv → GATE 1b PASS (7/7, stroma waived)	done
✅	_validation/extract_hand_mapping.py + hand_mapping_reference.csv	done, retained
✅	Plan file updated with Stage 1b result, the waiver, and all three known gaps	done
❌	Stage 2 s2_tokens.py + nn/tokens.py + panel/gate2_expect.csv → GATE 2 FAIL	BUILT AND RUN. Checks 2/3/4 pass, check 1 FAILS on 1 kept pair (Keren MKI67, R² −0.0117, median 0.5122 vs a 0.10 floor). FAIL accepted and recorded, D-34 — the threshold was NOT moved to make it pass. Check 3, the H3 question, passes: full panel 0.1963 · core-9 control 0.1707 · Gate 1 0.169. Arm B ([ABSENT] tokens) ships, D-30. Report in reports/s2_masking.md
✅	Stage 3 s3_encoder.py + nn/encoder.py + panel/gate3_expect.csv → GATE 3 PASS	BUILT AND RUN, 25/25 folds, 39.8 min on a Kaggle T4. Ships λ = 0 — the plan's declared fallback (D-36). Cross-cohort macro-F1 0.3642 over 22 reliable clusters vs majority 0.0078 and random 0.0466. The adversary does not help: λ ≤ 0.03 are inside fold noise, λ ≥ 0.1 clearly worse. Two findings matter more than the verdict — the adversary HIDES rather than removes (D-37), and its domain is misspecified, being mostly patients rather than batches (D-38). Report in reports/s3_encoder.md
✅	Stage 3b — the ablation that closes D-37 and D-38	RUN. 45 runs, 3 arms x 3 lambdas x 5 folds, 80.2 min on a T4. BOTH RESCUE HYPOTHESES FAIL and λ=0 still ships (D-43). H5: matching the discriminator's capacity made hiding WORSE — fresh bits 2.92 at λ=0.3 vs 2.65 with the linear head, co-trained −4.53 vs −2.02. H6: the nested domain is worse at every lambda (−0.018, −0.031, −0.086) and the Sorin gain behind D-38 did not replicate. Best challenger +0.0063, inside the ±0.06 fold noise. Reports: s3b_d_/s3b_n_/s3b_nd_encoder_PARTIAL.md
❌	Stage 4 s4_spatial.py	DEFERRED (D-18)
❌	Stage 5 global slide branch	DROPPED (D-19)
✅	Stage 6 s6_train.py + nn/losses.py + panel/gate6_expect.csv → GATE 6 PASS	BUILT AND RUN. 16 fits, 73.5 min on a Kaggle T4. Ships the PROTOTYPE head with 2 LOSSES (cell-type + masked-marker) at LOCO macro-F1 0.3901 over the 22 reliable clusters. Check 1 PASS (largest log-sigma move 1.142 vs a cap of 3.0). Check 2 PASS (prototype floor 0.0359, no pair frozen; prototypes SPREAD 0.0717 → 0.9571). Check 3 drops VICReg (2 losses 0.3901 vs 3 losses 0.3788). Check 4 PASS by +0.0209 against a declared +0.02. ⚠️ READ D-44 BEFORE QUOTING CHECK 4: the margin is p = 0.460, 95% CI [-0.0501, +0.0919], and ALL of it comes from the Sorin fold (+0.1211) while the prototype head loses 3 of 5. The gate PASSES on its declared rule; it does NOT demonstrate that the prototype loss improves transfer. ❌ CHECK 6 IS A NO-OP (D-45) - the confidence arms are bit-identical because UPMC was held out on the fold that tests UPMC confidence. UNSCORED, not passed. Report in reports/s6_train.md
✅	Stage 7 s7_spaces.py + s7_eval.py + panel/gate7_expect.csv → GATE 7 DONE	BUILT AND RUN 2026-08-11. 3 fits, 20.0 min on a Kaggle T4. **ferguson zero-shot macro-F1 = 0.3309** over 22 reliable clusters in the shipped space, against majority 0.0237 and random 0.0562. Three spaces (D-48): A 0.3309 (25 clusters) · B1 0.3080 (37, clean) · B2 0.4240 (22, clean, matched cut). Check 0 asserted and printed on the Kaggle machine. Check 3's ordering prediction HOLDS; check 8's predicted range 0.35-0.55 is WRONG at 0.3309 and the reason is recorded. Check 4 prices the leak at -0.0931 - it PENALISED the shipped number, correcting D-46 (see D-51). THE FINDING IS NOT THE NUMBER: labels whose cluster is carried by >= 3 training cohorts average F1 0.5291, those carried by <= 2 average 0.0014, r = 0.843 on cohort count - Gate 6's support law replicating on an unseen machine and tissue (D-50). All three runs hit the 30-epoch ceiling, so these are a LOWER BOUND. Report: reports/s7_eval.md
❌	Stage 1b H10 control s1b_control.py + panel/gate1b_control_expect.csv → FAIL	BUILT AND RUN 2026-08-11, 3 min on CPU. Check 1 PASS (SIM/EV bit-identical, so ferguson never touched the signatures). Checks 2/3/4 FAIL: cell-weighted ARI 0.5447 against a declared 0.90, unweighted 0.5238 against 0.85, and only 3 of 9 ferguson-target clusters unbroken. THE THRESHOLDS WERE NOT MOVED (D-34). Diagnostics 7-9, added after the FAIL and marked as such, locate the mechanism: hold the cut at the shipped 0.800 and the weighted ARI is 0.9828 with 18 of 22 control clusters nesting cleanly, so the structure is stable and what moved is the GRANULARITY - the usable cut window narrows from 0.650-0.850 to 0.750-0.800 when a 6th cohort binds both guards. The shipped cut is still inside the 5-cohort window; the control prefers a different one by 0.0035 of stability (D-47). The script reproduces the shipped 25 clusters EXACTLY first (ARI 1.0000). D-46. Report: reports/s1b_control_ferguson.md
⚪	D-45 repair: re-run the confidence on/off pair holding out CRC instead of UPMC	not run - 2 fits, ~10 min on a T4. Until then check 6 is unscored and confidence weighting ships unmeasured
✅	Stage 7b s7b_abstain.py + panel/gate7b_expect.csv → GATE 7b	BUILT AND RUN 2026-08-11, minutes on CPU - no training, Stage 7a's models reloaded. ABSTAIN WORKS: ranking ferguson cells by distance to the nearest prototype lifts macro-F1 from 0.3309 at full coverage to a PEAK of 0.4204 at 35% coverage, and all 8 scored classes survive at every coverage down to 10%. NOVELTY FAILS: AUROC 0.578 on a genuinely novel type (ferguson EP, 5,488 cells, admitted by no cluster in space B2). Declared in advance that an AUROC near chance is a reportable FAILURE of the deliverable (check 6), and it is reported as one. Calibration T = 1.10-1.15, fitted on training-cohort held-out slides only. D-52. Report: reports/s7b_abstain.md
✅	Step 4 s8_perclass.py → per-class reporting and the learnable/unlearnable split	BUILT AND RUN 2026-08-11, NO COMPUTE - existing checkpoints re-reported, no verdict moves. Gate 6 LOCO 0.3901 reported → 0.4606 learnable-only; 9 of 55 class-folds are unlearnable by construction. THE SUPPORT LAW ON THE LOCO FOLDS: 0 cohorts → 0.0000 (100% exactly zero) · 1 → 0.0921 (50% zero) · 2 → 0.2231 (22% zero) · 3+ → 0.6361 (0% zero, none of 29). r = 0.781. H7 CONFIRMED AND CLOSED exactly as files/07 asked - CRC ranks 2nd of 5 on learnable classes, not last. D-53. Report: reports/s8_perclass.md
🟡	Step 3 s8_seeds.py + kaggle/stage8.ipynb → repeated seeds and confidence intervals (H9)	CODE COMPLETE, CPU SMOKE-TESTED, NOT YET RUN. 55 fits, ~3.5-4 h on a T4. 5 seeds x 5 LOCO folds x 2 heads (proto, linear) + 5 seeds on ferguson. Settles three things: the Gate 6 LOCO headline, Gate 6 check 4 (the sentence D-44 BANNED), and the support law - which is the strongest result in the project and so far rests on 9 ferguson labels from one fit. Resumes fit by fit, so a session timeout costs only the fit in flight. Nothing is re-tuned and no verdict can move; only which SENTENCES may be written
✅	Stage 9 s9_newcohort.py — Danenberg arrival test (D-24) on a 7th cohort	BUILT AND RUN 2026-08-14, score-only by user decision (no gate9_expect.csv, no report file; numbers live in D-54). NO TRAINING — s7_A.pt / s7_B2.pt loaded and run forward. Space A 0.2161 reliable / 0.1774 all over 9 scored clusters; space B2 0.2944 / 0.2309 over 7; majority 0.0430 / 0.0683. 40,000-cell draw from 1,123,466 cells. ONLY 24 of 99 vocabulary slots are filled by Danenberg, and that — not training support — is what limits the number: the support-law correlation falls to 0.295 (A) / 0.278 (B2) against ferguson's 0.843. 3 labels NOVEL in A, 4 in B2, reported not forced. Check 2 PASS: all 106 existing signatures bit-identical after adding a 7th cohort. ⚠️ THE LABEL PLACEMENT VISIBLY FAILED on a thin panel — five epithelial/stromal labels were all put in `PECAM1+ CD34+ VIM+`, a cluster named for three markers Danenberg does not measure, and Endothelial went to a stromal cluster because CD31-vWF resolves to VWF (D-55). D-54
✅	Stage 10 s10_external.py — THE EXTERNAL BASELINE (H13a CLOSED, D-50 commitment met)	BUILT AND RUN 2026-08-14, 25 fits, ~41 min CPU, check 0 PASS. **Stage 6 0.3901 beats every baseline**: maps_core9 0.3447 · gbm_core9 0.3245 · gbm_full99 0.3233 · maps_full99_area 0.2306 · maps_full99 0.2116. Paired per fold: +0.0454 [+0.0054, +0.0766] over the best (4/5 folds); only gbm_full99's interval spans zero (3/5). ⚠️ +0.0454 conflates PANEL WIDTH with architecture — 99 markers vs 10 — and a bootstrap on n=5 undercovers; quote "4 of 5 folds, smallest margin +0.005". THE BIG ROW: maps_core9 0.3447 → maps_full99 0.2116 (−0.133) is the first EXTERNAL evidence for Stage 2's premise that a zero-fill lies about unmeasured markers. gbm_full99 beats the shipped model on Keren and Phillips and collapses on Sorin/UPMC. D-57. Report: reports/s10_external.md
	WAS	BUILT, CHECK 0 PASSING, RUNNING 2026-08-14. MAPS (Shaban et al., Nat Commun 2023) reimplemented from its published Methods: 4x512 FC, ReLU, dropout 0.10, softmax, Adam 1e-3, batch 128, early stop on val loss. 5 arms x 5 LOCO folds on IDENTICAL folds, cells, label space, slide splits and waiver — asserted element-by-element against s6.load_cohort, not assumed. Arms: maps_core9 · maps_full99 · maps_full99_area · gbm_core9 · gbm_full99. `full99` sets unmeasured markers to ZERO, so the core9→full99 gap measures Stage 2's founding claim against an outside architecture. NO PASS/FAIL — whatever it returns is reported, including a tree beating the transformer (D-50). ⚠️ the 3-epoch smoke test already put maps_core9 at ~0.337 vs Gate 6's 0.3901. ~1.5-2.5 h on CPU. D-57
🟡	Stage 11 s11_spacetest.py — derived vs curated label space (H13b, the thesis claim as an outcome)	BUILT AND SPACES CONSTRUCTED 2026-08-14; the 9 LOCO fits NEED A GPU and are not run. 3-fold LOCO over CRC/Keren/UPMC — the only trainable cohorts the hand mapping covers — with BOTH arms restricted to those 3 and scoring IDENTICAL cells (55 shared labels). Three spaces: hand 24 classes · derived 54 · matched 25. Prototypes for every arm from the same function so no arm gets a better init. ⚠️ A FINDING LANDED BEFORE ANY MODEL RAN: on 3 cohorts NO cut satisfies Stage 1b's three hard guards, so the method cannot choose a granularity at all and collapses to near-singletons. Granularity selection fails below 5 cohorts (H11 escalating); only the `matched` arm's comparison to `hand` is meaningful. D-58
✅	Stage 12 s12_ontology.py — EXTERNAL VALIDATION OF THE LABEL SPACE (H15 CLOSED, M6 SETTLED, H2 answered)	BUILT AND RUN 2026-08-14, minutes, CPU, no GPU and no training. 25 clusters scored against the Cell Ontology; all 106 labels mapped (Phillips and Sorin for the first time), 101 resolved to 33 CL terms. Gate declared before the run in panel/gate12_expect.csv. CHECK 0 PASS — 30 pipeline modules scanned with comments and strings stripped, none names a CL term or reads the scoring set, so D-4 and files/02 2.1 hold. **ARI 0.4400 [0.3662, 0.6624] per label · 0.5725 reliable-only · 0.934 cell-weighted**, against the project's own hand mapping at 0.596 / 0.962. Beats a 1000-shuffle null at p99.9 at all four of CL's OWN published levels. FIRST GATE IN THE PROJECT WITH A CONFIDENCE INTERVAL AND A NULL. ❌ Nesting layer fails its first external test (4b 0.282 vs bar 0.60) and same-term merging misses too (4a 0.645 vs 0.90). ✅ CL places Phillips|tumor cells and CRC|tumor cells DISTANT and Stage 1b splits them — an outside referee agrees on the hardest case in the project. M6 settled: L1 0.629 → 0.9927 many-to-one, an artefact. Check 5a's declared prediction is WRONG and recorded. D-59. Report: reports/s12_ontology.md
⚪	Ablation: do co-expression + log-prevalence earn their place? (§7 gap 1)	not run
⚪	Re-test the nesting layer (§7 gap 2)	not run
⚪	Wire up or delete --evidence-sweep / --graph-check (§7 gap 3)	not done
12. Dependencies
Package	Purpose	Status
requests	HGNC + UniProt REST in Stage 0b. Used once, then the cached work/marker_registry.csv makes every later run offline. Kaggle has internet off by default, so the cache is not optional	installed
networkx	The Stage 1b nesting DAG, SCC contraction, acyclicity assert	installed
leidenalg	No longer used — Leiden was replaced by scipy.cluster.hierarchy average linkage (D-22)	installed but unused
scipy	cluster.hierarchy.linkage/fcluster, spatial.distance.squareform, optimize.linear_sum_assignment, stats.rankdata	installed
torch 2.12.0+cpu	Stages 1, 2, 3, 6	installed, no CUDA
pandas, numpy, matplotlib (Agg)	throughout	installed
sentence-transformers (~90 MB)	Optional, naming only. α = 0, so the pipeline runs correctly without it	not required
torch_geometric	Not needed — Stage 4 uses plain scatter ops, and it is not available on Kaggle by default	not installed, by design
13. Verification Commands

python pipeline2/s0_audit.py --all              # gate 0  : counts + tissue plots
python pipeline2/s0b_markers.py --resolve       # gate 0b : HGNC/UniProt resolution + review queue
python pipeline2/s0b_markers.py --offline       # gate 0b : must reproduce byte-identically
python pipeline2/s1_values.py  --bakeoff        # gate 1  : V1 vs V2a vs V2b vs V3, scored LOCO
python pipeline2/s1b_labels.py                  # gate 1b : all 7 checks in one report
#   NOTE: --evidence-sweep and --graph-check are accepted but currently DO NOTHING - every run
#   emits the full report. See section 7, gap 3.
python pipeline2/s2_tokens.py  --build          # wide value tables + dynamic range + panel.json
python pipeline2/s2_tokens.py  --check          # gate 2  : reconstruction R2 vs the training MEAN (D-26)
#   --refit ignores the checkpoint cache; --holdout-epochs N raises the ceiling for the two
#   holdout arms only. Arm B needed 47 epochs, so the original 30 was binding.
python pipeline2/s3_encoder.py --lambda-sweep   # gate 3  : LOCO F1 + retained bits (fresh probe)
#   --quick smoke test · --lambdas 0,0.03,0.3 narrower grid · --folds CRC,Sorin split across
#   sessions (restricts which cohort is HELD OUT, never which are trained on) · --cpu forces CPU.
#   A partial run writes reports/s3_encoder_PARTIAL.md and is not a gate result.
python pipeline2/kaggle/make_upload.py          # build the 77 MB Kaggle dataset for the gate 3 run
# python pipeline2/s4_spatial.py --ablate       # gate 4  : DEFERRED - not built this pass
python pipeline2/s1b_control.py                 # H10 control: re-cluster without the frozen holdout
#   ~3 min CPU. Reproduces the shipped 25 clusters exactly, then re-runs the chain on 5 cohorts.
#   Writes reports/s1b_control_ferguson.md. Thresholds in panel/gate1b_control_expect.csv.
python pipeline2/s6_confidence.py               # one-off: label-confidence sidecar (UPMC only)
python pipeline2/s6_train.py   --ablate-losses  # gate 6  : 2 vs 3 losses (D-40), prototype drift
#   --quick smoke test · --folds CRC,UPMC subset · --refit ignore cache · --cpu · --no-warm
#   16 runs: proto+VICReg, proto only, linear control (5 folds each) + 1 confidence-off on UPMC
python pipeline2/s7_spaces.py --build           # build the two CLEAN label spaces + prototypes
python pipeline2/s7_eval.py --frozen-test ferguson          # gate 7, all three spaces
#   --spaces A|B1|B2 subset · --quick smoke test (scores nothing) · --refit ignore cache · --cpu
#   --report re-renders reports/s7_eval.md from cached checkpoints, no refit
python pipeline2/s7b_abstain.py                 # gate 7b : abstain curve + novel-class AUROC
#   No training. Reloads work/ckpt/s7_*.pt and runs forward. Minutes on CPU.
python pipeline2/s8_perclass.py                 # step 4  : per-class + learnable/unlearnable
#   No compute at all. Re-reports s6_sweep.pt and s7_A.pt. Closes H7.
python pipeline2/s8_seeds.py --loco --frozen    # step 3  : 55 fits, ~4 h on a T4 (H9)
#   --seeds N · --quick · --report re-renders from cached fits · --refit · --cpu
#   Resumes fit by fit. kaggle/stage8.ipynb wraps it.
#   3 fits, ~20-25 min on a T4. Needs work/values/ferguson_full.parquet (D-49).
python pipeline2/s9_newcohort.py --cohort Danenberg --prepare   # stage 9 : stages 0/0b/1/2 for a new cohort
python pipeline2/s9_newcohort.py --cohort Danenberg --spaces A,B2
#   No training. Intersects the new cohort's markers with the FROZEN 99-triple vocabulary, places
#   its labels into the frozen partition by the s7_spaces rule, then runs s7_*.pt forward.
#   Writes work/s1b_signatures_plus.npz (7 cohorts) — the shipped npz is never touched.
python -u pipeline2/s10_external.py             # H13a : MAPS + gradient boosting, identical folds
#   --arms maps_core9,gbm_core9 subset · --quick smoke test. ~1.5-2.5 h on CPU, 25 fits.
#   USE -u: without it stdout buffers and a 2-hour run shows nothing until it exits.
python pipeline2/s11_spacetest.py --build       # H13b : build the 3 label spaces, train nothing
python pipeline2/s11_spacetest.py               # H13b : 9 LOCO fits — NEEDS A GPU, use Kaggle
#   --quick smoke test · --refit ignore the per-fold cache.

python _validation/fetch_ext.py                 # H15 : vendor cl.obo + CellMarker 2.0 to work/ext/ (needs internet, once)
python _validation/build_cl_mapping.py --show    # H15 : resolve the 106 labels to CL terms, print, write nothing
python _validation/build_cl_mapping.py           # H15 : freeze _validation/cl_mapping.csv + its meta/sha
python pipeline2/s12_ontology.py                 # H15 : score the 25 clusters against the Cell Ontology, CPU, minutes
#   --quick 50 permutations instead of 1000. Run the three above IN ORDER; s12 asserts the mapping's sha matches.
Other useful commands:


python _validation/extract_hand_mapping.py      # regenerate the Gate 1b scoring set from git
python pipeline2/s1_values.py --rebuild         # rebuild value tables from scratch
git show HEAD:pipeline/step4_labels.py          # the old hand-written ontology (T and NAT dicts)
git show HEAD:pipeline/panel/never_merge.csv    # the 9 look-alike pairs
git show HEAD:kaggle/INSTRUCTIONS.md            # the old Kaggle path

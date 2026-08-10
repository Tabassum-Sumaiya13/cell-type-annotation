14. The Claim, and What Would Falsify It
The claim is proven only if all of the following hold:

Stage 0b resolves ≥90% automatically with all 9 never_merge pairs kept apart. ✅ 100%, 9/9
Gate 1 picks a normalisation that survives the composition-skew check and wins on LOCO, not on held-out cells. ✅ V3
Gate 1b agreement ≥0.90 with the hard cases correct and the nesting graph asserts acyclic. ✅ 0.928, 4/5 required + 1 waived, DAG asserted — with the caveats in §7
Stage 2 dynamic tokens beat the fixed core. ⚪ not run
LOCO macro-F1 beats 0.630. ⚪ not run
The ferguson zero-shot number is reported whether or not it is good. ⚪ not run
(The Stage 4 shuffle control is deferred with Stage 4.)

Comparison baselines: old pipeline 0.630 mean L1 macro-F1; published MAPS cross-dataset 0.5–0.6. State the cluster count next to any number — the class set is now data-derived, so the comparison is indicative, not exact.

15. Risk Register
Risk	Why it matters	Mitigation	Status
HGNC/UniProt return a wrong or ambiguous hit	A silently wrong marker id corrupts everything downstream	Field-scoped queries, spellings must agree, ambiguous → review queue	✅ handled; 0 leaks measured
Marker resolution drifts between runs	APIs change; results stop reproducing	Resolve once, cache, and Gate 0b requires a byte-identical offline re-run	✅ verified
All normalisation variants fail the skew check	Composition-skewed slides could break every option	Report it and use V3, which cannot invent a negative population	✅ V3 passed
Gate 1b agreement < 0.90	The biggest single change; if wrong, everything downstream is wrong	Inspect disagreements first — some will be the hand mapping being wrong. Fallback: hand mapping for the 4 old cohorts + automatic for the new	✅ 0.928
Too many label pairs below the evidence floor	Sorin has only 17 markers; the graph could fragment	Gate 1b prints the never-comparable share and sweeps k. Marker-rich cohorts bridge	✅ 100% directly comparable — but this also means the bridging mechanism was never exercised (§7 gap 1)
The label graph has cycles or contradictory nesting	A cyclic "hierarchy" is not a hierarchy	Margin rule kills 2-node cycles; SCC contraction gives a DAG by theorem; assert is_directed_acyclic_graph	✅ asserted — but weak evidence, the graph was too sparse to test it (§7 gap 2)
FiLM memorises cohort instead of slide drift	Would re-inject what Stage 3 removes	Within-cohort standardisation, ±30% output bound, V2a vs V2b raced on LOCO	✅ moot — FiLM lost
[ABSENT] tokens act as a panel fingerprint	Would hand Stage 3's adversary a problem it should not have	Gate 2 check 4: measured ablation + cohort probe	🟡 open, H1
A new cohort's labels are too coarse to cluster	e.g. only immune/stromal/tumour	Its labels join the coarse clusters; it contributes cells to training but not fine-level scoring. Reported per cohort	⚪ not yet hit
Prototypes collapse during training	Two classes silently merge and F1 still looks fine	Gate 6 collapse guard: track minimum pairwise distance, freeze and log violations	⚪ planned
Gate 3 fails at every λ	Cohort and biology may still be too tangled	Fall back to λ=0 and report it	⚪ planned
Sorin has only 17 markers	Could drag the shared panel down	It is the panel-mismatch stress test. Track its fold separately; the masked-token design exists for this	⚪ Stage 2
Breast tissue imbalance	—	Deliberate: same tissue on different machines separates batch from biology. Report per-tissue results	⚪ weakened by D-24 (Danenberg out of training)
Kaggle quota 30 h/week	The final run could be cut off	Checkpoint every epoch; the LOCO loop resumes fold by fold	⚪ planned
Stroma clusters are unreliable	8.5% of cells, 3 clusters, 23 labels	Flagged in label_map.csv; Stage 7 must exclude or separately report	✅ flagged, ⚪ Stage 7 must honour it
16. Immediate Next Actions
Confirm the Stage 2 design with the user (§4.6) — especially the [ABSENT] ablation (H1) and the declared Gate 2 thresholds. The user's standing rule is: confirm before every run and every decision.
Record D-24 (Danenberg as arrival test) in the plan file — this had not yet been written down when the conversation ended.
Write pipeline2/nn/tokens.py and pipeline2/s2_tokens.py, then run Gate 2.
Consider running the cheap §7 gap-1 ablation (co-expression / prevalence) while Stage 2 trains, since it costs one extra column.

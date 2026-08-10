7. Known Gaps in the Stage 1b Build — open, not fixed
Recorded so the gate result is not read as a claim that every part of M1–M4 is doing work. All three were admitted to the user and are written into the plan file.

M1's co-expression and log-prevalence are computed, stored, and never used.
The co-expression matrix is written into work/s1b_signatures.npz and reaches containment as CX, but its only consumer is an optional coex_gate argument that nothing calls. Log prevalence is not in the distance at all.
The plan's M1 claims both are part of the signature, and its Cap-4 answer credits co-expression with rescuing thin marker overlap. Neither claim is currently supported by a measurement.
It is untested rather than disproven — no ablation was run. Cheap to settle: the ablation is one extra column. On this roster it should not matter much, because check 3 measured 100% of label pairs directly comparable, so the thin-overlap case co-expression exists for never actually fires. That changes when a marker-poorer cohort is added.

The nesting layer missed every case declared for it.
All three of nest_tcell, nest_treg, nest_tumour_ki67 failed to come out as nesting (two found no edge, one merged instead). They are required=0 so they do not block, and check 5 still reports 22 edges — but the edges it finds are not the ones predicted.
The nesting layer is the weakest part of the stage and must not be relied on by Stage 6's descendant-tolerant loss until re-tested.
Check 7's DAG assert (0 cycles, 0 transitivity violations) is correspondingly weak evidence: the graph is sparse enough that the M2b machinery had nothing to repair.

--evidence-sweep and --graph-check do nothing.
Both are parsed into only and then ignored; every invocation produces the full report. The module docstring and the plan's verification command list both claim they subset it. Either wire them up or drop them.

8. Open Questions
8.1 High Priority (blocking research)
#	Question	Why blocking
H1	Is the [ABSENT] token a panel fingerprint? The plan mandates it; the analysis in §4.6 argues it hands Stage 3's adversary a problem it should never have.	Determines Stage 2's architecture and how hard Stage 3 has to work. Designed as a measured ablation (Gate 2 check 4); not yet run.
H2	Does the nesting layer actually work? All three declared cases failed.	Stage 6's descendant-tolerant loss depends on it. Cannot be built on an untrusted graph.
H3	Do dynamic tokens beat the fixed 9-marker core? (Gate 2 check 3, target LOCO R² ≥ 0.169.)	If not, Stage 2's complexity is not earned and the whole masked-token design is in question.
8.2 Medium Priority (important improvements)
#	Question
M1	Do co-expression and log-prevalence earn their place? One ablation column settles it (§7 gap 1). Should be run before a marker-poorer cohort is added, because that is when it starts to matter.
M2	Danenberg's three unresolved follow-ups — the duplicate HER2 triple policy, the CD31-vWF co-stain decision, and the bare-SMA → SMN1 alias risk (§3.3). All must be settled before the arrival test runs.
M3	What is the right tie_mass exclusion threshold for Stage 2? Declared at 0.5 with a sweep, but never measured.
M4	Will UPMC's assumed µm/px matter? Only Stage 4 (deferred) uses physical distance. Low risk while Stage 4 is off.
M5	Should _validation/ ever be deleted? Currently retained. The plan says delete after Gate 1b; the deviation is deliberate and documented.
8.3 Low Priority (future ideas)
#	Idea
L1	Report a Cell Ontology id per final cluster in the write-up only. Do not use CL anywhere in the pipeline, but reviewers compare across papers with those ids. Costs one lookup table at the end and keeps the pipeline pure.
L2	Wire up or delete --evidence-sweep / --graph-check (§7 gap 3).
L3	Revisit Stage 4 (spatial) after Stage 7 works.
L4	Revisit Stage 5 (global slide branch) as a final ablation only.

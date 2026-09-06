17. Resume Project
Prompt for a fresh session — paste this verbatim.

I am building a dynamic cross-cohort cell-type annotation pipeline for spatial proteomics data, in pipeline2/ inside d:\Desktop\FYDP\FYDP final works\cell type annotation. It replaces an older pipeline (still in git HEAD:pipeline/) that plateaued at 0.630 mean L1 macro-F1.

Read CANONICAL_PROJECT_STATE.md (this document) first. It is the complete project knowledge base — you do not need any prior conversation. The living plan file is C:\Users\User\.claude\plans\ah-my-apologies-you-sunny-hennessy.md.

How I work with you — these are hard rules:

Write in plain, simple English. Explain any technical term the first time. English is my second language.
Short sentences, short paragraphs, bullets where they help. No corporate language, no jargon.
Confirm with me before every run and every decision.
One report per piece of work. Reports go in reports/ as markdown, written for a reader, not as a log.
Recommend the best solution, not a menu. Challenge my approach if there is a better one, and say why.
For code problems: tell me what is wrong → why → the best fix → the corrected code → the side effects.
Do not spawn subagents and do not use workflows unless I explicitly ask.
The method — non-negotiable:

Every stage has a concrete pass/fail gate declared before the run, written into a CSV in pipeline2/panel/ where possible so results cannot be judged after the fact.
Nothing proceeds until its gate passes.
When a check and an argument disagree, the check wins. Several design decisions in this project were reversed by measurement — that is the expected behaviour, not a failure.
When something fails, diagnose it, record it visibly, and do not retune thresholds to make it pass.
Where things stand (2026-08-10):

✅ Stage 0 (audit), 0b (marker identity via HGNC/UniProt triple key), 1 (value harmonisation, winner V3 = per-cohort ECDF), 1b (automatic label alignment, 0.928 agreement with the hand mapping — the ontology is dead) all built and passing.
🟡 Stage 2 (tokenisation + masking) is designed but not written. The design and its four declared Gate 2 checks are in §4.6 of the canonical document. It needs my confirmation before you build it.
❌ Stage 4 deferred, Stage 5 dropped.
⚪ Stages 3, 6, 7 planned.
Before you propose anything, read §10 "Do Not Repeat" and §6 "Already Investigated". Sixteen ideas have already been tested and rejected with evidence, including text embeddings for label alignment, FiLM, Leiden, per-image ranking, and containment-as-merging-statistic. Do not re-propose them.

Three open gaps in Stage 1b you must not paper over (§7): co-expression and log-prevalence are stored but unused; the nesting layer missed all three declared cases and must not be trusted by Stage 6 until re-tested; and two CLI flags do nothing.

One permanent measured limitation (§6.4): the stroma hard case FAILED and was waived, not passed, because no fibroblast-specific marker exists anywhere in the roster. 3 clusters / 23 labels / 420,862 cells (8.5%) are flagged unreliable in work/label_map.csv. Stage 7 must exclude them from the headline number or report them separately.

Danenberg (1,123,466 cells, IMC breast, downloaded and spec-registered) is deliberately not in the training roster. By my decision it is the "new cohort arrives later" test — the live demonstration that adding a cohort needs no code change. Three follow-ups must be settled before it runs: the duplicate HER2 triple, the CD31-vWF co-stain, and the bare-SMA → SMN1 alias risk (§3.3).

Start by confirming the Stage 2 design with me, and by writing decision D-24 (Danenberg as arrival test) into the plan file — it was decided but never recorded there.

Appendix A — Things explicitly marked UNKNOWN
Stage 2 runtime figures (~20–40 s/epoch, ~70–80 min total) are estimates from a FLOP calculation, not measurements. Nothing has been run.
Gate 2 thresholds (median kept-marker R² ≥ 0.10, tie_mass ≥ 0.5) are declared judgements, never validated.
UPMC's µm/px (0.3774) is explicitly recorded in config.py as ASSUMED - not published anywhere.
The number of Stage 1b nesting edges that are biologically correct is unknown — 22 edges were found, but all three predicted edges were missed, and no independent check of the 22 was run.
Whether co-expression or log-prevalence would help is untested, not disproven. No ablation was run.
Sorin's channel count is reported as 18 in the Gate 0 table and 17 protein triples after Stage 0b filtering; the difference is the non-protein channel(s). Both numbers appear in this document and are consistent, not contradictory.

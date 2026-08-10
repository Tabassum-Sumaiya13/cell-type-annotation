# Project: Cross-cohort cell-type annotation (spatial proteomics)

This file is short on purpose. It is read automatically every session.
The full project history lives in `project_state/`, split into files so you
only load what a given task needs. Do not read all of them by default —
use the table below to pick the right one(s).

## One-paragraph orientation

Building a model that labels every cell in a spatial-proteomics tissue image
(T cell, tumour cell, fibroblast…) and still works on a hospital/machine/panel
it has never seen. Central claim: label harmonisation across cohorts can be
learned from marker profiles instead of a hand-written ontology. Repo:
`pipeline2/`. Old pipeline (plateaued at 0.630 macro-F1) is still in
`git HEAD:pipeline/`, kept only as a comparison baseline — do not build on it.

Status as of the last update (see file 09 for the live checklist):
Stages 0, 0b, 1, 1b built and passing their gates. Stage 2 designed, not built.

## File index — load only what the task needs

| File | Contains | Load when you're about to... |
|---|---|---|
| `01_header_and_rules.md` | Doc purpose, maintenance rules, repo/status header | Rarely — only if unsure how this doc system works |
| `02_goal_and_constraints.md` | Project goal, thesis framing, ALL permanent constraints (research/data/compute/communication/tooling) | Almost always worth a skim — these are non-negotiable rules that apply to every task |
| `03_data_roster.md` | Cohorts, cell counts, pixel sizes, Danenberg status, rejected datasets | Working with data loading, a specific cohort, or dataset questions |
| `04a_pipeline_folder_layout_stage0_0b.md` | Folder layout, Stage 0 (audit), Stage 0b (marker identity) | Touching acquisition, marker-name resolution, or repo structure |
| `04b_pipeline_stage1_and_1b.md` | Stage 1 (value harmonisation) and Stage 1b (label alignment) — the core proven result | Touching normalisation or label alignment; understanding the central experiment |
| `05_pipeline_planned_stages_2_to_7.md` | Designs for Stage 2 (tokenisation, next up) through Stage 7 | Building Stage 2 onward |
| `06_rejected_and_investigated.md` | Rejected designs, already-investigated ideas (don't repeat) | Before proposing any new design |
| `07_gaps_and_open_questions.md` | Known unresolved gaps, open questions | Before trusting Stage 1b outputs downstream |
| `08_decision_log_and_do_not_repeat.md` | Dated decision log (D-1...), explicit "do not repeat" list | Before proposing anything that sounds like a past idea; when recording a new decision |
| `09_status_deps_and_commands.md` | Implementation checklist, dependencies, verification commands | Checking what's built, or running verification |
| `10_claim_risk_and_next_actions.md` | Falsification checklist for the thesis claim, risk register, immediate next actions | Planning what to do next |
| `11_resume_prompt_and_appendix.md` | The original resume prompt, appendix of explicitly UNKNOWN items | Rarely — historical reference only |

## Update protocol (every session, before ending)

These docs are the single source of truth and must stay current. Follow the
maintenance rules in `01_header_and_rules.md`: **never delete or silently
rewrite** — mark old entries `Accepted / Replaced / Deprecated / Rejected`
and say what replaced them and why.

1. **New decision made?** → append a dated entry to
   `08_decision_log_and_do_not_repeat.md` (next D-number).
2. **A stage's status changed (built, gate passed/failed)?** → update
   `09_status_deps_and_commands.md` (checklist) AND the relevant `04x`/`05`
   file's status marker (✅/🟡/⚪/❌), plus the one-line status in this
   `CLAUDE.md` header above.
3. **A design was tried and rejected?** → add it to
   `06_rejected_and_investigated.md`, don't just delete it from wherever it was.
4. **A new gap or open question surfaced?** → add to
   `07_gaps_and_open_questions.md`.
5. **Risk status changed?** → update `10_claim_risk_and_next_actions.md`.
6. Keep edits inside the correct numbered file — do not grow this index file
   itself beyond an index. If a file grows past ~250 lines, split it further
   and add the new file to the table above.
7. Confirm every substantive edit with the user first (standing rule, see
   `02_goal_and_constraints.md` §2.4) before writing it.

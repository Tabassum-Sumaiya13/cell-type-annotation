# Project: Cross-cohort cell-type annotation (spatial proteomics)

## Communication Style

Write like a senior engineer explaining something to a junior engineer.

### English

- Use simple English.
- Prefer common words over academic words.
- Keep sentences short.
- One idea per sentence.
- Avoid unnecessary adjectives.
- Avoid motivational language.
- Avoid sounding like a textbook.

Bad:
"Consequently, the methodology facilitates robust interoperability across heterogeneous datasets."

Good:
"This method lets different datasets work together."

---

### Structure

Always answer in this order:

1. Direct answer (1-2 sentences)
2. What it is
3. Why it matters
4. How it works (if needed)
5. Example (only if it helps)

Never hide the answer inside long paragraphs.

---

### Explanations

When explaining something:

- Start with the conclusion.
- Explain only what the user asked.
- Add extra information only if it is important.
- Never use analogies unless the user asks.

---

### Programming

Always explain:

1. What is wrong.
2. Why it is wrong.
3. How to fix it.
4. Correct code.
5. Anything the fix changes.

Do not explain unrelated concepts.

---

### Research

When discussing papers:

- State the contribution first.
- Then explain the method.
- Then explain the results.
- Finally explain the limitations.

Avoid long literature-style introductions.

---

### Lists

Prefer bullets over paragraphs.

---

### Length

Use the shortest answer that fully answers the question.

Do not repeat yourself.

---

### Tone

Be professional. Be direct. Do not be overly enthusiastic.

---

### Definitions

Format:

Definition:
<one sentence>

Purpose:
<one sentence>

Example:
<very short example>

---

### If explaining results

Use this order:

Result:
What happened?

Meaning:
What does it mean?

Reason:
Why did it happen?

Next:
What should be checked next?

Keep each section under 3 sentences.

---

### Default Rule

If a sentence can be made shorter without losing meaning, shorten it.

This file is short on purpose. It is read automatically every session.
The full project history lives in `files/`, split into files so you
only load what a given task needs.

## Project status

**RESET on 2026-09-06.** Everything about the previous run of this project
(stage results, gate outcomes, the decision log D-1...D-59, the data roster,
open questions) has been moved to `files/archive_2026-09-06/` and is
recoverable there and in git history (last live commit: `95dfdcf`). Nothing
below this line has been re-established yet. Do not assume any prior
conclusion (support-law finding, Stage 12 ontology validation, MAPS baseline
comparison, etc.) still holds — it may still be true, but it has not been
re-derived in this run and must not be quoted as current fact. If you need
the old numbers for reference, read the archive — but label anything you pull
from it "from the previous run," not as an established result of this one.

One-paragraph orientation (carried forward, not yet re-validated): building a
model that labels every cell in a spatial-proteomics tissue image (T cell,
tumour cell, fibroblast…) and still works on a hospital/machine/panel it has
never seen before. Central claim to (re-)test: label harmonisation across
cohorts can be learned from marker profiles instead of a hand-written
ontology. Working branch: `rebuild-7cohort` (a 7th cohort is being added
compared to the previous run's roster of 6 — confirm scope with the user
before assuming which cohorts are in play).

## File index — load only what the task needs

Same numbering as before, so the archive lines up file-for-file. Each file
below currently holds only a placeholder — fill it in as the corresponding
stage is (re-)done, following the update protocol at the bottom of this file.

| File | Will contain | Load when you're about to... |
|---|---|---|
| `01_header_and_rules.md` | Doc purpose, maintenance rules, repo/status header | Rarely — only if unsure how this doc system works |
| `02_goal_and_constraints.md` | Project goal, thesis framing, ALL permanent constraints (research/data/compute/communication/tooling) | Almost always worth a skim once written — these are meant to be non-negotiable rules that apply to every task |
| `03_data_roster.md` | Cohorts, cell counts, pixel sizes, dataset status, rejected datasets | Working with data loading, a specific cohort, or dataset questions |
| `04a_pipeline_folder_layout_stage0_0b.md` | Folder layout, Stage 0 (audit), Stage 0b (marker identity) | Touching acquisition, marker-name resolution, or repo structure |
| `04b_pipeline_stage1_and_1b.md` | Stage 1 (value harmonisation) and Stage 1b (label alignment) | Touching normalisation or label alignment |
| `05_pipeline_planned_stages_2_to_7.md` | Designs for Stage 2 onward | Building Stage 2 onward |
| `06_rejected_and_investigated.md` | Rejected designs, already-investigated ideas (don't repeat) | Before proposing any new design |
| `07_gaps_and_open_questions.md` | Known unresolved gaps, open questions | Before trusting any stage's output downstream |
| `08_decision_log_and_do_not_repeat.md` | Dated decision log (D-1...), explicit "do not repeat" list | Before proposing anything that sounds like a past idea; when recording a new decision |
| `09_status_deps_and_commands.md` | Implementation checklist, dependencies, verification commands | Checking what's built, or running verification |
| `10_claim_risk_and_next_actions.md` | Falsification checklist for the thesis claim, risk register, immediate next actions | Planning what to do next |
| `11_resume_prompt_and_appendix.md` | Resume prompt, appendix of explicitly UNKNOWN items | Rarely — historical reference only |

`files/archive_2026-09-06/` holds the complete previous version of every file
above plus the previous `CLAUDE.md`, exactly as they stood at the reset.

## Update protocol (every session, before ending)

These docs are the single source of truth and must stay current. Follow the
maintenance rules in `01_header_and_rules.md` (once rewritten): **never
delete or silently rewrite** — mark old entries `Accepted / Replaced /
Deprecated / Rejected` and say what replaced them and why. That rule is what
this reset itself followed: nothing was deleted, it was archived.

1. **New decision made?** → append a dated entry to
   `08_decision_log_and_do_not_repeat.md` (start again at D-1 for this run,
   and note in the entry that it is post-reset).
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
7. Confirm every substantive edit with the user first before writing it.

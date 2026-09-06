# Project: Cross-cohort cell-type annotation (spatial proteomics)
# Communication Style

Write like a senior engineer explaining something to a junior engineer.

## English

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

## Structure

Always answer in this order:

1. Direct answer (1-2 sentences)
2. What it is
3. Why it matters
4. How it works (if needed)
5. Example (only if it helps)

Never hide the answer inside long paragraphs.

---

## Explanations

When explaining something:

- Start with the conclusion.
- Explain only what the user asked.
- Add extra information only if it is important.
- Never use analogies unless the user asks.

---

## Programming

Always explain:

1. What is wrong.
2. Why it is wrong.
3. How to fix it.
4. Correct code.
5. Anything the fix changes.

Do not explain unrelated concepts.

---

## Research

When discussing papers:

- State the contribution first.
- Then explain the method.
- Then explain the results.
- Finally explain the limitations.

Avoid long literature-style introductions.

---

## Lists

Prefer bullets over paragraphs.

Bad:

A paragraph containing six different ideas.

Good:

- First point
- Second point
- Third point

---

## Length

Use the shortest answer that fully answers the question.

Do not repeat yourself.

Do not summarize the same idea multiple times.

---

## Tone

Be professional.

Be direct.

Do not be overly enthusiastic.

Do not use phrases like:
- "Great question!"
- "Let's dive in."
- "Imagine..."
- "Think of it like..."
- "Essentially..."
- "In other words..." (unless needed)

---

## Definitions

Format:

Definition:
<one sentence>

Purpose:
<one sentence>

Example:
<very short example>

---

## If explaining results

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

## Default Rule

If a sentence can be made shorter without losing meaning, shorten it.

This file is short on purpose. It is read automatically every session.
The full project history lives in `files/`, split into files so you
only load what a given task needs. Do not read all of them by default —
use the table below to pick the right one(s).

## One-paragraph orientation

Building a model that labels every cell in a spatial-proteomics tissue image
(T cell, tumour cell, fibroblast…) and still works on a hospital/machine/panel
it has never seen. Central claim: label harmonisation across cohorts can be
learned from marker profiles instead of a hand-written ontology. Repo:
`pipeline2/`. Old pipeline (plateaued at 0.630 macro-F1) is still in
`git HEAD:pipeline/`, kept only as a comparison baseline — do not build on it.

Status as of 2026-08-11 (see file 09 for the live checklist):
Stages 0, 0b, 1, 1b built and passing. **Stage 2 built and run — GATE 2 FAIL**: checks 2/3/4 pass,
check 1 fails on one kept pair (Keren MKI67, R² −0.0117) and the FAIL is recorded, not repaired
(D-34). Check 3, the question the stage exists to answer, passes: 0.1963 vs core-9 control 0.1707
vs Gate 1 0.169. Arm B ([ABSENT] tokens) ships. **Stage 3 built and run — GATE 3 PASS**, cross-cohort
macro-F1 0.3642 over 22 clusters, shipping λ = 0: the adversary does not help, which is the plan's
declared fallback (D-36). Two findings outrank the verdict — it HIDES slide identity rather than
removing it (D-37), and it does so even against a matched-capacity discriminator. **Stage 3b ran
both rescue experiments (45 fits) and BOTH FAIL** (D-43): a stronger critic made hiding worse, and
the patient-nested domain (my own D-38 hypothesis) made transfer worse at every λ. Removing batch
signal more successfully made transfer WORSE — batch is not the bottleneck. **Stage 6 built and run
— GATE 6 PASS**, 16 fits, 73.5 min, shipping the prototype head with 2 losses at 0.3901 (D-44).
**Stage 7a built and run — GATE 7 DONE**, 3 fits, 20.0 min: the frozen holdout is finally
scored at **0.3309**, and every stage of the pipeline has now been through its gate (D-50).
**Stage 7b run too** — the abstain rule works (macro-F1 0.3309 → **0.4204** at 35% coverage) and
novel-class detection **FAILS at AUROC 0.578** (D-52). **Step 4 done**, no compute: LOCO 0.3901 →
**0.4606** learnable-only, and H7 is confirmed and closed (D-53). **2026-08-14 — Stage 9 run, Stages 10 and 11 built, and the priorities changed.**
**Stage 9 (D-24's arrival test) is DONE**: Danenberg zero-shot **0.2161** (space A) / **0.2944** (B2),
no training, no pipeline file edited — but only **24 of 99** vocabulary slots are filled, and the
support-law correlation collapses to 0.295 there against ferguson's 0.843 (D-54). **Three marker-id
errors are now measured and one — Keren `SMA` → SMN1 — is frozen inside the trained vocabulary**
(D-55); it is recorded, not repaired, by user decision. **The project has NO valid external
comparison**: the old pipeline's 0.630 and "MAPS cross-dataset 0.5-0.6" are BOTH withdrawn, the
second because that number does not exist (D-56). **Stage 10 IS RUN and H13a IS CLOSED — the
project has a real baseline at last, and the model wins it**: Stage 6 **0.3901** against MAPS
(reimplemented from its published Methods) at **0.3447**, paired margin **+0.0454 [+0.0054,
+0.0766]** on 4 of 5 folds (D-57). Two honest caveats travel with that number — it conflates panel
width with architecture (99 markers vs 10), and gradient boosting on zero-filled features beats the
shipped model on 2 of 5 folds. The bigger result is a different row: giving MAPS all 99 slots with
unmeasured markers zero-filled drops it **0.3447 → 0.2116**, the first EXTERNAL evidence for
Stage 2's premise that a zero is not a measurement. **Stage 11** (derived vs curated label space, H13b) is built and
needs a GPU — and it already found that **Stage 1b cannot choose a granularity from 3 cohorts**
(D-58). Step 3's 55 seed fits (H9) now rank BELOW those two: intervals on a number with no external
comparison are polish. See the 2026-08-14 block at the top of file 10.
**Stage 12 IS BUILT AND RUN — the 25-cluster label space finally has external validation, and it
holds** (D-59, `reports/s12_ontology.md`). All 106 labels mapped to the **Cell Ontology** (Phillips
and Sorin for the first time), then scored against CL's hierarchy and CL's OWN published levels:
**ARI 0.4400 [0.3662, 0.6624] per label · 0.5725 reliable-only · 0.934 cell-weighted**, beating a
1000-shuffle null at p99.9 at every level. The comparison that matters: Gate 1b scored the same
clusters against the project's own hand mapping at 0.596 / 0.962, and an ontology nobody here wrote
gives 0.440 / 0.934 over a **larger** label and class set — so the 0.928 was not marking your own
homework. **CL places `Phillips|tumor cells` and `CRC|tumor cells` DISTANT and Stage 1b splits
them**, refereeing the hardest case in the project from outside. Two costs travel with it: the
**nesting layer failed its first external test** (0.282 of CL's parent-child pairs represented
against a declared 0.60 — H2 is answered and the answer is no), and only 0.228 of labels resolved
automatically, so the defensible sentence is *"the derived clusters agree with a published
ontology's STRUCTURE"*, **never** *"the labels were mapped without human input"*. Also settled:
**M6 was an artefact** — L1 agreement 0.629 → **0.9927** many-to-one, so stop quoting 0.629. Stage
12 is the **first gate in this project ever scored with a confidence interval and a permutation
null** (part of H9). No GPU, no training, minutes on CPU.
⚠️ Gates 3/3b used an 88-triple vocabulary (pre-D-39); Stage 6 onward uses the canonical 99, so
those numbers are not comparable — deliberate, see file 10.

**Four things a new session must know before quoting any number.**
1. Gate 6 PASSES its declared rule, but check 4's +0.0209 margin is **p = 0.460, 95% CI
   [−0.0501, +0.0919]**, and all of it comes from the Sorin fold. No gate in this project has ever
   been scored with a confidence interval (H9). The gates are valid decisions; several of the
   *sentences* written about them are not. Read D-44 before citing Gate 6.
2. **GATE 7 IS RUN. ferguson zero-shot macro-F1 = 0.3309** (22 reliable clusters, majority
   0.0237). Three spaces: A 0.3309 shipped · B1 0.3080 clean-37 · B2 0.4240 clean-22 (D-50).
   **Do not quote that average without splitting it.** Labels whose cluster is carried by ≥3
   training cohorts average **0.5291**; those carried by ≤2 average **0.0014** — never
   predicted at all. r = 0.843 on cohort count. This is Gate 6's support law replicating on an
   unseen machine and tissue, and it is the strongest result in the project.
   All three runs hit the 30-epoch ceiling, so the numbers are a LOWER BOUND.
   ⚠️ Why three: the **H10 control FAILS** (D-46). Stage 1b clustered all 6 cohorts together,
   so ferguson helped choose the label space's GRANULARITY — 25 clusters instead of the 37 the
   5 training cohorts pick alone. The similarity structure is untouched (matched-cut ARI
   0.9828); the coarseness is not. Space B2 prices the leak with the cut held fixed.
3. **THE SUPPORT LAW IS THE FINDING — lead the thesis with it, not with any macro-F1.** A cell
   type transfers if several cohorts independently agree on it, and does not otherwise. By number
   of contributing training cohorts, LOCO mean F1 runs **0.000 · 0.092 · 0.223 · 0.636** (r =
   0.781; not one of the 29 three-plus class-folds scores zero), and ferguson runs **0.0014 vs
   0.5291** (r = 0.843). Measured inside the roster, on held-out cohorts, and on an unseen
   machine and tissue; in three label spaces; and it predicted ferguson's failures before they
   were scored (D-50, D-53). It also says what to do next: **add cohorts that overlap on the
   types you care about** — not more markers, not more architecture.
   ⚠️ **AMENDED 2026-08-14 — state it with TWO conditions, not one.** On Danenberg the correlation
   falls to **0.295** (space A) / 0.278 (B2), because with only 24 of 99 marker slots filled,
   PANEL OVERLAP replaces training support as the binding constraint. The rich/thin gap survives
   (0.1487 vs 0.0222); the correlation does not. So: a type transfers if several cohorts
   independently agree on it **AND** the new cohort measures enough of the markers that define it.
   Quoting r = 0.843 as a stable constant is not supportable (D-54).
4. **Always report macro-F1 twice** — all clusters and learnable-only (D-53). Under LOCO a
   cluster whose only cohort is the held-out one has zero training examples and scores 0.000
   whatever the model does: 9 of 55 class-folds. LOCO 0.3901 → 0.4606 learnable-only. Quote both
   and say which is which; the first answers "how well does this annotate a new cohort end to
   end", the second "how well does the model do the part it had data for".

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

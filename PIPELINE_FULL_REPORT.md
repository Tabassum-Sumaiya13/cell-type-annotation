# RECAP — What we have done so far (past runs, decisions, results)

> ## ⚠️ Read this first — parts of this report are out of date (2026-08-03)
>
> The ferguson dataset was replaced. The old export had only 3 coarse labels and they were
> **wrong** (it called a squamous-carcinoma TMA 54% immune and 14% tumour). The new export has
> 9 real cell types, so ferguson is now a full L2 cohort with real cell areas.
>
> | Section | Status |
> |---|---|
> | Section 2 cohort table, "ferguson is the odd one out" | **fixed below** |
> | Section 5, Step 8 backbone LOCO results | **superseded** — see `harmonised/model/step8_loco_results.csv` (re-run 2026-08-03) |
> | Step 9 blocks, Step 10a/10b/10c, Step 8b tables | **stale** — those steps have NOT been re-run against the new ferguson. Do not quote them. |
>
> Everything about steps 1–7 method, CRC/HubMap/Keren/UPMC, and the marker panel is unchanged
> and still correct.

For the deep detail behind any step, see the matching `harmonised/_audit/report/stepN_report.md`.*
```markdown
RAW DATA (5 cohorts)
        │
        ▼
┌───────────────────────┐
│ STEP 1               │
│ Panel harmonisation   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ marker_map, panel     │
│ 102 markers, 19 backbone
└───────────┬───────────┘
            │
    ┌───────┼───────┐
    ▼       ▼       ▼
┌───────┐ ┌───────┐ ┌───────┐
│STEP 2 │ │STEP 3 │ │STEP 4 │
│Norm   │ │Geom   │ │Labels │
└───┬───┘ └───┬───┘ └───┬───┘
    │         │         │
    ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐
│expr   │ │cells  │ │labels │
│.parq  │ │.parq  │ │.parq  │
└───┬───┘ └───┬───┘ └───┬───┘
    │         │         │
    └────┬────┴────┬────┘
         │         │
         ▼         ▼
    ┌───────────┐ ┌───────────┐
    │ STEP 5    │ │ STEP 6    │
    │ Graph     │ │ Spatial   │
    │ (r30,k10) │ │ features  │
    └─────┬─────┘ └─────┬─────┘
          │             │
          └──────┬──────┘
                 ▼
         ┌───────────────┐
         │ STEP 7        │
         │ Assemble      │
         │ model tables  │
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │ STEP 8        │
         │ Train  -HisGradientBoosting       │
         │ LOCO + within │
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │ STEP 9        │
         │ Evaluate      │
         │ + ablate      │
         └───────────────┘
```


## 1. The problem we are solving

We want to **name the type of every cell** (T cell, tumour cell, fibroblast, etc.) in tissue images, and we want a model that **still works on a cohort it has never seen before** — a different hospital, a different machine, a different antibody panel. This is called **cross-cohort cell type annotation**. Our extra idea is to use **spatial context** — who a cell's neighbours are — to help, because in earlier steps we saw that a cell's marker readings alone are sometimes not enough.

- **Cohort** = one dataset from one source (one study / hospital / machine).
- **Marker** = a protein stain measured per cell (e.g. CD3 marks T cells). A **panel** = the set of markers a cohort measured.
- **Annotation** = giving each cell a type label.



## 2. The five datasets

| cohort | platform (machine) | tissue | total cells | usable markers | label detail |
|---|---|---|---|---|---|
| CRC | CODEX | colorectal cancer | 258,385 | 56 | full (9 types) |
| HubMap | CODEX | healthy intestine | 2,603,217 | 47 | full (9 types) |
| Keren | MIBI-TOF | breast cancer (TNBC) | 197,678 | 36 | full (8 types) |
| UPMC | IMC | head & neck cancer | 2,061,102 | 39 | full (7 types) |
| ferguson | IMC | head & neck skin cancer (cSCC) | 155,913 | 33 | full (6 types) |
| **total** | | | **5,276,295** | | |

- **CODEX / MIBI-TOF / IMC** are three different imaging machines. They measure the same kind of thing (protein per cell) but in different ways, so their numbers are not directly comparable — a big reason cross-cohort is hard.
- **ferguson is still the odd one out**, but only on the panel now: it has the fewest markers (33) and is **spatially sparse** — its cells sit far apart, so a 30 µm circle catches ~11 neighbours instead of 20–33. Since the 2026-08 re-export its labels are no longer coarse: 9 native types collapsing to 6 L2 groups (Epithelial/Tumour 101,458 · T cell 20,287 · Endothelial 14,159 · Granulocyte 7,993 · Myeloid 7,694 · B/Plasma 4,322).



## 3. Data-preparation pipeline (steps 1–7) — what each did

These steps ran once and produced the clean tables the model reads. No model training here.

1. **Step 1 — Panel harmonisation** (matching markers across cohorts). Different cohorts call the same protein different names (e.g. "PD-L1", "PDL1", "PD-L1 - checkpoint"). We mapped every name to one standard name, dropped non-protein channels (DNA stains, machine channels). Result: a shared vocabulary of **102 markers total** across all cohorts. Of these:
   - **9 markers** are in **all 5** cohorts.
   - **19 markers** are in **at least 4** cohorts — we call these the **backbone** (the honest common ground every model can rely on).
   - **102 markers** = the full **union** (every marker any cohort has).
2. **Step 2 — Normalisation** (making values comparable). Raw marker numbers differ wildly between machines. For each (image, marker) we converted the raw value into a **probability that the cell is positive for that marker** (a 0–1 number), using a rank + 2-group split. This is machine-neutral.
3. **Step 3 — Geometry**. Converted pixel coordinates to real micrometres (µm) so distances mean the same thing in every cohort.
4. **Step 4 — Labels**. Built a two-level type system:
   - **L1** = 3 broad groups: **Immune / Stromal / Epithelial-Tumour**.
   - **L2** = 9 fine types: T cell, B/Plasma, Myeloid, NK, Granulocyte, Endothelial, Fibroblast/Muscle, Epithelial/Tumour, Other.
   - **gold** = cells we trust the original label of; **clean** = cells that passed quality control; **label_confidence** = how sure we are of each label (0–1).
5. **Step 5 — Graph** (who is next to whom). Built two neighbour maps per cohort: **r30** (every cell within 30 µm is a neighbour) and **k10** (each cell's 10 nearest neighbours). *Until now only r30 was used to build features.*
6. **Step 6 — Spatial features** (label-free descriptions of each cell's surroundings). See §6.
7. **Step 7 — Assemble**. Glued geometry + labels + marker values + spatial features into one table per cohort (`{cohort}_model.parquet`).

Trainable cells (gold + clean, with a fine L2 label): CRC 205k, HubMap 840k, Keren 151k, UPMC 1,335k, ferguson 21k (ferguson has few because it lacks fine labels).


## 4. Key decision — how we handle the different panels (masked input)

**Decision:** feed the model the **full 102-marker slot vector** for every cell. If a cohort did not measure a marker, that slot is **"unknown" (NaN)** *plus* a **mask flag = 0** ("this was not measured"). We never put a 0, because 0 means "measured and absent" — a different thing.

- **Why:** it lets one model read every cohort even though they measured different markers, without lying about missing data.
- **Effect:** the model can, in principle, use any marker; but it must be told (by the mask) what is real vs unknown.



## 5. Key decision — the model (HistGradientBoosting) and why

**Decision:** use **HistGradientBoostingClassifier** (a gradient-boosted decision-tree model from scikit-learn).

- **What it is (plain):** it builds many small "yes/no question" trees one after another, each fixing the previous ones' mistakes. "Histogram" = it speeds up by bucketing values.
- **Why we chose it:** it is the one common model that **handles "unknown" (NaN) values natively** — it can send unknowns down their own branch. Almost every other model (neural network, logistic regression, random forest) **cannot** take NaN and forces us to guess-fill the blanks first, which is exactly the wrong thing when whole markers are missing per cohort.
- **Settings used:** `max_iter` 150–200 trees, `class_weight='balanced'` (so rare cell types are not ignored), and each cell weighted by its `label_confidence` (trust good labels more).

---

## 6. The spatial features we built (all label-free)

For each cell, from its neighbourhood:
- **nb_mean_\<marker\>** — the average "positive probability" of each marker among the cell's neighbours (what kind of cells surround it). *This turned out to be the most useful spatial feature.*
- **nb_std_\<marker\>** — how mixed the neighbourhood is for that marker.
- **density_30um** — how crowded the cell is.
- **img_mean_\<marker\>**, **img_pos_\<marker\>** — the average marker level / % positive across the **whole image** (image-level context).
- **micro_env** — a neighbourhood "cluster id" (1 of 15), shared across cohorts, so "type-7 neighbourhood" means the same everywhere.

---

## 7. Key decision — how we test (LOCO = Leave-One-Cohort-Out)

**Decision:** the main test is **Leave-One-Cohort-Out**: train on 4 cohorts, test on the 5th one the model has never seen, and rotate so each cohort is the test once.

- **Why:** this is the honest simulation of "deploy on a brand-new hospital." An easier test (mixing all cohorts together) would let the model peek at the test cohort during training and give falsely high scores.
- **Score used:** **macro-F1** — the average accuracy across cell types, counting each type equally so common types don't hide poor performance on rare ones. 0 = useless, 1 = perfect. On the backbone we score at **L1** (3 groups; ferguson can be scored here) and **L2** (9 types).

---

## 8. The runs we did and what they showed

### Run 1 — Step 8: backbone LOCO (19 shared markers) — *does spatial help?*

| held-out cohort | markers only (L1) | + spatial (L1) | change | spatial shuffled (control) |
|---|---|---|---|---|
| CRC | 0.562 | 0.582 | **+0.020** | 0.553 |
| HubMap | 0.720 | 0.728 | +0.007 | 0.705 |
| Keren | 0.654 | 0.647 | **−0.007** | 0.621 |
| UPMC | 0.771 | 0.787 | +0.016 | 0.746 |
| ferguson | 0.391 | 0.406 | +0.015 | 0.389 |
| **mean** | **0.620** | **0.630** | **+0.010** | 0.603 |

**Finding:** on the shared 19 markers, spatial context gives a **small but real** boost (+0.010 average, positive on 4 of 5). The "shuffled" control (break each cell's link to its real neighbours) drops the score back down — proof the gain is genuinely spatial, not luck. Our score (0.62–0.63) is at/above the published cross-dataset baseline (MAPS, 0.5–0.6).

### Run 2 — Step 9: diagnostics — *which spatial feature matters?*

Average score lost when each spatial block is removed (bigger = more useful):

| spatial block | mean importance |
|---|---|
| **nb_mean** (neighbour marker averages) | **0.0127** ← dominant |
| img_mean (image-level average) | 0.0028 |
| density | 0.0025 |
| nb_std | 0.0017 |
| img_pos (image-level % positive) | 0.0012 |
| micro_env | 0.0007 |

**Finding:** almost all the spatial benefit comes from **nb_mean** — what kinds of cells are around you. The image-level features are weak and, on the odd cohorts, sometimes **harmful** (Keren img_mean −0.003, ferguson img_pos −0.008).

### Run 3 — Step 8b: full-panel LOCO (all 102 markers) — *do more markers + full spatial help?*

| held-out | markers only, 19 → 102 | full-panel + spatial (change vs its own expr) |
|---|---|---|
| CRC | 0.562 → 0.610 (**+0.048**) | 0.590 (−0.020) |
| HubMap | 0.720 → 0.749 (**+0.029**) | 0.716 (−0.033) |
| Keren | 0.654 → 0.660 (+0.006) | 0.535 (**−0.125**) |
| UPMC | 0.771 → 0.784 (+0.013) | 0.779 (−0.004) |
| ferguson | 0.391 → **0.306** (−0.085) | 0.328 (+0.022) |
| **mean** | 0.620 → **0.622** (flat) | 0.590 (**−0.032**) |

**Two findings:**
1. **More markers is not a free win.** Extra markers help the marker-rich cohorts (CRC, HubMap, UPMC) but **hurt the marker-poor ferguson** (−0.085), because the model learns to lean on markers ferguson doesn't have. The average stays flat.
2. **Piling all spatial features on the full panel backfires** (−0.032 average, **Keren −0.125**). With 102 markers the spatial block balloons to ~340 columns; the image-level ones become a **fingerprint of which cohort it is** — a shortcut that means nothing on a new cohort. It only helps ferguson (whose own markers are too weak to stand alone).

---
---

## 9. What "within-dataset" means (and why it matters)

- **Cross-cohort (what we did before, LOCO):** train on 4 cohorts, test on a **brand-new 5th** one.
  This is the hard, honest, real-deployment test.
- **Within-dataset (new here):** train and test **inside the same cohort**. Cut one cohort's cells
  into 5 equal parts, train on 4 parts, test on the leftover, rotate. There is **no cohort gap** —
  same machine, same panel, same tissue in train and test.

Within-dataset tells us the **ceiling**: the best the model can do when nothing is unfamiliar. The
**difference between the ceiling and the cross-cohort score is the pure "cross-cohort penalty"** —
how much we lose purely from moving to a new source.

We ran it two ways:
- **random split** — parts are random (keeps cell-type balance). This is the pure ceiling.
- **by-patient split** — the **same patient never appears in both train and test**. Stricter and more
  honest, because otherwise the model can "recognise the patient" instead of learning cell types.

---
## 2. Result — the ceiling vs the cross-cohort score (L1, 3 groups)

| cohort | cross-cohort (old) | within, random | within, by-patient | ceiling − cross gap |
|---|---|---|---|---|
| CRC | 0.582 | **0.825** | 0.751 | **+0.24** |
| HubMap | 0.728 | **0.896** | n/a* | +0.17 |
| Keren | 0.647 | **0.853** | 0.807 | +0.21 |
| UPMC | 0.787 | **0.916** | 0.896 | +0.13 |
| **mean (4 rich)** | **0.686** | **0.873** | — | **~ +0.19** |

*\*HubMap's cells come from only **3 donors**, so a 5-way by-patient split is not possible — only the
random split is shown.*

*(cross-cohort = +spatial L1 from Step 8; within = +spatial L1 from this run.)*

## 3. Result at the fine level (L2, 9 types)

| cohort | within, random | within, by-patient |
|---|---|---|
| CRC | 0.671 | 0.462 |
| HubMap | 0.649 | n/a |
| Keren | 0.638 | 0.497 |
| UPMC | 0.851 | 0.820 |

*(ferguson is not here: it has only one fine type, so a within-cohort fine-level test is impossible.)*

---
## 10. What the two graphs are

To describe a cell's surroundings, we first decide **who counts as a neighbour**:

- **r30 (radius 30 µm):** every cell within 30 micrometres is a neighbour. The **number** of
  neighbours varies — crowded cells have many, isolated cells have few.
- **k10 (10 nearest):** always the **10 closest** cells, no matter how far. The **count is fixed** at
  10, but the **distance** varies — in sparse tissue the 10th nearest can be far away.

From earlier counts: r30 gives ~10–17 neighbours in the dense cohorts but only **~5.6 in ferguson**
(its cells sit far apart). k10 forces 10 everywhere. So we expected k10 might help the sparse ferguson.

## 10.1. Result — cross-cohort L1 macro-F1

| held-out cohort | markers only | + r30 spatial | + k10 spatial | k10 − r30 |
|---|---|---|---|---|
| CRC | 0.570 | 0.596 | 0.600 | **+0.003** |
| HubMap | 0.701 | 0.714 | 0.724 | **+0.009** |
| Keren | 0.645 | 0.661 | 0.652 | −0.010 |
| UPMC | 0.772 | 0.786 | 0.783 | −0.003 |
| ferguson | 0.393 | 0.416 | 0.411 | −0.005 |
| **mean** | **0.616** | **0.635** | **0.634** | **−0.001** |


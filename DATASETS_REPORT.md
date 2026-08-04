# Datasets report — only what the pipeline needs

Five spatial proteomics cohorts. Goal: train on some cohorts, predict cell types on a cohort the
model has never seen (cross-cohort annotation).

Numbers here are measured from the files or from the last full pipeline run, not copied from papers.
Ferguson numbers are from the **2026-08-03 re-export** (the new one with 9 cell types).

---

## 1. The five cohorts at a glance

| | CRC | HubMap | Keren | UPMC | ferguson |
|---|---|---|---|---|---|
| Machine | CODEX | CODEX | MIBI-TOF | CODEX | IMC |
| Tissue | colorectal cancer | healthy intestine | breast cancer (TNBC) | head & neck cancer | skin cancer of head & neck (cSCC) |
| Cells | 258,385 | 2,603,217 | 197,678 | 2,061,102 | 155,913 |
| Images | 140 | 66 | 40 | 308 | 44 |
| Patients | 35 | 8 donors | 40 | 81 | 17 |
| Markers the pipeline uses | 56 | 47 | 36 | 39 | 33 |
| Native cell types | 29 | 25 | 17 | 16 | 9 |
| Value scale in the raw file | raw intensity | z-scored | z-scored | arcsinh | raw intensity |
| Pixel size (µm) | 0.3774 | 0.3774 | 0.3906 | 0.3774 | 1.0 |

**Machine names:** CODEX, MIBI-TOF and IMC are three different imaging machines. All of them measure
protein amount per cell, but the numbers they produce are on different scales. This is the main
reason cross-cohort work is hard.

Two things to keep in mind:

- **Size is very unequal.** HubMap + UPMC hold 4.6 M of the 5.3 M cells. Without a cap they would
  drown the other three during training. That is why every experiment subsamples 120,000 cells per
  cohort.
- **Label quality is not equal.** See section 4.

---

## 2. Which raw file each cohort is read from

The whole file mess lives in one place: [pipeline/common.py](pipeline/common.py). Nothing else
touches raw paths.

| Cohort | Position + patient | Marker values | Cell type labels |
|---|---|---|---|
| CRC | `CRC_clusters_neighborhoods_markers.csv` | same file | same file (`ClusterName`) |
| HubMap | `cell_locations.parquet` | `cell_expression.parquet` | `cell_labels.parquet` |
| Keren | `cell_locations.csv` + `sample_metadata.csv` + `cellData.csv` | `cell_expression.csv` | `cell_locations.csv` (`cluster_label`) |
| UPMC | `dataset_info/cell_locations_and_labels.csv` + `sample_metadata.csv` | `dataset_info/labeled_arcsinh_norm_data.parquet` | `cell_locations_and_labels.csv` (`CLUSTER_LABEL`) |
| ferguson | `csv_export/ferguson_cells_counts.csv` | same file | same file (`cellType`) |

**Join rule that matters:** CRC and ferguson are one flat file, so row order is already correct.
The other three keep expression in a separate file, so the pipeline joins on a real key
(HubMap: `cell_id`; Keren: `SampleID` + `cellLabelInImage`; UPMC: acquisition + cell id) and
**asserts no NaN after the join**. If a raw file is incomplete you get a loud error, not silent
garbage.

**ferguson note:** two twin files exist — `_counts.csv` (raw) and `_norm.csv` (already normalised).
The pipeline reads `_counts` on purpose, because Step 2 does its own normalisation. Using `_norm`
would normalise twice.

Everything else in `Datasets/` (UPMC `celltype_neighborhoods/`, `denvar/`, ferguson `.rda` files,
`spicyWorkflow_images/`) is **not read by the pipeline**.

---

## 3. Markers — the core problem

Each cohort stains a different set of proteins, and the same protein has different names
("PD-L1", "PDL1", "PD-L1 - checkpoint"). Step 1 maps every name to one standard name and throws out
channels that are not proteins (DNA stains, metal/instrument channels, QC scores).

Since 2026-08-04 the standard name is the **gene symbol** (`CD8A`, not `CD8`). The familiar
antibody name is kept next to it as `display`, so reports can still say "CD8".

Result after cleaning:

| In how many cohorts | Markers | Names (gene symbol, familiar name) |
|---|---|---|
| all 5 | **9** | CD3E (CD3), CD4, CD68, CD8A (CD8), HLA-DRA (HLA-DR), KRT_PAN (PanCK), MKI67 (Ki67), PECAM1 (CD31), PTPRC_RO (CD45RO) |
| 4 | 10 | ACTA2 (aSMA), CD274 (PDL1), FCGR3A (CD16), FOXP3, ITGAX (CD11c), MS4A1 (CD20), PDCD1 (PD1), PDPN (Podoplanin), PTPRC (CD45), VIM (Vimentin) |
| 3 | 13 | |
| 2 | 18 | |
| 1 only | 51 | |
| **Union (all)** | **101** | |

Two marker sets are used downstream:

- **Backbone = 19 markers** (present in 4 or 5 cohorts). Honest common ground — every model sees
  these. This is the main experiment (Step 8).
- **Union = 101 markers**. A cohort that does not have a marker gets **NaN plus a mask flag = 0**
  ("not measured"). Never 0, because 0 means "measured and absent" — a different thing. Used in
  Step 8b.

**Channels dropped and why** (decided in [pipeline/step1_panel_harmonisation.py](pipeline/step1_panel_harmonisation.py)):

- DNA / nuclear channels (dsDNA, HH3, DNA1, DNA2, HOECHST1, DRAQ5) — used for segmentation, not cell type.
- Non-protein channels in Keren (C, Na, Si, P, Ca, Fe, Ta, Au, Background).
- Dead or near-flat channels: Keren `C` (all zeros), Keren `CD56`, `CD163`, `OX40`.
- HubMap `OLFM4`, `FAP`, `CD25`, `CollIV`, `CK7`, `MUC6` — captured but not used for clustering, mostly empty.

**One risky assumption to state in the write-up:** CRC `Cytokeratin`, Keren `Pan-Keratin` and
UPMC/ferguson `PanCK` are different antibody clones. They were merged into one marker `KRT_PAN`.
This is normal practice but it is still an assumption.

**Name pairs kept apart on purpose** (`pipeline/panel/never_merge.csv`): CD66a (CEACAM1) vs CD66
(CEACAM5/6); CD45 vs CD45RA vs CD45RO (same gene `PTPRC`, but naive and memory isoforms mean
opposite things); H3K9ac vs H3K27me3; pan-keratin vs KRT17 / KRT6A / KRT7.

---

## 4. Labels — how native names become one shared vocabulary

Every cohort names its cell types differently, so Step 4 maps the 90 native names onto a
two-level ontology (see [pipeline/step4_labels.py](pipeline/step4_labels.py)):

- **L1 — 3 broad groups:** Immune, Stromal, Epithelial/Tumour.
- **L2 — 9 types:** T cell, B/Plasma, Myeloid, Granulocyte, NK, Endothelial, Fibroblast/Muscle,
  Other (nerve, adipocyte, ICC), Epithelial/Tumour.
- **State is kept separate from type.** "CD4+ T cell CD45RO+" becomes type = CD4+ T cell,
  state = CD45RO+. State is a condition, not a cell type.

**Gold cells** = the cells whose label we trust and train on. A cell is gold when:

1. it was not dropped (CRC `dirt`, `undefined`, Keren `Unidentified`), **and**
2. it is not an ambiguous mixture label (CRC `tumor cells / immune cells`), **and**
3. UPMC only: kNN label confidence ≥ 0.70, **and**
4. HubMap only: it comes from donor B004, B005 or B006 — the three donors labelled by hand. The
   other 5 donors were labelled by a model (STELLAR), so training on them means learning another
   model's mistakes.

| Cohort | Cells | Dropped | Gold | L2 classes present |
|---|---|---|---|---|
| CRC | 258,385 | 17,831 | 240,554 | 9 |
| HubMap | 2,603,217 | 0 | 867,324 | 9 |
| Keren | 197,678 | 1,725 | 195,953 | 8 (no "Other") |
| UPMC | 2,061,102 | 0 | 1,567,717 | 7 (no NK, no "Other") |
| ferguson | 155,913 | 0 | 155,913 | **6** |

**ferguson L2 counts (new export):** Epithelial/Tumour 101,458 · T cell 20,287 · Endothelial 14,159 ·
Granulocyte 7,993 · Myeloid 7,694 · B/Plasma 4,322. Missing: NK, Fibroblast/Muscle, Other.

> Anything written before 2026-08-03 saying "ferguson has 3 labels" or "ferguson is L1 only" is
> **obsolete**. The old export had 3 coarse labels and they were wrong.

**Why this matters for scoring:** no cohort has all 9 L2 classes. Macro-F1 must be computed only
over the classes that actually exist in the held-out cohort, otherwise missing classes count as
zero and the score is unfair.

**Label origin is not the same quality everywhere:**

| Cohort | Where labels came from | Trust |
|---|---|---|
| CRC | expert clustering | good |
| HubMap | 3 donors by hand, 5 donors predicted by STELLAR | only the 3 manual donors are gold |
| Keren | clustering | good |
| UPMC | kNN clustering, has a confidence score | gold only above 0.70 |
| ferguson | FuseSOM clustering (10 clusters → 9 named types) | good, re-checked against marker profiles |

---

## 5. Values and geometry — why Steps 2 and 3 exist

**Step 2 — normalisation.** The raw scales are not comparable at all: CRC goes 0 → 54,777,
UPMC 0 → 13.2, HubMap is already z-scored. So a raw value cannot be shared across cohorts.
Step 2 converts every value into **P(positive)** — the probability that a cell is positive for that
marker — fitted **per image and per marker**. After this, every cohort speaks the same language
(0 to 1) and per-image staining differences are removed at the same time.

**Step 3 — geometry.** All coordinates are in pixels in the raw files, with different pixel sizes.
Step 3 converts to micrometres so that "30 µm neighbourhood" means the same thing everywhere.

- CRC pixel size 0.3774 and Keren 0.3906 come from the papers.
- HubMap and UPMC use 0.3774 as an assumption (same CODEX setup).
- ferguson uses 1.0 (IMC standard) — so for ferguson, pixels and micrometres are the same number.

**Quality flags added in Step 3** (a cell can carry more than one): area outlier, cell touching the
image border (< 30 µm), isolated cell (no neighbour). Plus, from Step 2: no-DNA and bright-speck.
"Clean" means no flag.

| Cohort | Has cell area? | Median area µm² | % border | % clean |
|---|---|---|---|---|
| CRC | yes | 81.5 | 11.9 | 86.2 |
| HubMap | no | — | 2.5 | 96.9 |
| Keren | yes | 58.6 | 15.0 | 83.5 |
| UPMC | yes | 55.3 | 10.4 | 87.9 |
| ferguson | yes | — | 3.8 | 96.0 |

Training uses **gold + clean** cells only:

| Cohort | Trainable cells (gold + clean) |
|---|---|
| CRC | ~208,000 |
| HubMap | ~843,000 |
| Keren | ~164,000 |
| UPMC | ~1,380,000 |
| ferguson | ~150,000 (new export; was ~21,000 with the old 3-label version) |

Testing scores **all gold cells** of the held-out cohort, clean or not — a real deployment does not
get to skip the messy cells.

---

## 6. Traps to remember

1. **Only 9 markers exist in all 5 cohorts.** This is the single number that shapes the whole
   project. Everything else is missing somewhere.
   Also: UPMC `CD134` and ferguson `OX40` are the **same protein** (`TNFRSF4`). The old naming
   treated them as two separate markers and lost that overlap — fixed 2026-08-04.
2. **HubMap labels are 5/8 machine-made.** Training on all of them teaches the model STELLAR's
   errors. Gold filter already handles this — do not remove it.
3. **UPMC and HubMap are huge.** Any experiment without a per-cohort cap becomes "predict HubMap".
4. **Tissue types are all different** (cancer of colon / breast / head & neck / skin, plus healthy
   intestine). A model can look good simply by recognising the tissue, not the cell. This is why
   image-level spatial features hurt on rich-panel cohorts — they act as a fingerprint of the cohort.
5. **CRC has duplicate imaging.** Each region was imaged twice (TMA A and B). Patient-level splits
   are required — splitting by image would leak the same tissue into train and test.
6. **ferguson has 6 of 9 L2 classes and 1 µm pixels.** It is the smallest and weakest panel; it is
   also the cohort that gains most from extra spatial context.

---

## 7. Where to check these numbers again

| Number | Produced by | File |
|---|---|---|
| marker names, backbone, union | Step 1 | `harmonised/_audit/step1_report.md`, `panel.json` |
| value ranges, normalisation audit | Step 2 | `harmonised/_audit/step2_{cohort}_marker_audit.csv` |
| cells, images, patients, clean % | Step 3 | `harmonised/_audit/step3_geometry_report.md` |
| label mapping, gold counts | Step 4 | `harmonised/_audit/cl_mapping.csv`, `step4_report.md` |
| final trainable table | Step 7 | `harmonised/_audit/step7_report.md` |

**Note:** the `harmonised/` folder is not on disk right now, so these audit files must be rebuilt by
re-running Steps 1–7 (see [RUN_PIPELINE.md](RUN_PIPELINE.md)). The numbers above come from the last
full run, plus a direct re-count of the new ferguson export.

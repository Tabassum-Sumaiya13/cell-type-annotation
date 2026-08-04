# Datasets report — only what the pipeline needs

Five spatial proteomics cohorts. Goal: train on some cohorts, predict cell types on a cohort the
model has never seen (cross-cohort annotation).

Numbers here are measured from the files or from the last full pipeline run, not copied from papers.

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


---

## 3. Markers — the core problem



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

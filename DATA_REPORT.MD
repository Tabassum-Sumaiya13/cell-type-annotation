# Cross-cohort cell type annotation — raw data report

Scope: 5 spatial proteomics cohorts. Goal is cross-cohort cell type annotation, with
spatial context used to improve accuracy.

All numbers below were measured directly from the files, not taken from papers,
unless marked **[lit]** (from literature) or **[assumed]**.



## 0. One-page summary

| | CRC | HubMap | Keren | UPMC | ferguson |
|---|---|---|---|---|---|
| Technology | CODEX | CODEX | MIBI-TOF | CODEX | IMC |
| Tissue | Colorectal cancer | Normal intestine | TNBC (breast) | Head & neck cancer | Head & neck skin cancer (cSCC) |
| Cells | 258,385 | 2,603,217 | 201,656 (197,678 labelled) | 2,061,102 | 155,913 |
| Images / regions | 140 spots (70 regions) | 66 regions | 43 FOVs (40 labelled) | 308 acquisitions | 44 acquisitions |
| Patients | 35 | 8 donors | 40 | 81 | 17 |
| Marker channels | 59 (56 protein) | 47 used + 6 extra | 49 (36 protein) | 39 | 36 (34 protein) |
| Expression state | **RAW intensity** | **z-scored per column per tissue** | **z-scored per column** | **arcsinh** | **RAW mean intensity** |
| Value range | 0 → 54,777 | −0.80 → 223 | −4.6 → 263 | 0 → 13.2 | 0 → 3,114 |
| Cell type labels | 29 | 25 | 17 | 16 | 9 |
| Label origin | expert clustering | 3 donors manual, **5 donors STELLAR-predicted** | clustering | kNN clustering (has confidence) | FuseSOM clustering |
| Pixel size | 0.3774 µm **[lit]** | 0.3774 µm **[assumed]** | 0.39 µm **[lit]** | 0.3774 µm **[assumed]** | 1.0 µm **[assumed, IMC standard]** |
| Coord units | pixels | pixels | pixels | pixels | pixels |
| Neighbourhood labels | 9 | 20 + community + segment | none | precomputed k1–k20 matrices | none |

**The single most important number:** only **9 markers exist in all 5 cohorts**
(CD3, CD31, CD4, CD45RO, CD68, CD8, HLA-DR, Ki67, PanCK).

# CRC- colorectal cancer (CODEX)

### Structure

| Item | Value |
|---|---|
| Rows (cells) | 258,385 |
| Columns | 99 |
| Patients | 35 |
| Regions | 70 (`reg001` … `reg070`) |
| Spots / images | 140 — every region imaged twice, on TMA `A` and TMA `B` |
| Design | each patient = 2 regions × 2 TMA copies = 4 spots |
| Groups | `groups` = 1 (17 patients) / 2 (18 patients) — CLR vs DII immune pattern |
| Cells per spot | min 84, median 1,979, max 3,887 |

### Cell types (29)

| type | cells | | type | cells |
|---|---|---|---|---|
| tumor cells | 47,602 | | CD11b+CD68+ macrophages | 1,500 |
| CD68+CD163+ macrophages | 39,596 | | CD11b+ monocytes | 815 |
| smooth muscle | 27,817 | | nerves | 659 |
| granulocytes | 22,144 | | CD11c+ DCs | 400 |
| stroma | 20,139 | | lymphatics | 328 |
| CD8+ T cells | 16,675 | | NK cells | 323 |
| CD4+ T cells CD45RO+ | 16,661 | | CD3+ T cells | 189 |
| B cells | 13,043 | | CD68+ macrophages GzmB+ | 183 |
| vasculature | 11,725 | | CD4+ T cells GATA3+ | 67 |
| plasma cells | 8,510 | | CD163+ macrophages | 38 |
| **dirt** | **7,357** | | adipocytes | 1,811 |
| **undefined** | **6,524** | | tumor cells / immune cells | 1,797 |
| immune cells | 3,127 | | immune cells / vasculature | 2,153 |
| Tregs | 2,791 | | CD68+ macrophages | 2,108 |
| CD4+ T cells | 2,303 | | | |

**Problems:** `dirt` + `undefined` = 13,881 cells (5.37%). Three classes are ambiguous
mixtures (`tumor cells / immune cells`, `immune cells / vasculature`). Nine classes have
under 1,000 cells.



## 2. HubMap — normal human intestine, CODEX

*(sections 2–4 not written up here — see `reports/1/DATA_REPORT.md` for the long version)*



## 5. ferguson — head & neck cutaneous squamous cell carcinoma, IMC

**Re-exported 2026-08-03.** The older export in this slot had only 3 coarse labels and they were
wrong, so anything written before that date about "ferguson has 3 labels" or "ferguson is
L1-only" is obsolete.

### Files

Everything the pipeline needs is one flat CSV:

```
Datasets/ferguson/csv_export/ferguson_cells_counts.csv    <- the pipeline reads this
Datasets/ferguson/csv_export/ferguson_cells_norm.csv      <- same table, spicy-normalised values
Datasets/ferguson/csv_export/marker_panel.csv             <- the 36 marker names, in assay order
Datasets/ferguson/ferguson_2022/                          <- original .rda + clinical data
Datasets/ferguson/spicyWorkflow_images/                   <- source R package, not used
```

One row per cell, 155,913 rows × 52 columns, no missing values, already in the row order the
rest of the pipeline uses. Columns: `imageID patientID group ROI object_id x y cellType cluster
region area radius_mean major_axis eccentricity` + the 36 markers.

**We read `_counts`, not `_norm`.** Step 2 does its own per-(image, marker) percentile + GMM
normalisation, so feeding it raw keeps ferguson on the same footing as CRC and Keren. Using
`_norm` would normalise twice.

### The 9 cell type codes

`cellType` comes from FuseSOM clusters 1–10 (clusters 3 and 5 are both `SC`). The published
abbreviations are terse, so each one was re-checked against its own marker profile in this data:

| code | means | top marker (z-scored) | cells |
|---|---|---|---|
| `SC` | squamous cells (the tumour) | panCK — highest of any type | 87,288 |
| `EP` | epithelial cells | podoplanin +1.53, panCK 2nd-highest | 14,170 |
| `EC` | endothelial cells | CD13 +1.32, CD31 | 14,159 |
| `TC_CD4` | CD4 T cells | CD4 +1.36, CD3 +0.91 | 11,753 |
| `TC_CD8` | CD8 T cells | CD8a +2.92, CD3 +1.23 | 8,534 |
| `GC` | granulocytes | CD66a +3.19 | 7,993 |
| `MC` | macrophages | CD68 +2.60 | 5,283 |
| `BC` | B cells | CD20 +3.10 | 4,322 |
| `DC` | dendritic cells | HLADR +3.85 | 2,411 |

`SC` and `EP` are the only two that are not obvious from the letters. Both map to
**L1 = Epithelial/Tumour and L2 = Epithelial/Tumour**, so the distinction between them does not
change any score — it only affects the fine `cl_name`.

### Watch out for

- **Pixel size is assumed 1.0 µm** (IMC standard). Coordinates therefore pass through unchanged,
  and `area` in pixels equals area in µm² (median 106 µm²).
- **CXCR3 has a median of 29.25**, about 45× the next marker. Flagged in Step 1 as possible
  channel bleed. It is still kept, because Step 2 normalises within each image anyway.
- **Spatially sparse.** A 30 µm circle catches ~11 neighbours here versus 20–33 in the other
  cohorts. This is why the r30-vs-k10 graph comparison (Step 10b) exists.
- `group` is NP / P (non-progressor / progressor) and `region` is a lisaClust spatial domain.
  Neither is used by this pipeline.
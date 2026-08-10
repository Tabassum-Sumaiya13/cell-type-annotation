3. Data Roster (measured, not estimated)
3.1 Built and passing Gate 0 (6 cohorts)
Cohort	Tech	Tissue	Cells	Images	Patients	Markers	Labels	Arrival	Role
Sorin	IMC	lung adeno	2,141,875	536	476	18	17	raw-uint8	train
UPMC	CODEX	head & neck	2,061,102	308	81	39	16	arcsinh	train
CRC (Schürch 2020)	CODEX	colorectal	258,385	140	35	58	29	raw	train
Keren (2018)	MIBI-TOF	breast TNBC	197,678	40	40	49	17	z-scored	train
Phillips 2021 (CTCL)	CODEX	skin lymphoma	117,170	69	14	59	21	raw	train
ferguson (2022) 🔒	IMC	skin SCC	155,913	44	17	36	9	raw	test-only
Totals: 4,932,123 cells · 1,137 slides · 663 patients.
log2(1,137) = 10.15 bits — the slide-adversary baseline for Gate 3 on the current roster.

Citations: CRC = Schürch et al., Cell 2020, 10.1016/j.cell.2020.07.005 · UPMC = Wu et al., Nat Biomed Eng 2022, 10.1038/s41551-022-00951-w · Phillips 2021 (Mendeley 3gmvy3bcmk) · Sorin 2023 (Zenodo 7760826) · Danenberg 2022 METABRIC (Zenodo 6036188). All CC-BY-4.0.

3.2 Pixel sizes independently confirmed by measured slide extent
Cohort	Measured extent	Published expectation
CRC	690 × 536 µm	TCIA: ~724 × 543 µm tile
Keren	775 × 775 µm	paper: 800 µm field of view
UPMC	1000 × 815 µm	report: ≈1.0 × 1.1 mm
ferguson	1156 × 1159 µm	IMC ~1.2 mm core
Danenberg	554 × 584 µm at 1 µm/px	consistent with an IMC ROI
Note: UPMC's px_um=0.3774 is marked px_um_source='ASSUMED - not published anywhere; same CODEX vendor stack as CRC'. This is an open assumption, not a verified fact.

3.3 Danenberg — downloaded, spec registered, deliberately NOT built
Status changed 2026-08-10 by user decision (D-24): Danenberg is repurposed as the "new cohort arrives later" test. It will not be folded into the training roster now. It becomes the live demonstration that adding a cohort needs no code change — the strongest possible evidence for the thesis claim.

Download finished (6.65 GB, throttled by Zenodo to ~0.3 MB/s throughout — measured on a fresh connection and against alternative record 5850952, so it was not a local network problem). Archive verified: 4,823 members, SingleCells.csv 849 MB, extracted along with AbPanel.csv and markerStackOrder.csv.

Audit result (better than the plan's estimate):

planned	actual
Cells	~1.1M	1,123,466
Images	693	794
Patients	—	718
Markers	37	39
Phenotypes	—	32
Missing values	—	0
config.SPECS['Danenberg'] is registered and its range rule resolves 39 markers with no leaked columns, verified.

Why its labels matter: CK^{med}ER^{lo}, CK8-18^{hi}CXCL12^{hi}, T_{Reg} & T_{Ex}, MHC I^{hi}CD57^{+}. Fine-grained, compositional, completely opaque to a text encoder. This is the argument for marker-profile alignment stated as a dataset rather than as an opinion.

Three known follow-ups, flagged now so they are not discovered later:

Two HER2 clones in one panel — HER2 (3B5) and HER2 (D8F12) both target ERBB2, so the triple key maps them to the same id. That is a duplicate triple within one cohort, which no earlier cohort produced. Stage 0b needs a stated duplicate policy (keep both and average, or keep the higher-dynamic-range one). Unresolved.
CD31-vWF is a co-stain, not plain CD31. If it does not resolve to PECAM1, Danenberg drops out of the 9-marker all-cohort core. Probably should become a COMPLEX: entry with PECAM1 and VWF as members — a judgement call for complexes.csv, made visibly. Unresolved.
Bare SMA is a dangerous string. aSMA is already in manual_overrides.csv, but bare SMA is also an alias route to SMN1 (spinal muscular atrophy). Exactly the Na → XK failure mode. Gate check 3c must be watched on that run. Unresolved.
If ever added to training (not the current plan), the roster becomes 7 cohorts / ~6.0M cells / 1,830 slides (1,786 trainable), log2(1,786) = 10.80 bits, and it would be the only IMC breast cohort — the "same tissue, different machine" pair against Keren (MIBI breast).

3.4 Risom 2022 — REJECTED
Recorded in config.REJECTED. Its single-cell table (69,672 × 136) ships no X/Y centroid, only derived Neighbor_dist_* features. The 298 MB image archive (checked by range-reading its zip directory, not downloaded) holds marker TIFFs and four region masks (duct/epi/myoep/stroma) but no per-cell label mask, so centroids cannot be recovered.

Also corrected: Zenodo 5945388, widely cited as this dataset, is a different study — the MIBI-TOF reproducibility paper on tonsil (345,490 cells, 165 FOVs, has centroids but is healthy tissue). Do not re-attempt.


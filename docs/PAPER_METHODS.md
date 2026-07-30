**Methods**

Data and cohorts
----------------
We analysed imaging-derived single-cell measurements from five cohorts. Cohort-level provenance, inclusion/exclusion criteria and per-cohort marker lists are recorded in `harmonised/_audit/panel.json` and `DATA_REPORT.MD`.

Panel harmonisation
-------------------
Raw channel names were mapped to canonical antigen identifiers with an alias table implemented in `pipeline/step1_panel_harmonisation.py`. Channels annotated as DNA, non-biological or QC were excluded from modelling. Two panel definitions were published for downstream experiments: a 19-marker BACKBONE (present in >=4 cohorts) for honest cross-cohort comparisons, and a 102-marker UNION representing all measured phenotypic markers. The script writes `harmonised/_audit/panel_matrix.csv` and `harmonised/_audit/panel.json`.

Signal normalisation
--------------------
Per-image per-marker values were converted to within-image percentile ranks and then processed with a two-component Gaussian mixture model to produce a continuous per-cell P(positive) score for each marker (implemented in `pipeline/step2_normalise.py`). Implementation details: percentile ranks use average-ties; GMM fitting uses a subsample of up to 4,000 cells (`FIT_SUB = 4000`) and falls back to percentile ranks for very small images (`MIN_CELLS = 50`) or failed fits. For unimodal images a soft flat probability (0.85 if the image mean is above the cohort median; else 0.15) is used to avoid degenerate all-positive / all-negative images. Outputs: `harmonised/{cohort}_expr.parquet` (P(positive) columns and `pct_*` percentile columns).

Geometry and QC
---------------
Pixel coordinates were converted to micrometres and stored as `x_um` and `y_um` in the per-cell geometry tables; segmentation and QC flags are retained (see `pipeline/step3_geometry.py` and `pipeline/step7_assemble.py`). Cells with `is_clean==False` or lacking gold labels are excluded from training where specified.

Graph construction (neighbourhoods)
----------------------------------
Local cellular neighbourhoods were encoded using two graph constructions built per image: an undirected radius graph with radius r = 30 μm (primary) and a k-nearest-neighbour graph with k = 10 (secondary). Edges are stored as unique undirected pairs with `src < dst` and include `dist_um` for optional pruning or weighting (`pipeline/step5_graph.py`). The radius graph is the primary spatial representation for neighbourhood aggregation.

Spatial feature derivation
--------------------------
Using the radius graph, we computed row-normalised sparse adjacency multiplication to derive neighbourhood means (`nb_mean_*`) for every marker and neighbourhood standard deviations (`nb_std_*`) for BACKBONE markers only. Additional per-image statistics (`img_mean_*`, `img_pos_*`) and a local density feature (`density_30um` = degree in the radius graph) were computed. A pooled MiniBatchKMeans (k = 15) fit to BACKBONE neighbourhood-means across all cohorts produced a shared `micro_env` id (see `pipeline/step6_spatial.py`, `K_MICROENV = 15`). Spatial outputs are written to `harmonised/{cohort}_spatial_r30.parquet` and per-cohort `*_microenv.parquet` files.

Model assembly
--------------
Per-cohort model tables were assembled by concatenating geometry, labels, the per-cohort P(positive) marker columns (stored as `x_<marker>`), spatial blocks and `micro_env`. To keep file sizes manageable, UNION-level alignment and masks are reconstructed at load time; assembled tables are written to `harmonised/model/{cohort}_model.parquet` and the layout recipe is saved to `harmonised/model/feature_columns.json` (`pipeline/step7_assemble.py`).

Classification and evaluation
-----------------------------
Primary experiments evaluate whether adding spatial features improves cross-cohort annotation. For Stage 1 we trained `HistGradientBoostingClassifier` (scikit-learn) on BACKBONE-derived features. Exact training configuration: `max_iter=200`, `learning_rate=0.1`, `l2_regularization=1.0`, `class_weight='balanced'`, `random_state=0`, and no early stopping (see `pipeline/step8_model.py`).

Training/validation protocol
---------------------------
- Leave-one-cohort-out (LOCO): models are trained on four cohorts and evaluated on the held-out fifth.
- Targets: L2 (9 classes) where available; an L1-level descendant-tolerant scoring maps predicted L2 → L1 for cohorts with coarser labels.
- Metrics: macro-F1 at L2 and L1. We report both `expr` (expression-only) and `expr+spatial` variants and compute the change in L1 macro-F1 attributable to spatial features. A permutation control is applied by shuffling the spatial feature rows within the test cohort to test for cohort-fingerprint artefacts.
- Training data are subsampled per-cohort to bound memory and runtime (`PER_COHORT_TRAIN = 100_000`, `CAP = 300_000` training-cap per fold); test cohorts are loaded at full size in each fold.

Implementation and reproducibility
---------------------------------
- Environment: Python (project tested on Python 3.12) with NumPy, pandas, SciPy, scikit-learn, pyarrow. Exact package versions and a `requirements.txt` should be provided alongside the repository.
- Determinism: random seeds are fixed where applicable (e.g., `numpy.random.default_rng(0)`, clustering and model RNGs use `random_state=0`).
- Source: all pipeline scripts referenced above are available under `pipeline/` and write audit artifacts to `harmonised/_audit/` for transparency.

Limitations and design choices
-----------------------------
- BACKBONE selection (≥4 cohorts) prioritises cross-cohort comparability but reduces marker dimensionality for experiments that could exploit the full UNION.
- The GMM-based per-image normalisation handles heterogenous imaging scales but collapses absolute intensity information; we mitigate this by reporting `pct_*` percentile columns and by including image-level summary features.
- Spatial permutation controls are a coarse test for cohort fingerprinting; further ablations (coordinate-level shuffles or region-restricted permutations) are recommended for publication-grade causal claims.

Where to find outputs
---------------------
- Harmonised audit and panel: `harmonised/_audit/panel.json`, `harmonised/_audit/panel_matrix.csv`.
- Per-cohort expression, spatial and model tables: `harmonised/{cohort}_expr.parquet`, `harmonised/{cohort}_spatial_r30.parquet`, `harmonised/model/{cohort}_model.parquet`.
- LOCO results and reports: `harmonised/model/step8_loco_results.csv`, `harmonised/_audit/step8_report.md`.

If you want, I can now:
- insert a short version of this Methods text into `PIPELINE_FULL_REPORT.md` or a specific `_audit` report, or
- create a `references.bib` with the citations we prepared earlier and add citation keys into this document.

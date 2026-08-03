# Writing the Methods Section (Guidance & Template)

Purpose
-------
This document provides concise guidance and a reusable template for writing the Methods section of a scientific paper, with emphasis on reproducibility and clarity for computational pipelines.

Audience
--------
- Researchers preparing a Methods section for machine‑learning or computational biology manuscripts.

Structure (recommended)
-----------------------
1. Summary paragraph — one-line task and high-level approach.
2. Data sources and cohort description — provenance, inclusion/exclusion, sizes.
3. Preprocessing and harmonisation — file formats, normalization, missing data handling.
4. Feature engineering — what features were derived and how (spatial, morphological, aggregated).
5. Model training and selection — algorithms, hyperparameters, software versions.
6. Evaluation and validation — cross-validation scheme, held-out cohorts, metrics.
7. Implementation details & reproducibility — code, seeds, compute, and data availability.
8. Limitations and choices — known weaknesses and rationale for design decisions.

Concise writing tips
-------------------
- Use past tense and active voice for methods already executed.
- Be specific: provide numeric values (e.g., radius = 30 μm, k = 10, k-means k = 15).
- Report software and versions (e.g., Python 3.12, scikit-learn 1.2.0).
- Report random seeds and sampling/subsampling strategies.
- Prefer short paragraphs and bulleted lists for multi-step procedures.

Reproducibility checklist
------------------------
- Data sources and selection criteria documented.
- Marker / variable selection described (e.g., BACKBONE vs UNION).
- Exact parameter values for normalization and graph construction included.
- File paths or repository locations for input/output specified.
- Code repository, environment specs, and example commands provided.

Example Methods paragraph (template)
-----------------------------------
We analyzed N samples across M cohorts to develop a cell-type classification pipeline. Raw imaging data were harmonised using a canonical panel mapping to produce two marker sets: a 19-marker BACKBONE used for cross-cohort experiments and a 102-marker UNION for within-cohort ablations. Signal preprocessing applied per-image percentile scaling followed by a two-component Gaussian mixture model to estimate per-marker positive probabilities. Spatial relations were encoded by building an undirected radius graph (r = 30 μm) and a k-nearest-neighbour graph (k = 10), from which local neighbourhood means and standard deviations were computed. We trained gradient-boosted tree classifiers (HistGradientBoostingClassifier) using leave-one-cohort-out (LOCO) evaluation; model hyperparameters and training details are listed in the repository. All code, parameter files, and harmonised tables are available at the project repository.

Quick example commands (publishable)
----------------------------------
Install environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run preprocessing (example):

```bash
python pipeline/step1_panel_harmonisation.py
python pipeline/step2_normalise.py --cohort COHORT_NAME
```

Where to put this in the paper
------------------------------
- Use the short template paragraph at the start of Methods for a concise overview; expand each numbered subsection below the overview as needed.

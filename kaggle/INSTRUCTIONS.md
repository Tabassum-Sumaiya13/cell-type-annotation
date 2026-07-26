# How to run the full-scale cross-cohort experiment on Kaggle

*For when a run is too heavy for your 2 GB local machine. Kaggle gives 30 GB RAM, free.*
*This runs the same experiments as local, but with NO memory cap — all cells, full 102-marker panel.*

---

## What you will upload

Only these files are needed (total ~2.4 GB). Keep this exact folder shape:

```
cross-cohort-model/            <- the Kaggle dataset folder
├── feature_columns.json       (from harmonised/model/)
├── panel.json                 (from harmonised/_audit/)
└── model/
    ├── CRC_model.parquet
    ├── HubMap_model.parquet
    ├── Keren_model.parquet
    ├── UPMC_model.parquet
    └── ferguson_model.parquet  (all from harmonised/model/)
```

> Tip: 2.4 GB may upload slowly. That is fine — you upload it **once** and reuse it in every run.

---

## Step 1 — Make a Kaggle account
Go to <https://www.kaggle.com>, sign up (free), and verify your phone number (needed to enable
notebooks with internet + more RAM).

## Step 2 — Create the dataset (upload the data)
1. Left menu → **Datasets** → **New Dataset**.
2. Drag in `feature_columns.json`, `panel.json`, and the whole `model/` folder (5 parquet files),
   arranged as shown above.
3. Name it exactly **`cross-cohort-model`** (or any name — but then update `INPUT_DIR` in the script).
4. Click **Create**. Wait until it finishes processing.

## Step 3 — Create the notebook
1. Open your new dataset → click **New Notebook** (this auto-attaches the data).
2. In the notebook, right side → **Settings**:
   - **Accelerator**: None (our model is CPU-only — a GPU does not help).
   - **Persistence / Environment**: leave default.
3. Confirm the data path: right panel shows the mounted folder, usually
   `/kaggle/input/cross-cohort-model`. If different, copy that path.

## Step 4 — Paste the code
1. Delete the default cell.
2. Open [`kaggle_full_run.py`](kaggle_full_run.py), copy **everything**, paste into one cell.
3. At the top, edit the **CONFIG** block if needed:
   - `INPUT_DIR` — must match the path from Step 3.
   - `PANEL_SET` — `"union"` for the full 102-marker run (heavy), or `"backbone"` for the fast
     19-marker run.
   - `CAP` — `None` = use **all** cells (the real full run). If you hit an "out of memory" error,
     set it to a number like `300_000`.
   - `RUN_LOCO` / `RUN_WITHIN` — turn each experiment on/off.

## Step 5 — Run
- Top menu → **Run All** (or **Save Version → Save & Run All** to run in the background so you can
  close the tab).
- The full-union run takes roughly **1–4 hours**. Kaggle allows up to **12 hours** per session, so
  it fits. Progress prints live.

## Step 6 — Get the results
- Results are written to `/kaggle/working/`:
  - `full_loco.csv` — cross-cohort scores (train on 4, test on the new 5th), markers-only vs +spatial.
  - `full_within.csv` — within-cohort ceiling scores.
- Download them from the **Output** tab (or the right panel), and send them to me — I will turn them
  into the final report tables.

---

## What this answers
- The **uncapped** version of our cross-cohort and within-cohort results, at the **full 102-marker
  panel** — the "whole run" that does not fit on the local machine (see Report A for the memory math).

## If you want the k10-graph or model-zoo experiments at full scale too
Those need extra files (`{cohort}_expr.parquet` and `{cohort}_graph_k10.parquet`). Tell me and I will
add a second Kaggle script that includes them — I kept this first one lean so the upload stays small.

## Common problems
- **"Out of memory / kernel died"** → set `CAP = 300_000` (or lower) in CONFIG and re-run.
- **"FileNotFoundError"** → your `INPUT_DIR` is wrong; copy the exact path from the right panel.
- **Run too slow** → set `PANEL_SET = "backbone"` first to confirm everything works, then switch to
  `"union"`.

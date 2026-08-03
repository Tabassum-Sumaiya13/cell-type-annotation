# How to run the pipeline end to end

Plain instructions for rebuilding everything from the raw datasets to the final result tables.

> **Current state (2026-08-03).** The ferguson dataset was replaced, so steps 1–8 were re-run and
> their outputs are current. **Steps 9, 10a, 10b, 10c and 8b were NOT re-run** — their CSVs in
> `harmonised/model/` are still from the old ferguson and must not be quoted. Run them next:
>
> ```powershell
> cd "d:\Desktop\FYDP\FYDP final works\cell type annotation\pipeline"
> python step9_diagnostics.py
> python step10a_validation.py
> python step10b_graph_models.py
> python step10c_k10_nbmean.py
> ```
>
> ferguson now has 6 L2 classes, so Step 10a will produce a real within-cohort row for it
> instead of skipping it.

---

## 0. Before you start

**You need:**

| Thing | Detail |
|---|---|
| Python | 3.12 (that is what is installed here) |
| Packages | `pandas numpy scipy scikit-learn pyarrow tabulate` |
| Raw data | the `Datasets/` folder with all 5 cohort folders inside |
| Free disk | about **5 GB** for the `harmonised/` outputs |
| Free RAM | about **2 GB** is enough for every step except Step 8b |

Install packages once:

```powershell
pip install pandas numpy scipy scikit-learn pyarrow tabulate
```

**One rule that matters:** every script does `from common import ...`, so you must run them
**from inside the `pipeline` folder**. If you run them from the project root you get
`ModuleNotFoundError: No module named 'common'`.

```powershell
cd "d:\Desktop\FYDP\FYDP final works\cell type annotation\pipeline"
```

**Path note:** the data location is hard-coded in [common.py:10](../pipeline/common.py#L10)
(`ROOT = r"d:\Desktop\FYDP\..."`). If you move the project, edit that one line — nothing else
needs changing.

---

## 1. The order, and why

Each step reads what the step before it wrote. You cannot skip ahead.

```
Step 1  panel harmonisation   -> decides the marker names       (no cell data touched)
Step 2  normalise             -> turns every value scale into P(positive)
Step 3  geometry              -> pixels to micrometres + quality flags
Step 4  labels                -> native cell names to L1 / L2
Step 5  graph                 -> who is a neighbour of whom
Step 6  spatial features      -> neighbourhood + image context per cell
Step 7  assemble              -> stack it all into one table per cohort
        ---- everything above is built once; everything below is an experiment ----
Step 8  backbone LOCO         -> the main cross-cohort result (19 markers)
Step 8b full-union LOCO       -> same but all 102 markers   (SLOW - see timing)
Step 9  diagnostics           -> per-class F1, confusion, which spatial block matters
Step 10a validation schemes   -> within-cohort CV, patient CV, skip-ferguson
Step 10b graph + model zoo    -> r30 vs k10 graph, HistGB vs RF vs LogReg vs MLP
```

Steps 2 and 3 do not depend on each other, so their order between themselves is free. Everything
else is strictly sequential.

---

## 2. Run it, one step at a time

Run these in order. Each one prints a per-cohort progress line, so you can see it working.

```powershell
python step1_panel_harmonisation.py
python step2_normalise.py
python step3_geometry.py
python step4_labels.py
python step5_graph.py
python step6_spatial.py
python step7_assemble.py
```

That is the **build**. After Step 7 you have the model-ready tables and never need to repeat
steps 1–7 unless the raw data or a design decision changes.

Then the **experiments** — these are independent of each other, run whichever you need:

```powershell
python step8_model.py           # main result, ~20 min
python step9_diagnostics.py     # needs step8's feature code, reads step7 tables
python step10a_validation.py    # builds its own small cache first
python step10b_graph_models.py  # reuses the same cache
python step8b_full.py           # ~4 hours - run last, or on Kaggle instead
```

### Copy-paste: build everything in one go

PowerShell, stops at the first failure:

```powershell
cd "d:\Desktop\FYDP\FYDP final works\cell type annotation\pipeline"
$steps = @(
  "step1_panel_harmonisation.py","step2_normalise.py","step3_geometry.py",
  "step4_labels.py","step5_graph.py","step6_spatial.py","step7_assemble.py",
  "step8_model.py","step9_diagnostics.py","step10a_validation.py","step10b_graph_models.py"
)
foreach ($s in $steps) {
  Write-Host "=== $s ===" -ForegroundColor Cyan
  python $s
  if ($LASTEXITCODE -ne 0) { Write-Host "FAILED at $s" -ForegroundColor Red; break }
}
```

`step8b_full.py` is deliberately left out of that list — add it only if you have 4 hours.

---

## 3. What each step writes (use this to check it worked)

All output goes under `harmonised/`. `_audit/` holds the human-readable reports.

| Step | Files it creates | Quick check |
|---|---|---|
| 1 | `_audit/marker_map.csv`, `panel_matrix.csv`, **`panel.json`**, `step1_report.md` | `panel.json` has 102 union + 19 backbone markers |
| 2 | `{cohort}_expr.parquet` × 5, `_audit/step2_{cohort}_marker_audit.csv` | 5 expr files exist |
| 3 | `{cohort}_cells.parquet` × 5, `_audit/step3_geometry_report.md` | report shows a "clean %" per cohort |
| 4 | `{cohort}_labels.parquet` × 5, `_audit/cl_mapping.csv`, `ontology_tree.csv` | report shows gold counts |
| 5 | `{cohort}_graph_r30.parquet` and `_graph_k10.parquet` × 5 | mean degree is roughly 5–15 for r30 |
| 6 | `{cohort}_spatial_r30.parquet`, `{cohort}_microenv.parquet` × 5 | 15 micro-env clusters listed in the report |
| 7 | `model/{cohort}_model.parquet` × 5, `model/feature_columns.json` | ~2.4 GB total on disk |
| 8 | `model/step8_loco_results.csv`, `_audit/step8_report.md` | 5 rows, one per held-out cohort |
| 8b | `model/step8b_full_results.csv`, `_audit/step8b_report.md` | 5 rows |
| 9 | `model/step9_{blocks,perclass,confusion}.csv` | |
| 10a | `model/step10a_within.csv`, `step10a_skipferg.csv` | |
| 10b | `model/step10b_graph.csv`, `step10b_models.csv` | |

**`panel.json` is the keystone file.** Steps 6, 7, 8, 8b and `r2common` all read it at import
time. If Step 1 did not finish, every later step crashes immediately with a missing-file error.

---

## 4. Timing and memory

Measured on the ~2 GB local machine (from [Report A](2/REPORT_A_compute_cost.md)):

| Step | Time | Peak RAM |
|---|---|---|
| 1 | seconds | tiny |
| 2 | minutes (Gaussian mixture per image × marker) | low |
| 3 | minutes | low |
| 4 | minutes | low |
| 5 | minutes (KD-tree per image) | low |
| 6 | minutes (sparse matrix multiply) | low |
| 7 | minutes (pyarrow column stacking) | low |
| **8** | **~20 min** | **< 1.3 GB** |
| 9 | ~ same order as 8 | < 1.3 GB |
| 10a / 10b | minutes each after the cache is built | < 1 GB |
| **8b** | **~4 hours** | ~1.5 GB |

Step 8b is slow because of **prediction**, not training: scoring UPMC's 1.38 M test cells across
546 features took 2.5 hours in a single fold. Training itself is only 200–320 s per fold.

**Caps in place so it fits in 2 GB:** every experiment subsamples training cells
(120,000 per cohort) and streams test cells in 200,000-row batches. No run so far has trained on
all 2.55 M cells at once — that needs ~11 GB. For an uncapped run use the Kaggle scripts in
[`kaggle/`](../kaggle/INSTRUCTIONS.md) (30 GB free RAM).

---

## 5. Restarting from the middle

Nothing is incremental — each step overwrites its own outputs, so re-running a step is always
safe. If you change something, re-run **that step and everything after it**:

| You changed | Re-run from |
|---|---|
| marker names / aliases | Step 1 (everything downstream depends on `panel.json`) |
| normalisation method | Step 2, then 6, 7, and the experiments |
| pixel size / QC rules | Step 3, then 5, 6, 7, experiments |
| label mapping | Step 4, then 7, experiments |
| graph radius or k | Step 5, then 6, 7, experiments |
| model settings only | just the experiment step (8 / 8b / 9 / 10a / 10b) |

Steps 2 and 6 accept cohort names to redo only part:

```powershell
python step2_normalise.py Keren UPMC
python step6_spatial.py Keren UPMC
```

⚠️ **Careful with Step 6 partial runs.** The micro-environment clusters (pass 6b) are one shared
k-means over *all 5 cohorts*. If you pass a subset, Step 6 skips 6b and leaves the old
`_microenv.parquet` files behind — the clusters no longer match the new features. After any
partial run, finish with a full `python step6_spatial.py` before Step 7.

Steps 10a/10b keep a feature cache in the system temp folder
(`%TEMP%\claude\r2_featcache`). Delete it if you changed Steps 1–7, or it will silently reuse
stale features.

---

## 6. Errors you are likely to hit

| Message | Cause | Fix |
|---|---|---|
| `No module named 'common'` | ran from the wrong folder | `cd` into `pipeline` first |
| `FileNotFoundError: ...panel.json` | Step 1 not run or failed | run Step 1 |
| `{cohort} expr join left NaNs` | raw file mismatch — the join key did not line up | check that cohort's raw files are complete |
| `{cohort} labels cell_id misaligned` (Step 7) | a step 2–6 output is stale, built from a different row order | re-run steps 2–6 for that cohort, then 7 |
| `window shape cannot be larger than input array shape` | a marker is NaN in every training cohort | already handled by the all-NaN column drop; if it appears, the fix is missing from that script |
| MemoryError in Step 8b | not enough RAM | lower `CAP` / `BATCH` at the top of the file, or run it on Kaggle |

---

## 7. Shortest version

```powershell
cd "d:\Desktop\FYDP\FYDP final works\cell type annotation\pipeline"
python step1_panel_harmonisation.py
python step2_normalise.py
python step3_geometry.py
python step4_labels.py
python step5_graph.py
python step6_spatial.py
python step7_assemble.py
python step8_model.py
```

That gives you the full build plus the main cross-cohort result in well under an hour.
Everything else is an optional extra experiment.

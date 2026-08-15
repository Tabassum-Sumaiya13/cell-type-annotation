# Running the GPU stages on Kaggle

Two notebooks, one dataset. Build the dataset once with `make_upload.py` (77.84 MB) and attach it
to both.

| notebook | gate | fits | time on a T4 | state |
|---|---|---|---|---|
| `stage3.ipynb` cells 1-5 | GATE 3 - lambda sweep | 25 | 39.8 min (measured) | done, PASS, ships lambda=0 |
| `stage3.ipynb` cells 6-7 | Stage 3b - the D-37/D-38 ablation | 45 | 80.2 min (measured) | done, both hypotheses fail |
| `stage6.ipynb` | GATE 6 - losses and training | 16 | 73.5 min (measured) | done, PASS, ships 2 losses at 0.3901 |
| `stage7.ipynb` | GATE 7 - the frozen-holdout number | 3 | 20.0 min (measured) | done, ferguson = 0.3309 |
| `stage8.ipynb` | STEP 3 - repeated seeds, confidence intervals | 55 | ~3.5-4 h (estimated) | **not run** |

**REBUILD THE DATASET BEFORE RUNNING STAGE 7.** The upload changed for Stage 7 and grew from 77.84 MB to 94.00 MB. It now carries `work/values/ferguson_full.parquet` - the frozen holdout, which never left this machine before (D-49) - plus the two CLEAN label spaces `label_map_B1.csv` / `label_map_B2.csv` and their prototypes. Cell 1 of `stage7.ipynb` asserts `MANIFEST.json` says `stage: 7` and refuses to continue on an older dataset, so an out-of-date upload fails loudly rather than silently scoring the wrong label space.

**The freeze is now enforced in code, not by file location.** `s7_eval.load_frozen` builds a `test` tensor and nothing else; gate 7 check 0 asserts the training cohort list is exactly the five and that ferguson is absent from every draw; and cell 3 asserts that assert PRINTED on the Kaggle machine before the real fit may start. If check 0 does not print, stop - do not run cell 4 and do not report any number.

**A caveat that applies to every Stage 3 number.** Gates 3 and 3b ran before D-39 fixed the
vocabulary bug, so they used 88 triples and a partial warm start. Stage 6 uses the canonical 99.
The two are therefore NOT comparable, which is why Gate 6 re-measures Stage 3's linear head inside
its own run instead of citing 0.3642. Cell 2 of `stage6.ipynb` asserts the vocabulary is 99 so the
bug cannot come back unnoticed.

---

# Stage 3 (the original instructions)

Stage 3's Gate 3 is 5 lambdas x 5 LOCO folds = **25 fits**. Measured on this laptop that is about
**18 hours**. On a Kaggle T4 it should be one to two hours, inside the 30 h/week free quota.

This folder holds everything needed to move the run there and nothing else changes: the same
`s3_encoder.py` runs in both places, picking the device automatically. There is no GPU fork of the
training code, because two copies drift and then the local number and the Kaggle number stop being
comparable.

---

## What gets uploaded, and what does not

`make_upload.py` assembles **76 MB**: the code plus exactly the tables Stage 3 reads.

| Included | Why |
|---|---|
| `pipeline2/` (686 KB) | The code, pinned with the data so a result always has a known source |
| `work/values/{CRC,UPMC,Keren,Phillips,Sorin}_full.parquet` (75 MB) | The five training cohorts' wide value tables |
| `work/marker_registry.csv` | Stage 0b's triple resolution - builds the 99-token vocabulary |
| `work/label_map.csv` | Stage 1b's 25 clusters, the label space Gate 3 scores on |
| `work/panel.json` | Token vocabulary + `stage2_arm` (currently `absent`) |
| `work/ckpt/s2_armA.pt`, `s2_armB.pt` | Stage 2 weights, for the warm start |
| `_validation/hand_mapping_reference.csv` (5 KB) | The secondary L2 column only. Never trained on (D-4) |

| Left out | Why |
|---|---|
| `work/raw/*.parquet` (**627 MB**) | Stage 3 opens none of it. `s2.built()` tests for these files, which is why `s3_encoder.available()` exists instead - it tests for the value tables Stage 3 actually reads. Uploading raw would be 8x the data for an existence check |
| `work/values/ferguson_full.parquet` | The frozen holdout. Never trained on, never loaded by Stage 3, so it has no reason to leave this machine |
| `Datasets/` | Source data. Stage 1 already reduced it |
| `*_rand`, `*_slidestats` | Stage 1 diagnostics, unused from Stage 2 on |

---

## Step by step

### 1. Build the upload folder (local)

```
python pipeline2/kaggle/make_upload.py
```

Writes `work/kaggle_upload/` and prints the size and a `MANIFEST.json` carrying a SHA-256 prefix
for every file. It says `MISSING` and names the file if anything Stage 3 needs is absent.

### 2. Upload it as a Kaggle Dataset

1. Zip `work/kaggle_upload/` (or upload the folder directly).
2. kaggle.com -> **Datasets** -> **New Dataset**.
3. Title it so the slug becomes `cta-stage3`. If you pick another name, change `SRC` in cell 1.
4. Visibility **Private**.

### 3. Create the notebook

1. **Code** -> **New Notebook**, then **Add Data** -> your dataset.
2. In the settings panel on the right:
   - **Accelerator: GPU T4 x2** (or P100 - the code uses one GPU either way)
   - **Internet: Off** - everything is in the dataset, and off is faster to start
   - **Persistence: None**
3. The notebook is already built: **`pipeline2/kaggle/stage3.ipynb`**. Upload it with
   **File -> Import Notebook**, or open a blank notebook and paste the cells.

   To rebuild it after changing anything in `kaggle_stage3.py`:
   ```
   python pipeline2/kaggle/kaggle_stage3.py pipeline2/kaggle/stage3.ipynb   # rewrite the .ipynb
   python pipeline2/kaggle/kaggle_stage3.py                                 # or just print the cells
   ```
   The notebook is NOT part of the dataset upload - `make_upload.py` skips this folder, because
   the notebook goes to Kaggle as a notebook, not as data.

### 4. Run the cells in order

| Cell | Does | Time |
|---|---|---|
| 1 | Copies the dataset into the writable `/kaggle/working/proj`, asserts a GPU is present | seconds |
| 2 | Re-hashes every file against `MANIFEST.json` | seconds |
| 3 | **Smoke test** - one fold at two lambdas, 2 epochs on 1,500 cells, then deletes its own checkpoints. Also asserts it really is on CUDA | ~1-2 min |
| 4 | The real sweep, streamed line by line | see below |
| 5 | Renders the gate report, prints the fold table, zips reports + checkpoints | seconds |
| 6 | **Stage 3b** - the D-37 / D-38 ablation, 3 arms x 3 lambdas x 5 folds | ~72 min |
| 7 | Compares all three arms against Gate 3's lambda=0 baseline | seconds |

**Cells 6-7 are a separate experiment.** Gate 3 (cells 3-5) is already done. To run only Stage 3b
in a fresh session, run cells 1, 2, then 6, 7 - cells 3-5 can be skipped. Nothing in 6-7 can
overwrite a Gate 3 result: every Stage 3b checkpoint and report carries a `d_` / `n_` / `nd_` tag.

**Do not skip cell 3.** Stage 3 has been caught twice by defects that only appeared at run time -
once by a metric that could not be computed at all (D-35), once by a flag that emptied the
training set. Both were invisible until something actually ran. One or two minutes to find a
GPU-specific break is worth it against an hour of quota.

**How long cell 4 takes.** Measured on this 8-core CPU: **37.4 min per fold** (2,241 s, 25 epochs,
15k cells x 4 cohorts), so **15.6 h for all 25**. A T4 should be far quicker, but this workload is
small per kernel launch - batches of 512 cells x 99 tokens at d=64 - so expect the GPU to spend a
lot of its time waiting on Python rather than computing. Treat 1-2 h as the hope, not a promise;
the first few folds will tell you the real rate.

### 5. Bring the results home

Download `stage3_ckpt.zip` from the notebook's Output panel and unzip into `work/ckpt/`. The fold
files carry the fitted weights as well as the scores, so a fold can be reopened locally without
retraining.

---

## Things worth knowing before you start

**The mount is read-only.** `/kaggle/input/` cannot be written, and the pipeline writes
checkpoints, so cell 1 copies everything to `/kaggle/working/proj`. That layout is also what makes
`config.ROOT` resolve correctly - `ROOT` is derived from where `pipeline2/config.py` sits.

**Re-running cell 4 resumes.** Each fold is cached to `work/ckpt/s3_lam*_*.pt` the moment it
finishes. If the session dies at fold 20, re-running picks up at fold 20. This is what makes a
timeout survivable, and it is why the sweep does not need to fit in one sitting.

**GPU and CPU results will not match bit for bit.** Different kernels and non-deterministic
reductions. The seed makes each machine reproducible against itself, not against the other. If a
number needs to be compared with a Stage 1 or Stage 2 figure produced locally, re-run that
comparison on one machine.

**The 12-hour session limit is not the binding constraint** at 1-2 h, but the 30 h/week GPU quota
is worth watching if the sweep gets re-run several times.

**If it is slower than hoped**, the reason is batch size, not the GPU. Stage 3 trains on batches of
512 cells x 99 tokens at d=64 - small work per kernel launch, so a T4 spends much of its time
waiting on Python. Raising `BATCH` in `s3_encoder.py` is the first lever, and it changes the
optimisation, so it is a declared change and not a free one.

---

## Narrowing the grid, if the quota gets tight

```
python pipeline2/s3_encoder.py --lambda-sweep --lambdas 0,0.03,0.3   # 15 runs instead of 25
```

The plan declares "at least" the five-value grid `{0, 0.01, 0.03, 0.1, 0.3}`, so dropping to three
is a change to a declared design and belongs in the decision log - not something to do quietly
because a run felt slow.

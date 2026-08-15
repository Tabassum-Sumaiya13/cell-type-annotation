# Cross-cohort cell-type annotation — how to run it

This file is the **operating manual**: how to run the pipeline, how to add a new dataset,
and how to unfreeze the held-out cohort and train on it.

It does **not** repeat the science. Results, decisions and open questions live in
[files/](files/) — start at [CLAUDE.md](CLAUDE.md) for the index.

---

## 1. What the pipeline does

Takes several spatial-proteomics cohorts (different hospitals, machines and antibody panels),
puts them on one scale, learns a **shared label space** from marker profiles instead of a
hand-written ontology, and trains one model that labels cells in a cohort it has never seen.

All the code is in [pipeline2/](pipeline2/). The old pipeline is only in git history
(`git show HEAD:pipeline/`) and must not be built on.

---

## 2. Setup

```
python 3.12
pip install torch pandas numpy pyarrow matplotlib scipy networkx requests
```

| Package | Needed for |
|---|---|
| `requests` | Stage 0b only, and only the **first** run (HGNC/UniProt lookups get cached) |
| `networkx` | Stage 1b nesting graph |
| `scipy` | clustering, Hungarian matching, rank stats |
| `torch` | Stages 1, 2, 3, 6, 7 (CPU is fine; GPU is much faster) |
| `pyarrow` | parquet read/write |

Optional: `sentence-transformers` (naming only, weight α = 0 — the pipeline is correct without it).
Not needed: `torch_geometric`, `leidenalg`.

**Folder layout** (all paths are derived from where `pipeline2/config.py` sits, so you can run
commands from anywhere):

```
Datasets/          source data, one folder per cohort      (git-ignored, not in the repo)
work/              everything the pipeline produces        (git-ignored)
  raw/             one standard table per cohort
  values/          Stage 1 + Stage 2 value tables
  ckpt/            model checkpoints
  panel.json       THE token vocabulary — see the warning in §6
  label_map.csv    THE label space
  prototypes.npy   one marker signature per cluster
reports/           every gate report, as markdown + figures
pipeline2/panel/   gate thresholds, committed BEFORE each run
files/             the project history and decision log
```

`Datasets/`, `work/` and `_validation/` are git-ignored, so a fresh clone has code only.
You must download the data and re-run from Stage 0.

---

## 3. The pipeline, stage by stage

Run from the repo root. Every stage writes a markdown report into `reports/`.

| # | Command | Reads | Writes | Time |
|---|---|---|---|---|
| load | `python pipeline2/loaders.py` | `Datasets/` | `work/raw/{cohort}.parquet` | minutes, CPU |
| 0 | `python pipeline2/s0_audit.py` | `work/raw/` | `reports/s0_audit.md` | minutes, CPU |
| 0b | `python pipeline2/s0b_markers.py` | `work/raw/` | `work/marker_registry.csv` | minutes, CPU (first run needs internet) |
| 1 | `python pipeline2/s1_values.py --bakeoff` | `work/raw/` | `work/values/{cohort}.parquet` | slow on CPU — the bake-off trains 6 arms |
| 1b | `python pipeline2/s1b_labels.py` | `work/values/` | `work/label_map.csv`, `work/prototypes.npy` | minutes, CPU |
| 2 | `python pipeline2/s2_tokens.py --build` | `work/values/` | `work/values/{cohort}_full.parquet`, **`work/panel.json`** | minutes, CPU |
| conf | `python pipeline2/s6_confidence.py` | `work/raw/` | `work/label_conf/` | seconds, CPU |
| 2 gate | `python pipeline2/s2_tokens.py --check` | above | `reports/s2_masking.md` | hours — use a GPU |
| 3 | `python pipeline2/s3_encoder.py --lambda-sweep` | above | `work/ckpt/s3_*.pt` | **39.8 min** on a T4 (measured) |
| 6 | `python pipeline2/s6_train.py --ablate-losses` | above | `work/ckpt/s6_sweep.pt` | **73.5 min** on a T4 (measured) |
| 7a | `python pipeline2/s7_spaces.py --build` | `work/s1b_signatures.npz` | `work/label_map_B1.csv`, `_B2.csv` + prototypes | minutes, CPU |
| 7a | `python pipeline2/s7_eval.py --frozen-test ferguson` | above | `work/ckpt/s7_*.pt`, `reports/s7_eval.md` | **20.0 min** on a T4 (measured) |
| 7b | `python pipeline2/s7b_abstain.py` | `work/ckpt/s7_*.pt` | `reports/s7b_abstain.md` | minutes, CPU — no training |
| 8 | `python pipeline2/s8_perclass.py` | existing checkpoints | `reports/s8_perclass.md` | no compute at all |
| 8 | `python pipeline2/s8_seeds.py --loco --frozen` | above | `reports/s8_seeds.md` | ~4 h on a T4 (estimated, 55 fits) |

Only the times marked **measured** were timed on a real run (they are recorded in
[files/09](files/09_status_deps_and_commands.md)). The CPU stages have never been timed —
treat those as rough.

Useful flags, most stages accept them:

- `--quick` — tiny smoke run. Proves the code path, **scores nothing**. Always do this first.
- `--refit` — ignore the checkpoint cache and retrain.
- `--cpu` — force CPU even if a GPU exists.
- `--report` — re-render the report from cached checkpoints (Stage 7, Stage 8).

Two flag notes, because the older docs are out of date:

- `s0_audit.py --all` does nothing. The real flag is `--build`, which runs the loaders first.
- `s7_eval.py --frozen-test ferguson` — the cohort name is **decorative**. The held-out cohort
  is hard-coded in [s1b_control.py:41-42](pipeline2/s1b_control.py#L41-L42).

### Running the heavy stages on a GPU

Stages 2-gate, 3, 6, 7 and 8 are slow on a laptop. They run on Kaggle from the same code:

```
python pipeline2/kaggle/make_upload.py     # builds work/kaggle_upload/ (~94 MB) + MANIFEST.json
```

Upload that folder as a **private** Kaggle Dataset, then import the matching notebook from
[pipeline2/kaggle/](pipeline2/kaggle/). Full instructions: [pipeline2/kaggle/README.md](pipeline2/kaggle/README.md).

---

## 4. Adding a new dataset

### 4.1 What the dataset must have

| Needed | Notes |
|---|---|
| one row per cell | with an image/slide id, `x`, `y`, and a native cell-type label |
| a marker matrix | one column per antibody, under the **original vendor name** — do not rename them, Stage 0b resolves names against HGNC/UniProt |
| pixel size in µm | reporting only today (Stage 4 is deferred), but record where the number came from |

Optional but useful: patient id, cell area, per-cell label confidence.
If a patient id is missing the loader fills `unknown`; if confidence is missing it fills `1.0`.

The arrival scale (raw / arcsinh / z-score / uint8) does **not** matter — Stage 1's per-cohort
ECDF removes it. Just record it honestly in the spec.

### 4.2 Write the spec — this is the only code you write

Everything cohort-specific lives in `SPECS` in [pipeline2/config.py](pipeline2/config.py).
`loaders.py` is one generic reader with **no** `if cohort == "X"` anywhere. If a new dataset
needs a code change in `loaders.py`, extend the spec format — do not add a branch.

```python
'MyCohort': dict(
    tech='IMC', tissue='liver', disease='hepatocellular carcinoma',
    role='train',                       # 'train' or 'holdout'
    px_um=1.0,
    px_um_source='hardware fact - IMC ablation spot is 1 um',
    arrival='raw',                      # raw | arcsinh | zscore | raw-uint8
    citation='Author et al., Journal 2024, doi:...',
    base=dict(
        file='MyCohort/cells.csv', format='csv',      # relative to Datasets/
        cols={'image_id': 'ImageID', 'patient_id': 'PatientID',
              'x_px': 'X', 'y_px': 'Y', 'native_label': 'CellType'},
        area=dict(kind='column', column='Area'),      # or kind='divide', numerator=, denominator=
        keep=['CellID'],                              # extra columns needed as join keys
    ),
    joins=[],                                          # extra tables merged by key
    expr=dict(markers=dict(kind='range', start='CD3', end='DNA1')),
),
```

Marker columns are declared by **rule**, never hand-listed:

| Rule | Use when |
|---|---|
| `{'kind': 'pattern', 'regex': r':Cyc_\d+_ch_\d+$'}` | marker names share a suffix/prefix |
| `{'kind': 'range', 'start': 'CD3', 'end': 'DNA1'}` | markers sit in one contiguous block |
| `{'kind': 'exclude', 'cols': ['SampleID', 'cellLabel']}` | the file is markers plus a few key columns |
| `{'kind': 'file', 'path': 'MyCohort/panel.csv', 'column': 'marker'}` | a panel list ships with the data. Add `'header': None` for a bare one-name-per-line file, or the first marker is silently eaten |

If the marker matrix is a separate file, add `file`, `format`, `left_on`, `right_on` to `expr`
and the loader merges it. A join that duplicates rows raises immediately — it does not
silently multiply your cells.

### 4.3 Back up `work/` first

Adding a cohort rewrites shared artefacts. Before you start:

```
xcopy /E /I work work_backup            # PowerShell / cmd
cp -r work work_backup                  # bash
```

At minimum keep copies of `work/panel.json`, `work/label_map.csv`, `work/prototypes.npy`
and `work/ckpt/`.

### 4.4 Run it

```
python pipeline2/loaders.py MyCohort            # just the new one
python pipeline2/s0_audit.py                    # sanity: cells, images, coordinates
python pipeline2/s0b_markers.py                 # resolve its marker names (needs internet once)
python pipeline2/s1_values.py                   # builds only the missing value table
python pipeline2/s1b_labels.py --resign         # MUST use --resign: the signature cache is stale
python pipeline2/s2_tokens.py --build
python pipeline2/s6_confidence.py
```

Then check §4.5 before training anything.

Three things to read before you trust the output:

- **`--resign` is not optional.** Signatures are cached in `work/s1b_signatures.npz`.
  Without it, Stage 1b clusters the old cohorts and quietly ignores the new one.
- **`--build` on Stage 2 is not optional either.** Run bare, `s2_tokens.py` notices the one
  missing table, builds only that cohort — and then overwrites `work/s2_dynrange.csv` with that
  cohort's rows alone. Stage 6 reads that file to decide which (cohort, marker) pairs to exclude,
  so it would silently train on the wrong exclusion set. `--build` rebuilds every table and every
  row. It is slower and it is the only safe option.
- `s0b_markers.py` puts anything it cannot resolve into a **review queue** and never guesses.
  Read that section of `reports/s0b_markers.md`. Fix real misses in
  [pipeline2/panel/manual_overrides.csv](pipeline2/panel/manual_overrides.csv), and add genuinely
  non-gene channels (dyes, elemental channels, protein complexes) to
  [pipeline2/panel/complexes.csv](pipeline2/panel/complexes.csv).

### 4.5 The vocabulary trap — check this every time

`work/panel.json` holds the **token vocabulary**: every resolved marker triple, and its index.
Model weights, and `work/prototypes.npy`, are indexed by that position. This already broke
one run silently (D-39).

After `s2_tokens.py --build`, compare `n_vocab` with the backup:

```
python -c "import json; print(json.load(open('work/panel.json'))['n_vocab'])"
```

| Result | Meaning | What you must do |
|---|---|---|
| **unchanged** (99) | every new marker was already in the vocabulary | existing checkpoints stay valid |
| **changed** | the new cohort added markers | every Stage 2/3/6/7 checkpoint is now misaligned — delete `work/ckpt/s2_*.pt`, `s3_*`, `s6_*`, `s7_*` and refit from Stage 2 |

The same applies to the label space: re-running `s1b_labels.py` rewrites `work/label_map.csv`
and `work/prototypes.npy`. If the number of clusters changes, `prototypes.npy` no longer matches
and Stage 6 falls back to **random** prototype initialisation — it prints a line saying so.
Watch for it.

### 4.6 Which of the two roles do you want?

**As a training cohort** (`role='train'`) — it joins the roster and every LOCO number is
re-measured. Run §4.4, then Stage 2 gate → 3 → 6 → 7 with `--refit`.

**As a new test cohort** (`role='holdout'`) — it is scored zero-shot. Also edit
[s1b_control.py:41-42](pipeline2/s1b_control.py#L41-L42):

```python
TRAIN  = ['CRC', 'UPMC', 'Keren', 'Phillips', 'Sorin', 'ferguson']   # everything you train on
FROZEN = 'MyCohort'                                                   # the cohort under test
```

Then:

```
python pipeline2/s7_spaces.py --build        # clusters TRAIN alone, then places MyCohort's
                                             # labels into that FROZEN partition by signature
python pipeline2/s7_eval.py --frozen-test MyCohort
```

`s7_spaces.py` is the mechanism for "a cohort that arrives later": its labels join the cluster
whose members are closest on average, and only if that distance is inside the same cut the
partition was built at. A label no cluster admits is reported as **NOVEL**, never forced into
the nearest bin.

### 4.7 Limitation: the new dataset needs labels

There is **no predict-only entry point today**. Every scoring path maps `native_label` through
`label_map.csv` and drops cells it cannot map, so a dataset with no ground-truth labels runs
through Stage 2 and then stops.

Annotating a truly unlabelled cohort needs a small new script that:

1. builds `{cohort}_full.parquet` (Stages 0 → 2, which need no labels),
2. loads `work/ckpt/s7_A.pt` and the vocabulary from `work/panel.json`,
3. runs the encoder over the cells, takes the nearest prototype,
4. maps the cluster index back to a name through `label_map.csv`,
5. optionally applies the Stage 7b abstain rule — distance to the nearest prototype, which
   lifted macro-F1 from 0.3309 to 0.4204 at 35% coverage.

Ask if you want this built; it is roughly 60 lines and reuses `s7_eval.load_frozen`.

---

## 5. Unfreezing and training

### 5.1 First: what is actually frozen

Two different meanings, and only one is about model weights.

| "Frozen" | What it really is |
|---|---|
| **The frozen holdout** (`ferguson`) | A whole cohort kept out of every loss so Stage 7's zero-shot number is honest. This is the one people mean. |
| **The frozen partition** (spaces B1/B2) | The label clusters are built from training cohorts alone, then locked, and the holdout's labels are placed into them. The holdout can never move a cluster boundary. |
| **Model weights** | **Nothing is frozen.** There is no `requires_grad = False` anywhere in the codebase. The encoder trains end to end in Stages 2, 3, 6 and 7. |

What people sometimes mistake for a frozen encoder is the **warm start**: Stage 6 and 7 load
Stage 2's pretrained token layer from `work/ckpt/s2_armB.pt` as a *starting point*, then train
all of it. Turn it off with `--no-warm` to train from cold.

### 5.2 Unfreeze the holdout and train on it

Do this when you want `ferguson` (or whichever cohort is frozen) to become an ordinary training
cohort. **You give up the zero-shot claim about that cohort permanently** — you cannot un-see it.

1. [pipeline2/config.py](pipeline2/config.py#L121) — change the ferguson spec:
   ```python
   role='train',        # was 'holdout'
   ```
2. [pipeline2/s1b_control.py:41-42](pipeline2/s1b_control.py#L41-L42) — these two lists are
   hard-coded and drive Stages 7 and 8:
   ```python
   TRAIN  = ['CRC', 'UPMC', 'Keren', 'Phillips', 'Sorin', 'ferguson']
   FROZEN = 'NewHoldout'      # Stage 7 needs a held-out cohort. With none, skip Stages 7/7b/8.
   ```
3. Clear the artefacts that were built without it:
   ```
   del work\ckpt\s3_*.pt work\ckpt\s6_*.pt work\ckpt\s7_*.pt
   del work\label_map_B1.csv work\label_map_B2.csv work\prototypes_B1.npy work\prototypes_B2.npy
   ```
4. Rebuild and retrain:
   ```
   python pipeline2/s1b_labels.py --resign
   python pipeline2/s2_tokens.py --build
   python pipeline2/s6_confidence.py
   python pipeline2/s6_train.py --ablate-losses --quick     # smoke test first
   python pipeline2/s6_train.py --ablate-losses --refit     # the real run
   ```
5. Then Stage 7 only if you set a new `FROZEN`.

**Side effects, all of them real:**

- Every number in `reports/` was measured with ferguson out. After this they are stale — do not
  quote old and new numbers side by side.
- The LOCO folds change from 5 to 6, so Gate 6's 0.3901 is not comparable to whatever comes out.
- ferguson's 34 markers may add triples to the vocabulary. Re-check §4.5.
- The support law predicts the win: ferguson adds a 6th independent vote on the types it shares,
  which is exactly the "add cohorts that overlap on the types you care about" lever.
- This is a design change. Log it in
  [files/08_decision_log_and_do_not_repeat.md](files/08_decision_log_and_do_not_repeat.md)
  with the next D-number, and update the status line in [CLAUDE.md](CLAUDE.md).

### 5.3 Training knobs

All in [pipeline2/s6_train.py:60-73](pipeline2/s6_train.py#L60-L73), declared as constants:

| Constant | Value | What it does |
|---|---|---|
| `EPOCHS`, `PATIENCE` | 30, 4 | ceiling and early stopping |
| `N_TRAIN` | 15,000 | training cells drawn per cohort |
| `BATCH`, `LR` | 512, 1e-3 | |
| `D_TOK`, `D_Z` | 64, 128 | token and cell embedding size |
| `BLOCKS`, `HEADS` | 2, 4 | set-transformer depth |
| `MASK_FRAC` | 0.15 | markers hidden per cell for the reconstruction loss |
| `PROTO_TEMP` | 0.1 | prototype softmax temperature |

**The highest-value knob right now is `EPOCHS`.** All three Gate 7 runs hit the 30-epoch ceiling,
so **0.3309 is a lower bound**, not a converged number. Raising it is the obvious next
experiment — and it changes a declared constant, so it belongs in the decision log.

Stage 2 has its own ceiling: `EPOCHS = 30` plus `--holdout-epochs N` to raise it for the two
holdout arms only (Arm B needed 47, so 30 was binding there too).

To train from scratch instead of warm-starting: add `--no-warm`.
To ignore cached checkpoints: add `--refit`. Without it, a finished fit is reloaded, which is
what makes a Kaggle session timeout survivable — a re-run picks up where it stopped.

Reproducibility: one `SEED = 20260810` in [config.py:36](pipeline2/config.py#L36), and every
random draw derives its own generator from it plus a purpose string. CPU and GPU will not match
bit for bit — the seed makes each machine reproducible against itself.

---

## 6. Common errors

| Message | Cause | Fix |
|---|---|---|
| `nothing built - run: python loaders.py` | no `work/raw/*.parquet` | run the loaders |
| `work/panel.json missing` | Stage 2 never built | `python pipeline2/s2_tokens.py --build` |
| `marker file lists columns absent from the data` | the panel list does not match the expression table | check the spec's `expr.markers` rule, and `header: None` for bare lists |
| `marker range endpoint not found` | a `range` rule's `start`/`end` column was renamed | open the file's header and fix the endpoints |
| `join on [...] duplicated rows` | the joined table's key is not unique | de-duplicate the right-hand table first |
| `prototypes.npy is (25, 99), expected (31, 99) - random init instead` | the label space changed but prototypes did not | re-run `s1b_labels.py --resign`, then refit Stage 6 |
| `--offline but <url> is not cached` | Stage 0b hit a new marker with no internet | run once online to fill `work/api_cache.json` |
| `work/s2_dynrange.csv predates D-28` | old artefact | `python pipeline2/s2_tokens.py --build` |
| Stage 3/6/7 numbers look wrong on Kaggle | stale uploaded dataset | re-run `make_upload.py` and re-upload; the notebooks assert on `MANIFEST.json` |

---

## 7. House rules for anyone running this

1. **Gate thresholds are committed before the run**, in `pipeline2/panel/gate*_expect.csv`.
   Never move a threshold to make a gate pass. Two gates in this project are recorded as
   FAIL for exactly that reason.
2. **A `--quick` smoke test costs 1-2 minutes and has caught real breakages twice.** Run it.
3. **Report macro-F1 twice** — all clusters, and learnable-only. See point 4 of [CLAUDE.md](CLAUDE.md).
4. **Update the docs before you finish.** New decision → `files/08`. Status change → `files/09`
   plus the header in `CLAUDE.md`. Never delete an old entry; mark it
   Accepted / Replaced / Deprecated / Rejected and say what replaced it.

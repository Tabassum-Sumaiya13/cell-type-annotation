"""
Kaggle notebook body for GATE 7 - Stage 7, the frozen-holdout number.

Paste each block into its own cell, in order. Settings before running anything:
Accelerator = GPU T4 x2 (or P100), Internet = OFF, Persistence = off.

    python pipeline2/kaggle/kaggle_stage7.py                     # print the cells
    python pipeline2/kaggle/kaggle_stage7.py stage7.ipynb        # write the notebook

WHAT GATE 7 RUNS - 3 fits, about 20-25 min on a T4 at Gate 6's measured rate.
    space A    the shipped 25-cluster label space          <- NOT blind to the holdout (D-46)
    space B1   37 clusters, 5 training cohorts, own cut    <- clean, hardest
    space B2   22 clusters, 5 training cohorts, shipped cut <- clean, matched to A

Each fit trains on ALL FIVE training cohorts - not LOCO - with Gate 6's shipped configuration
and nothing re-tuned, then scores ferguson as pure test.

THE ONE THING THAT MATTERS MORE THAN THE NUMBER. ferguson is the frozen holdout. Its value table
is in this dataset for the first time (D-48) because Stage 7 is the stage that scores it. Cell 3
asserts, on Kaggle and not just on the laptop, that it never reaches the training data. If that
assert ever fails, stop - every number after it is worthless.

READ BEFORE READING THE RESULT.
  - The thresholds AND a predicted range were committed to pipeline2/panel/gate7_expect.csv
    before s7_eval.py was written. Read that file first, then the report.
  - Two things were already true before any model ran: space B2 admits only 8 of ferguson's 9
    labels (EP is NOVEL, 14,170 cells, dropped from the macro-F1 rather than forced into a bin),
    and space B1 fuses EP with GC into one cluster. Both are properties of the label space, not
    model failures, and the report states them next to the numbers.
  - Space A is reported FIRST and is NOT a clean zero-shot number. Reporting only the clean ones
    would hide what the pipeline as-built produces; reporting only A would hide the leak.
"""

# ============================================================================ CELL 1 - setup
CELL_1 = r'''
import os, shutil, json
SRC = "/kaggle/input/cta-stage3"          # <-- same dataset, rebuilt with make_upload.py
DST = "/kaggle/working/proj"

assert os.path.isdir(SRC), f"dataset not attached at {SRC} - check the Add Data panel"
if os.path.isdir(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)
os.makedirs(f"{DST}/work/ckpt", exist_ok=True)
os.makedirs(f"{DST}/reports/figures", exist_ok=True)

man = json.load(open(f"{DST}/MANIFEST.json"))
print("manifest stage:", man.get("stage"), "| arm:", man["stage2_arm"],
      "| data", round(man["total_bytes"]/1e6, 1), "MB")
assert man.get("stage") == "7", (
    "this dataset was built before Stage 7 - rebuild it locally with "
    "`python pipeline2/kaggle/make_upload.py` and re-upload. Without that the frozen "
    "holdout's value table and the two clean label spaces are not here.")

# Stage 7 needs five things Stage 6 did not. Missing any of them does NOT crash - the code would
# fall back to a different label space or random prototypes and score a model nobody chose.
need = ["work/values/ferguson_full.parquet",
        "work/label_map_B1.csv", "work/prototypes_B1.npy",
        "work/label_map_B2.csv", "work/prototypes_B2.npy"]
for f in need:
    assert os.path.exists(f"{DST}/{f}"), f"MISSING {f} - rebuild the upload with make_upload.py"
print("Stage 7 inputs: all present")

import torch
print("\ntorch", torch.__version__, "|",
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU")
assert torch.cuda.is_available(), "no GPU - set Accelerator to GPU in the notebook settings"
'''

# ============================================================================ CELL 2 - integrity
CELL_2 = r'''
# Confirm the upload arrived intact, and that the three label spaces are the ones expected.
import hashlib, json, os, sys
import numpy as np, pandas as pd
DST = "/kaggle/working/proj"

def sha(p, n=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(n)
            if not b: break
            h.update(b)
    return h.hexdigest()[:16]

man = json.load(open(f"{DST}/MANIFEST.json"))
bad = [f["path"] for f in man["files"]
       if not os.path.exists(os.path.join(DST, f["path"]))
       or os.path.getsize(os.path.join(DST, f["path"])) != f["bytes"]
       or sha(os.path.join(DST, f["path"])) != f["sha256_16"]]
print("checked", len(man["files"]), "files ->", "ALL OK" if not bad else f"PROBLEMS {bad}")
assert not bad

sys.path.insert(0, f"{DST}/pipeline2")
os.chdir(DST)
import s2_tokens as s2, s3_encoder as s3

# D-39 again. ferguson's table is now on disk, so available() would return 6 cohorts - the
# vocabulary must still come from panel.json and still be 99.
V = len(s2.read_panel(["CRC","UPMC","Keren","Phillips","Sorin","ferguson"])[0])
print("vocabulary:", V)
assert V == 99, f"expected the canonical 99 triples, got {V} - D-39 has regressed"

# Each space's prototypes must match its cluster count, or every prototype is misaligned BY INDEX
# with nothing to signal it - the exact failure D-39 caused and D-42 nearly repeated.
for tag, lm, pt in [("A",  "work/label_map.csv",    "work/prototypes.npy"),
                    ("B1", "work/label_map_B1.csv", "work/prototypes_B1.npy"),
                    ("B2", "work/label_map_B2.csv", "work/prototypes_B2.npy")]:
    d = pd.read_csv(f"{DST}/{lm}", keep_default_na=False)
    P = np.load(f"{DST}/{pt}")
    n_cl = d[d.cluster >= 0].cluster.nunique()
    nov  = int((d.cluster < 0).sum())
    print(f"  space {tag}: {n_cl} clusters, prototypes {P.shape}, "
          f"NaN {int(np.isnan(P).sum())}/{P.size}" + (f", {nov} NOVEL" if nov else ""))
    assert P.shape == (n_cl, V), f"space {tag}: prototypes {P.shape} != ({n_cl}, {V})"

fz = pd.read_parquet(f"{DST}/work/values/ferguson_full.parquet", columns=["native_label"])
print(f"\nferguson value table: {len(fz):,} cells, {fz.native_label.nunique()} native labels")
'''

# ============================================================================ CELL 3 - smoke test
CELL_3 = r'''
# ~3 min. One space, 2 epochs. Scores nothing and writes no report - it exists to prove the code
# path and, above all, to run gate 7 check 0 on this machine.
import subprocess, glob, os
DST = "/kaggle/working/proj"
r = subprocess.run(["python", "-u", "pipeline2/s7_eval.py", "--frozen-test", "ferguson",
                    "--quick", "--spaces", "A"], cwd=DST, capture_output=True, text=True)
print(r.stdout[-7000:]); print(r.stderr[-3000:])
assert r.returncode == 0, "smoke test failed - do not start the real run"
assert "device     : cuda" in r.stdout, "ran on CPU - the real run would take hours"

# CHECK 0. The frozen holdout must never reach the training data. This is the assert the whole
# project rests on, and it runs HERE, not only on the laptop.
assert "ferguson absent from every draw: OK" in r.stdout, \
    "CHECK 0 DID NOT PRINT - stop. Do not run the real fit, do not report any number."
print("\ncheck 0 confirmed on this machine")
for p in glob.glob(f"{DST}/work/ckpt/s7_*_quick.pt"):
    os.remove(p)
print("smoke checkpoints removed")
'''

# ============================================================================ CELL 4 - GATE 7
CELL_4 = r'''
# The real run: 3 fits, one per label space. Streamed. Each space caches to work/ckpt/s7_*.pt as
# it finishes, so re-running this cell resumes rather than restarting.
import subprocess, time
DST = "/kaggle/working/proj"
t0 = time.time()
p = subprocess.Popen(["python", "-u", "pipeline2/s7_eval.py", "--frozen-test", "ferguson"],
                     cwd=DST, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="")
p.wait()
print(f"\nexit {p.returncode} after {(time.time()-t0)/60:.1f} min")
'''

# ============================================================================ CELL 5 - collect
CELL_5 = r'''
# Render the gate, then zip everything worth taking home.
import os, shutil, torch, pandas as pd
from IPython.display import Markdown, display
DST = "/kaggle/working/proj"

rep = f"{DST}/reports/s7_eval.md"
if os.path.exists(rep):
    display(Markdown(open(rep, encoding="utf-8").read()))
else:
    print("NO REPORT - the run did not finish all 3 spaces. Re-run cell 4; it resumes.")

rows = []
for tag in ("A", "B1", "B2"):
    p = f"{DST}/work/ckpt/s7_{tag}.pt"
    if not os.path.exists(p):
        continue
    r = torch.load(p, weights_only=False)
    rows.append({k: r[k] for k in ("tag", "n_class", "f1_core", "f1_all",
                                   "f1_majority", "f1_random", "n_scored", "seconds")}
                | {"epochs": r["info"]["epochs_used"], "val_f1": r["info"]["val_f1"]})
d = pd.DataFrame(rows)
print(d.round(4).to_string(index=False))

# The headline, stated the way the gate says to state it: whatever it is.
if len(d):
    a = d[d.tag == "A"]
    if len(a):
        print(f"\nferguson zero-shot macro-F1 (shipped space A, {int(a.n_class.iloc[0])} "
              f"clusters): {a.f1_core.iloc[0]:.4f}")
        print(f"  baselines on the same cells: majority {a.f1_majority.iloc[0]:.4f}, "
              f"random {a.f1_random.iloc[0]:.4f}")
    if {"A", "B2"} <= set(d.tag):
        gap = float(d[d.tag == "A"].f1_core.iloc[0]) - float(d[d.tag == "B2"].f1_core.iloc[0])
        print(f"  leak cost at matched cut (A - B2): {gap:+.4f}")
    print(f"\ntotal GPU time: {d.seconds.sum()/60:.1f} min over {len(d)} fits")

shutil.copytree(f"{DST}/reports", "/kaggle/working/out/reports", dirs_exist_ok=True)
shutil.copytree(f"{DST}/work/ckpt", "/kaggle/working/out/ckpt", dirs_exist_ok=True)
shutil.make_archive("/kaggle/working/stage7_results", "zip", "/kaggle/working/out")
print("\nwrote /kaggle/working/stage7_results.zip",
      round(os.path.getsize("/kaggle/working/stage7_results.zip")/1e6, 1), "MB")
'''

CELLS = [CELL_1, CELL_2, CELL_3, CELL_4, CELL_5]

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else None
    if out:
        import json
        nb = dict(cells=[dict(cell_type="code", metadata={}, source=c.strip().splitlines(True),
                              outputs=[], execution_count=None) for c in CELLS],
                  metadata=dict(kernelspec=dict(name="python3", display_name="Python 3",
                                                language="python"),
                                language_info=dict(name="python")),
                  nbformat=4, nbformat_minor=5)
        json.dump(nb, open(out, "w"), indent=1)
        print("wrote", out)
    else:
        for i, c in enumerate(CELLS, 1):
            print(f"\n{'='*78}\nCELL {i}\n{'='*78}\n{c.strip()}")

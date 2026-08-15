"""
Kaggle notebook body for STEP 3 - repeated seeds and confidence intervals.

Paste each block into its own cell, in order. Settings before running anything:
Accelerator = GPU T4 x2 (or P100), Internet = OFF, Persistence = off.

    python pipeline2/kaggle/kaggle_stage8.py                     # print the cells
    python pipeline2/kaggle/kaggle_stage8.py stage8.ipynb        # write the notebook

WHAT THIS RUNS - 55 fits, about 3.5-4 h on a T4. The longest run in the project, and the most
important one left.

    loco    5 seeds x 5 LOCO folds x 2 heads (proto, linear)   = 50 fits
    frozen  5 seeds x ferguson, space A                        =  5 fits

WHY. Every verdict in this project from Gate 1 onward is a mean over 5 folds at ONE seed compared
against a threshold. That is a decision procedure, not evidence, and it has already produced one
result that looked publishable and was noise (D-38, disproven by D-43). This run settles three
things:

  1. the Gate 6 LOCO headline, currently the bare number 0.3901
  2. Gate 6 check 4 - the sentence "the prototype loss improves cross-cohort transfer", which
     D-44 BANNED because the single-seed margin was +0.0209 with p = 0.460
  3. the support law - the strongest result in the project and so far measured on 9 ferguson
     labels from one fit

NOTHING IS RE-TUNED AND NO VERDICT MOVES. What changes is which sentences may be written.

IT RESUMES. Every fit caches to work/ckpt/s8_*.pt the moment it finishes, so a 12-hour session
limit or a dead kernel costs only the fit that was in flight. Re-run cell 4 and it picks up.
BUDGET NOTE: the free quota is 30 GPU-hours a week and this is ~4 of them. Gate 3 + 3b + 6 + 7
together were 3.6 h, so after this run the project has used well under half a week's quota.
"""

# ============================================================================ CELL 1 - setup
CELL_1 = r'''
import os, shutil, json
SRC = "/kaggle/input/cta-stage3"          # <-- same dataset as Stage 7, rebuilt with make_upload.py
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
    "rebuild the dataset locally with `python pipeline2/kaggle/make_upload.py` and re-upload - "
    "step 3 needs the same inputs Stage 7 needed, including the frozen holdout's value table.")

import torch
print("\ntorch", torch.__version__, "|",
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU")
assert torch.cuda.is_available(), "no GPU - set Accelerator to GPU in the notebook settings"
'''

# ============================================================================ CELL 2 - integrity
CELL_2 = r'''
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
V = len(s2.read_panel(["CRC","UPMC","Keren","Phillips","Sorin","ferguson"])[0])
print("vocabulary:", V)
assert V == 99, f"expected the canonical 99 triples, got {V} - D-39 has regressed"

# This run scores in the SHIPPED space A only. Its prototypes must still line up.
P = np.load(f"{DST}/work/prototypes.npy")
d = pd.read_csv(f"{DST}/work/label_map.csv", keep_default_na=False)
print("space A:", d.cluster.nunique(), "clusters, prototypes", P.shape)
assert P.shape == (d.cluster.nunique(), V)
'''

# ============================================================================ CELL 3 - smoke test
CELL_3 = r'''
# ~4 min. One seed, 2 epochs, both heads, all folds + the frozen fit. Scores nothing and writes
# no report - it exists to prove the code path before committing 4 hours of quota.
import subprocess, glob, os
DST = "/kaggle/working/proj"
r = subprocess.run(["python", "-u", "pipeline2/s8_seeds.py", "--loco", "--frozen",
                    "--seeds", "1", "--quick"], cwd=DST, capture_output=True, text=True)
print(r.stdout[-8000:]); print(r.stderr[-3000:])
assert r.returncode == 0, "smoke test failed - do not start the real run"
assert "device: cuda" in r.stdout, "ran on CPU - the real run would take days"
for p in glob.glob(f"{DST}/work/ckpt/s8_*_quick.pt"):
    os.remove(p)
print("\nsmoke checkpoints removed")
'''

# ============================================================================ CELL 4 - the run
CELL_4 = r'''
# The real run: 55 fits, ~3.5-4 h. Streamed. Every fit caches the moment it finishes, so
# re-running this cell after a timeout resumes rather than restarting.
import subprocess, time
DST = "/kaggle/working/proj"
t0 = time.time()
p = subprocess.Popen(["python", "-u", "pipeline2/s8_seeds.py", "--loco", "--frozen",
                      "--seeds", "5"],
                     cwd=DST, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="")
p.wait()
print(f"\nexit {p.returncode} after {(time.time()-t0)/60:.1f} min")
'''

# ============================================================================ CELL 5 - collect
CELL_5 = r'''
# Render the report, print the three answers, zip.
import os, glob, shutil, torch, pandas as pd
from IPython.display import Markdown, display
DST = "/kaggle/working/proj"

rep = f"{DST}/reports/s8_seeds.md"
if os.path.exists(rep):
    display(Markdown(open(rep, encoding="utf-8").read()))
else:
    print("NO REPORT - the run did not finish. Re-run cell 4; it resumes.")

rows = []
for p in sorted(glob.glob(f"{DST}/work/ckpt/s8_*.pt")):
    if p.endswith("_quick.pt"):
        continue
    r = torch.load(p, weights_only=False)
    rows.append({k: r[k] for k in ("kind", "seed", "held", "head", "f1_core", "epochs",
                                   "val_f1", "seconds")})
d = pd.DataFrame(rows)
print(f"{len(d)} fits of 55 complete\n")
if len(d):
    print(d.groupby(["kind", "head"]).f1_core.agg(["mean", "std", "count"]).round(4).to_string())
    print(f"\ntotal GPU time: {d.seconds.sum()/3600:.2f} h")

shutil.copytree(f"{DST}/reports", "/kaggle/working/out/reports", dirs_exist_ok=True)
# ckpt only - the s8 fits do not store weights, so this stays small
os.makedirs("/kaggle/working/out/ckpt", exist_ok=True)
for p in glob.glob(f"{DST}/work/ckpt/s8_*.pt"):
    shutil.copy2(p, "/kaggle/working/out/ckpt/")
shutil.make_archive("/kaggle/working/stage8_results", "zip", "/kaggle/working/out")
print("\nwrote /kaggle/working/stage8_results.zip",
      round(os.path.getsize("/kaggle/working/stage8_results.zip")/1e6, 1), "MB")
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

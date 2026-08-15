"""
Kaggle notebook body for the Stage 3 lambda sweep (GATE 3).

Paste each numbered block into its own notebook cell, in order. Settings that must be on before
you run anything: Accelerator = GPU T4 x2 (or P100), Internet = OFF, Persistence = off.

Read pipeline2/kaggle/README.md first - it covers building and uploading the dataset.

The point of splitting this into cells is cell 3: a two-minute smoke test that proves the code
path on the GPU BEFORE the real sweep starts spending quota. Stage 3 has already been caught once
by a defect that only appeared at run time, so the cheap check earns its place.
"""

# ============================================================================ CELL 1 - setup
CELL_1 = r'''
import os, sys, shutil, json, subprocess, time

SRC = "/kaggle/input/cta-stage3"          # <-- rename if you named the dataset differently
DST = "/kaggle/working/proj"

assert os.path.isdir(SRC), f"dataset not attached at {SRC} - check the Add Data panel"

# The dataset mount is READ-ONLY and the pipeline writes checkpoints, so everything is copied to
# the writable working directory. config.ROOT is derived from the location of pipeline2/config.py,
# so this layout is what makes ROOT resolve to /kaggle/working/proj.
if os.path.isdir(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)
os.makedirs(f"{DST}/work/ckpt", exist_ok=True)
os.makedirs(f"{DST}/reports/figures", exist_ok=True)

man = json.load(open(f"{DST}/MANIFEST.json"))
print("stage2_arm:", man["stage2_arm"])
print("cohorts   :", man["train_cohorts"])
print("data      :", round(man["total_bytes"] / 1e6, 1), "MB")

import torch
print("\ntorch", torch.__version__, "| cuda", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU")
assert torch.cuda.is_available(), "no GPU - set Accelerator to GPU in the notebook settings"
'''

# ============================================================================ CELL 2 - integrity
CELL_2 = r'''
# Confirm the upload arrived intact. A truncated parquet fails deep inside training otherwise,
# an hour in, and looks like a modelling problem rather than a transfer problem.
import hashlib, json, os
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
bad = []
for f in man["files"]:
    p = os.path.join(DST, f["path"])
    if not os.path.exists(p):
        bad.append((f["path"], "MISSING")); continue
    if os.path.getsize(p) != f["bytes"]:
        bad.append((f["path"], "SIZE")); continue
    if sha(p) != f["sha256_16"]:
        bad.append((f["path"], "HASH"))
print("checked", len(man["files"]), "files")
print("ALL OK" if not bad else f"PROBLEMS: {bad}")
assert not bad
'''

# ============================================================================ CELL 3 - smoke test
CELL_3 = r'''
# ~1-2 minutes. Proves the GPU code path end to end and prints the device line. Scores nothing:
# 2 epochs on 1,500 cells, one fold. Two lambdas on purpose - 0.0 leaves the gradient reversal
# layer a no-op, 0.3 actually exercises it, so both paths are tested.
# If this fails, the real sweep would have failed the same way after burning an hour of quota.
import subprocess, os
DST = "/kaggle/working/proj"
r = subprocess.run([ "python", "-u", "pipeline2/s3_encoder.py", "--lambda-sweep", "--quick",
                     "--lambdas", "0.0,0.3", "--folds", "CRC" ],
                   cwd=DST, capture_output=True, text=True)
print(r.stdout[-6000:])
print(r.stderr[-4000:])
assert r.returncode == 0, "smoke test failed - do not start the real sweep"
assert "device: cuda" in r.stdout, "ran on CPU - the sweep would take 15+ hours"

# Throw the smoke checkpoints away so nothing tagged quick_ can be mistaken for a scored run.
import glob
for p in glob.glob(f"{DST}/work/ckpt/s3_quick_*.pt"):
    os.remove(p)
print("\nsmoke checkpoints removed")
'''

# ============================================================================ CELL 4 - the sweep
CELL_4 = r'''
# The real run: 5 lambdas x 5 LOCO folds = 25 fits. Streamed so progress is visible - a silent
# cell for an hour is indistinguishable from a hung one.
#
# Each fold is cached to work/ckpt/s3_lam*_*.pt as it finishes, so re-running this cell resumes
# rather than restarting. That is what makes a session timeout survivable.
import subprocess, time
DST = "/kaggle/working/proj"
t0 = time.time()
p = subprocess.Popen(["python", "-u", "pipeline2/s3_encoder.py", "--lambda-sweep"],
                     cwd=DST, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="")
p.wait()
print(f"\nexit {p.returncode} after {(time.time()-t0)/60:.1f} min")
'''

# ============================================================================ CELL 5 - collect
CELL_5 = r'''
# Read the verdict, then pull everything out. /kaggle/working is what gets saved with the
# notebook version, so the zip is the thing to download and unpack into work/ckpt/ at home.
import shutil, os, torch, pandas as pd
from IPython.display import Markdown, display
DST = "/kaggle/working/proj"

rep = f"{DST}/reports/s3_encoder.md"
if os.path.exists(rep):
    display(Markdown(open(rep, encoding="utf-8").read()))
else:
    print("NO REPORT - the sweep did not finish all 25 runs. Re-run cell 4; it resumes.")
    p = f"{DST}/reports/s3_encoder_PARTIAL.md"
    if os.path.exists(p):
        display(Markdown(open(p, encoding="utf-8").read()))

sw = torch.load(f"{DST}/work/ckpt/s3_sweep.pt", weights_only=False)
d = pd.DataFrame([{k: r[k] for k in
                   ("lam", "held", "f1_core", "f1_majority", "f1_l2", "fresh_bits", "fresh_acc",
                    "cotrained_bits", "cohort_acc", "n_slide", "seconds")} for r in sw])
print(d.round(4).to_string(index=False))
print(f"\ntotal GPU time: {d.seconds.sum()/60:.1f} min over {len(d)} folds "
      f"({d.seconds.mean()/60:.1f} min each)")

# The fold checkpoints carry their fitted weights, so this zip is what lets a fold be reopened
# at home without a retrain. Reports go in too - the verdict should not live only in this tab.
shutil.copytree(f"{DST}/reports", "/kaggle/working/out/reports", dirs_exist_ok=True)
shutil.copytree(f"{DST}/work/ckpt", "/kaggle/working/out/ckpt", dirs_exist_ok=True)
shutil.make_archive("/kaggle/working/stage3_results", "zip", "/kaggle/working/out")
print("\nwrote /kaggle/working/stage3_results.zip",
      round(os.path.getsize("/kaggle/working/stage3_results.zip") / 1e6, 1), "MB")
'''

# ============================================================================ CELL 6 - STAGE 3b
CELL_6 = r'''
# STAGE 3b - the ablation that closes D-37 and D-38.  ~72 min on a T4.
#
# Gate 3 shipped lambda=0: the adversary did not help. Two candidate reasons, and this cell
# separates them instead of changing both at once (the lesson D-27 taught in Gate 2).
#
#   arm A  --deep-slide  The slide head Gate 3 trained against was ONE nn.Linear, while the probe
#                        that judged it had two hidden layers. So the encoder only had to make
#                        slide identity NON-LINEARLY separable - cheap, and it removes nothing.
#                        Measured: co-trained fell to -3.29 bits, fresh probe still found 89%.
#                        This arm matches the head to the probe, so hiding stops being an option.
#
#   arm B  --nested      On this roster a slide is often a whole PATIENT: Keren 1.00 slides per
#                        patient, Sorin 1.13, against CRC 4.00, UPMC 3.80, Phillips 4.93. So
#                        51-73% of what the adversary erased in 4 of 5 folds was patient identity,
#                        which is tumour biology. This arm restricts the domain to slides SHARING
#                        A PATIENT - technical by construction.
#
#   arm C  both          Do they compound?
#
# lambda=0 is NOT rerun: gradient reversal is a true no-op there, so the encoder is identical to
# Gate 3's and 0.3642 is already the shared baseline.
import subprocess, time
DST = "/kaggle/working/proj"
ARMS = [("A  deep discriminator (D-37)", ["--deep-slide"]),
        ("B  nested domain (D-38)",      ["--nested"]),
        ("C  both",                      ["--deep-slide", "--nested"])]
t0 = time.time()
for name, flags in ARMS:
    print(f"\n{'='*70}\nARM {name}\n{'='*70}", flush=True)
    p = subprocess.Popen(["python", "-u", "pipeline2/s3_encoder.py", "--lambda-sweep",
                          "--lambdas", "0.03,0.1,0.3"] + flags,
                         cwd=DST, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        print(line, end="")
    p.wait()
    print(f"arm exit {p.returncode}")
print(f"\nall arms done in {(time.time()-t0)/60:.1f} min")
'''

# ============================================================================ CELL 7 - compare
CELL_7 = r'''
# The comparison. Gate 3's lambda=0 is the baseline every arm is measured against.
import torch, pandas as pd, os
DST = "/kaggle/working/proj"

# From the completed Gate 3 run (reports/s3_encoder.md). lambda=0, per fold.
BASE = {"CRC": 0.2770, "UPMC": 0.3848, "Keren": 0.3978, "Phillips": 0.4287, "Sorin": 0.3324}
BASE_MEAN = 0.3642

rows = []
for tag, name in [("d_", "A deep"), ("n_", "B nested"), ("nd_", "C both")]:
    f = f"{DST}/work/ckpt/s3_{tag}sweep.pt"
    if not os.path.exists(f):
        print(f"MISSING {f} - arm did not finish"); continue
    for r in torch.load(f, weights_only=False):
        rows.append(dict(arm=name, lam=r["lam"], held=r["held"], f1=r["f1_core"],
                         base=BASE[r["held"]], gain=round(r["f1_core"] - BASE[r["held"]], 4),
                         fresh=round(r["fresh_bits"], 2), cotr=round(r["cotrained_bits"], 2),
                         coh=round(r["cohort_acc"], 3), n_slide=r["n_slide"]))
d = pd.DataFrame(rows)

print("MEAN over the 5 folds, against Gate 3 lambda=0 = %.4f\n" % BASE_MEAN)
m = d.groupby(["arm", "lam"]).agg(f1=("f1", "mean"), gain=("gain", "mean"),
                                  fresh=("fresh", "mean"), cotr=("cotr", "mean"),
                                  coh=("coh", "mean"), slides=("n_slide", "mean")).round(4)
print(m.to_string())

print("\n\nDID THE ADVERSARY ACTUALLY REMOVE ANYTHING THIS TIME?")
print("Gate 3 kept 89% of the slide bits at lambda=0.1 while its co-trained head hit -3.29.")
print("A working adversary should now show FRESH bits falling, not just co-trained.\n")
print(d.groupby(["arm", "lam"])[["fresh", "cotr"]].mean().round(2).to_string())

print("\n\nPER FOLD - gain over Gate 3 lambda=0\n")
print(d.pivot_table(index=["arm", "lam"], columns="held", values="gain").round(4).to_string())
'''

CELLS = [CELL_1, CELL_2, CELL_3, CELL_4, CELL_5, CELL_6, CELL_7]

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else None
    if out:                       # write a .ipynb you can upload directly
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

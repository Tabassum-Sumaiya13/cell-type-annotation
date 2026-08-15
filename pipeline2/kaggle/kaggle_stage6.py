"""
Kaggle notebook body for GATE 6 - Stage 6, losses and training.

Paste each block into its own cell, in order. Settings before running anything:
Accelerator = GPU T4 x2 (or P100), Internet = OFF, Persistence = off.

    python pipeline2/kaggle/kaggle_stage6.py                     # print the cells
    python pipeline2/kaggle/kaggle_stage6.py stage6.ipynb        # write the notebook

Its own notebook rather than more cells on stage3.ipynb: Stage 6 is a separate gate with separate
outputs, and mixing them means every future re-run of one risks touching the other's checkpoints.

WHAT GATE 6 RUNS - 16 fits, about 30-40 min on a T4 at Stage 3's measured rate.
    proto3   prototype loss + masked-marker + VICReg      x 5 LOCO folds
    proto2   prototype loss + masked-marker               x 5 LOCO folds
    linear   Stage 3's plain linear head, same encoder    x 5 LOCO folds   <- check 4's control
    noconf   confidence weighting off, UPMC only          x 1             <- check 6

READ THIS BEFORE READING THE RESULT. Three things the design asked for are NOT in this stage, each
declared in pipeline2/panel/gate6_expect.csv before any code was written:
  - descendant-tolerant cross-entropy - blocked by the untrusted nesting graph (D-41)
  - the neighbourhood-context loss    - needs Stage 4, which is deferred, so the declared
                                        "2 vs 4 losses" ablation is a 2 vs 3 (D-40)
  - the adversary                     - Gate 3 shipped lambda=0 (D-36)
"""

# ============================================================================ CELL 1 - setup
CELL_1 = r'''
import os, shutil, json
SRC = "/kaggle/input/cta-stage3"          # <-- the same dataset; rename here if yours differs
DST = "/kaggle/working/proj"

assert os.path.isdir(SRC), f"dataset not attached at {SRC} - check the Add Data panel"
if os.path.isdir(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)
os.makedirs(f"{DST}/work/ckpt", exist_ok=True)
os.makedirs(f"{DST}/reports/figures", exist_ok=True)

man = json.load(open(f"{DST}/MANIFEST.json"))
print("stage2_arm:", man["stage2_arm"], "| data", round(man["total_bytes"]/1e6, 1), "MB")

# Stage 6 needs three inputs Stage 3 did not. Missing any of them does NOT crash - it silently
# falls back to random prototypes or uniform weights, and the gate would score a different model
# than the one intended. So they are asserted, not hoped for.
need = ["work/prototypes.npy", "work/s2_dynrange.csv", "work/label_map.csv", "work/panel.json"]
for f in need:
    assert os.path.exists(f"{DST}/{f}"), f"MISSING {f} - rebuild the upload with make_upload.py"
print("label_conf:", os.listdir(f"{DST}/work/label_conf")
      if os.path.isdir(f"{DST}/work/label_conf") else "NONE (confidence weighting will be off)")

import torch
print("\ntorch", torch.__version__, "|",
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU")
assert torch.cuda.is_available(), "no GPU - set Accelerator to GPU in the notebook settings"
'''

# ============================================================================ CELL 2 - integrity
CELL_2 = r'''
# Confirm the upload arrived intact, and that the two things D-39 and D-42 broke are right.
import hashlib, json, os, sys, numpy as np
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

# D-39: the vocabulary must come from panel.json and be 99 even though ferguson is not uploaded.
# It was 88 here once, which silently dropped ident.weight from the warm start.
sys.path.insert(0, f"{DST}/pipeline2")
os.chdir(DST)
import s2_tokens as s2, s3_encoder as s3
V = len(s2.read_panel(s3.available())[0])
print("vocabulary:", V)
assert V == 99, f"expected the canonical 99 triples, got {V} - D-39 has regressed"

# D-42: prototypes are [25, 99] and ~30% NaN by design; the NaNs route to the [ABSENT] token.
P = np.load(f"{DST}/work/prototypes.npy")
print("prototypes:", P.shape, "| NaN", int(np.isnan(P).sum()), "of", P.size,
      "(expected - a cluster has no signature for a marker none of its cohorts measures)")
assert P.shape[1] == V
'''

# ============================================================================ CELL 3 - smoke test
CELL_3 = r'''
# ~2 min. Two folds so check 6 (confidence on/off, UPMC) is exercised too. Scores nothing:
# 2 epochs on 1,500 cells. Its checkpoints are quick_-tagged and deleted straight after.
import subprocess, glob, os
DST = "/kaggle/working/proj"
r = subprocess.run(["python", "-u", "pipeline2/s6_train.py", "--ablate-losses", "--quick",
                    "--folds", "CRC,UPMC"], cwd=DST, capture_output=True, text=True)
print(r.stdout[-7000:]); print(r.stderr[-3000:])
assert r.returncode == 0, "smoke test failed - do not start the real run"
assert "device     : cuda" in r.stdout, "ran on CPU - the real run would take hours"
# guard=COLLAPSE on every fold is how the D-42 prototype-NaN bug showed itself. If it reappears,
# stop: the prototypes are broken and every number after this point is meaningless.
assert "guard=COLLAPSE" not in r.stdout, "prototypes collapsed at init - check D-42"
for p in glob.glob(f"{DST}/work/ckpt/s6_quick_*.pt"):
    os.remove(p)
print("\nsmoke checkpoints removed")
'''

# ============================================================================ CELL 4 - GATE 6
CELL_4 = r'''
# The real run: 16 fits. Streamed, and each fold caches to work/ckpt/s6_*.pt as it finishes, so
# re-running this cell resumes rather than restarting.
import subprocess, time
DST = "/kaggle/working/proj"
t0 = time.time()
p = subprocess.Popen(["python", "-u", "pipeline2/s6_train.py", "--ablate-losses"],
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

rep = f"{DST}/reports/s6_train.md"
if os.path.exists(rep):
    display(Markdown(open(rep, encoding="utf-8").read()))
else:
    print("NO REPORT - the run did not finish all 16 fits. Re-run cell 4; it resumes.")

sw = torch.load(f"{DST}/work/ckpt/s6_sweep.pt", weights_only=False)
d = pd.DataFrame([{k: r[k] for k in ("tag", "held", "head", "vicreg", "conf",
                                     "f1_core", "f1_all", "f1_majority", "seconds")} for r in sw])
d["epochs"] = [r["info"]["epochs_used"] for r in sw]
print(d.round(4).to_string(index=False))

print("\nMEAN by arm:")
print(d.groupby(["head", "vicreg", "conf"]).f1_core.agg(["mean", "std", "count"]).round(4).to_string())
print(f"\ntotal GPU time: {d.seconds.sum()/60:.1f} min over {len(d)} fits")

# check 6 - confidence weighting, UPMC only. 1-of-5 coverage; never a roster-wide claim.
u = d[(d.held == "UPMC") & (d["head"] == "proto") & (d["vicreg"])]
if len(u) == 2:
    on = float(u[u["conf"]].f1_core.iloc[0]); off = float(u[~u["conf"]].f1_core.iloc[0])
    print(f"\ncheck 6 - UPMC only: confidence ON {on:.4f} vs OFF {off:.4f} -> {on-off:+.4f}")

shutil.copytree(f"{DST}/reports", "/kaggle/working/out/reports", dirs_exist_ok=True)
shutil.copytree(f"{DST}/work/ckpt", "/kaggle/working/out/ckpt", dirs_exist_ok=True)
shutil.make_archive("/kaggle/working/stage6_results", "zip", "/kaggle/working/out")
print("\nwrote /kaggle/working/stage6_results.zip",
      round(os.path.getsize("/kaggle/working/stage6_results.zip")/1e6, 1), "MB")
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

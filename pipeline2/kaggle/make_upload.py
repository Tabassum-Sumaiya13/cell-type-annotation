"""
Build the folder to upload to Kaggle as a Dataset for the GPU stages (3, 3b, 6, 7).

    python pipeline2/kaggle/make_upload.py            # writes work/kaggle_upload/
    python pipeline2/kaggle/make_upload.py --out D:/somewhere/else

WHY CODE AND DATA GO IN ONE DATASET, not a git clone in the notebook.
A `git clone` needs Internet enabled on the notebook and a token if the repo is private, and it
lets the code drift from the numbers - you would not know afterwards which commit produced a
result. One upload pins the exact code and the exact tables together, and the notebook can run
with Internet OFF.

WHAT IS DELIBERATELY LEFT OUT.
  work/raw/*.parquet      627 MB of acquisition output. Stage 3 opens none of it - see
                          s3_encoder.available(). Including it would be an 8x bigger upload for
                          an existence check.
  Datasets/               The source data. Stage 1 already reduced it to the value tables.
  *_rand, *_slidestats    Stage 1 diagnostics, unused from Stage 2 onward.

THE FROZEN HOLDOUT IS NOW INCLUDED, AND THAT IS A DELIBERATE CHANGE (D-48). Through Stage 6 this
file said of ferguson_full.parquet: "it is never trained on and Stage 3 never loads it, so there
is no reason for it to leave this machine." Stage 7 is the reason. It is the stage that scores
the holdout, and it cannot do that with the table on another computer.

  Nothing about the freeze changes. ferguson is loaded by s7_eval.load_frozen, which builds a
  `test` tensor and NOTHING else - deliberately not s6.load_cohort, which would create a `train`
  key holding holdout cells even if nothing read it. s7_eval asserts the training cohort list is
  exactly the five and that ferguson is absent from it (gate 7 check 0), and that assert runs on
  Kaggle, not just here.

  What DOES change is that the holdout now sits in a private Kaggle dataset, so it can be scored
  more than once. The protection against re-scoring until a number looks good was never the file
  location - it is that the gate thresholds are committed before the run and the result is
  recorded whatever it is. Keep that.
"""
import os, sys, json, shutil, hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from config import ROOT, WORK, SPECS

TRAIN = [c for c, s in SPECS.items() if s['role'] == 'train']
FROZEN = 'ferguson'


def sha(p, n=1 << 20):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while True:
            b = f.read(n)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:16]


def main():
    out = (sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv
           else os.path.join(WORK, 'kaggle_upload'))
    if os.path.exists(out):
        shutil.rmtree(out)

    # ---- the code, minus caches. Small enough that pinning all of it is free.
    shutil.copytree(os.path.join(ROOT, 'pipeline2'), os.path.join(out, 'pipeline2'),
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'kaggle'))

    # ---- exactly the tables the GPU stages read
    want = [(os.path.join(WORK, 'values', f'{c}_full.parquet'), f'work/values/{c}_full.parquet')
            for c in TRAIN if os.path.exists(os.path.join(WORK, 'values', f'{c}_full.parquet'))]
    # Stage 6 additions. prototypes.npy seeds the prototype loss and label_conf/ carries the one
    # cohort with a real label confidence - without them Stage 6 falls back to random prototypes
    # and uniform weights, silently, and the gate would score a different model than intended.
    want += [(os.path.join(WORK, 'prototypes.npy'), 'work/prototypes.npy'),
             (os.path.join(WORK, 's2_dynrange.csv'), 'work/s2_dynrange.csv')]
    if os.path.isdir(os.path.join(WORK, 'label_conf')):
        want += [(os.path.join(WORK, 'label_conf', f), f'work/label_conf/{f}')
                 for f in sorted(os.listdir(os.path.join(WORK, 'label_conf')))]
    # Stage 7 additions. The frozen holdout's value table (D-48 - see the module docstring), and
    # the two CLEAN label spaces with their prototypes. The spaces are built locally by
    # s7_spaces.py because that needs work/s1b_signatures.npz, which is 100 MB and has no other
    # consumer on Kaggle - shipping the finished CSVs instead keeps the upload small.
    fz = os.path.join(WORK, 'values', f'{FROZEN}_full.parquet')
    want += [(fz, f'work/values/{FROZEN}_full.parquet')]
    for tag in ('B1', 'B2'):
        want += [(os.path.join(WORK, f'label_map_{tag}.csv'), f'work/label_map_{tag}.csv'),
                 (os.path.join(WORK, f'prototypes_{tag}.npy'), f'work/prototypes_{tag}.npy')]
    # Stage 11 additions (H13b). Same build-locally / train-on-GPU split as the Stage 7 spaces
    # directly above, and for the same reason: constructing these needs s1b_signatures.npz, but
    # TRAINING in them needs only the finished mapping and the centroids - 91 KB against 100 MB.
    for tag in ('hand', 'derived', 'matched'):
        want += [(os.path.join(WORK, f'label_map_s11_{tag}.csv'),
                  f'work/label_map_s11_{tag}.csv'),
                 (os.path.join(WORK, f'proto_s11_{tag}.npy'), f'work/proto_s11_{tag}.npy')]
    want += [(os.path.join(WORK, 's11_spaces.json'), 'work/s11_spaces.json')]
    want += [(os.path.join(WORK, 'marker_registry.csv'), 'work/marker_registry.csv'),
             (os.path.join(WORK, 'label_map.csv'), 'work/label_map.csv'),
             (os.path.join(WORK, 'panel.json'), 'work/panel.json'),
             (os.path.join(WORK, 'ckpt', 's2_armB.pt'), 'work/ckpt/s2_armB.pt'),
             (os.path.join(WORK, 'ckpt', 's2_armA.pt'), 'work/ckpt/s2_armA.pt'),
             (os.path.join(ROOT, '_validation', 'hand_mapping_reference.csv'),
              '_validation/hand_mapping_reference.csv')]

    manifest, missing, total = [], [], 0
    for src, rel in want:
        if not os.path.exists(src):
            missing.append(rel)
            continue
        dst = os.path.join(out, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        n = os.path.getsize(src)
        total += n
        manifest.append(dict(path=rel, bytes=n, sha256_16=sha(src)))

    # The checkpoint directory must exist and be writable on the Kaggle side; the dataset mount is
    # read-only, so the notebook copies everything into /kaggle/working first (see README).
    os.makedirs(os.path.join(out, 'work', 'ckpt'), exist_ok=True)
    os.makedirs(os.path.join(out, 'reports', 'figures'), exist_ok=True)

    arm = json.load(open(os.path.join(WORK, 'panel.json'))).get('stage2_arm', 'set')
    json.dump(dict(stage='7', stage2_arm=arm, train_cohorts=TRAIN, frozen=FROZEN,
                   total_bytes=total, files=manifest),
              open(os.path.join(out, 'MANIFEST.json'), 'w'), indent=2)

    code = sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(os.path.join(out, 'pipeline2')) for f in fs)
    print(f"upload folder: {out}")
    print(f"  code   {code / 1e6:6.2f} MB")
    print(f"  data   {total / 1e6:6.2f} MB   ({len(manifest)} files)")
    print(f"  TOTAL  {(code + total) / 1e6:6.2f} MB")
    print(f"  stage2_arm = {arm}")
    if missing:
        print("\n  MISSING (Stage 3 will fail without these):")
        for m in missing:
            print(f"    {m}")
    else:
        print("\n  nothing missing. Zip this folder and upload it as a Kaggle Dataset.")


if __name__ == "__main__":
    main()

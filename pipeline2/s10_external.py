"""Stage 10 - THE EXTERNAL BASELINE. Closes H13(a).

    python pipeline2/s10_external.py                 # all arms, 5 LOCO folds
    python pipeline2/s10_external.py --arms maps_core9,gbm_core9
    python pipeline2/s10_external.py --quick         # smoke test, scores nothing

WHY THIS EXISTS. Every number in this project so far is compared against majority-class and
random-uniform. Those are sanity checks a working model cannot fail, so Gate 6's 0.3901 and Gate
7's 0.3309 are uninterpretable to a reader: there is no published method on the same folds, in the
same label space, on the same cells. H13 recorded this on 2026-08-11 as "what makes every other
number in the thesis readable". This file is that comparison.

WHAT IS BEING COMPARED. Not architectures in the abstract - the SAME PREDICTION TASK. Identical
LOCO folds, identical 25-cluster Stage 1b label space, identical slide splits, identical drawn
cells, identical macro-F1 with the identical stroma waiver. Everything except the model is held
fixed, and the loader is asserted bit-identical to s6.load_cohort (check 0) rather than
reimplemented and hoped about.

THE BASELINE IS MAPS (Shaban et al., Nat Commun 2023, 10.1038/s41467-023-39698-6), reimplemented
from its published Methods: four fully connected hidden layers of 512 units, ReLU, dropout 0.10,
softmax output, Adam at lr 1e-3, batch 128, early stopping on validation loss. It is the method
this project's own files/10 already names as its comparison point.

TWO FEATURE SETS, AND THE SECOND ONE IS THE REAL EXPERIMENT:

  core9   the 9 triples every training cohort measures. This is what MAPS can honestly do in a
          cross-cohort setting: it assumes ONE FIXED PANEL, so the only panel that exists for all
          five cohorts is their intersection. This is the fair reading of "what would a published
          method achieve here".
  full99  all 99 vocabulary slots with UNMEASURED MARKERS SET TO ZERO. This is the exact failure
          mode Stage 2 was built to fix - a zero means "this cell is negative", not "nobody
          looked". Running a published architecture this way MEASURES the cost of that choice
          instead of asserting it, which is the thing Stage 2's docstring claims and never tested
          against an outside method.

  full99+area adds cell area, which MAPS's published input includes and this pipeline's tokens do
          not. It is here so that "MAPS lost because you crippled its input" is not available as
          an objection.

GRADIENT BOOSTING is carried alongside as the dumb-but-strong control. If a histogram gradient
boosting classifier on nine markers matches the set transformer, that is a finding, and it is
consistent with two measurements this project already has: Gate 2's wide panel beating its own
core-9 control by only +0.026 R2, and Gate 6's prototype head beating the linear head by +0.0209
at p = 0.460.

WHAT THIS FILE DOES NOT DO. It does not re-tune anything, it does not touch the label space, and
it writes no checkpoint any other stage reads. A baseline that gets tuned while the model does not
is not a baseline.
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                                        # noqa: E402
from config import WORK, REPORTS, RAW, SEED                          # noqa: E402
import s1_values as s1                                               # noqa: E402
import s2_tokens as s2                                               # noqa: E402
import s3_encoder as s3                                              # noqa: E402
import s6_train as s6                                                # noqa: E402

CKPT = os.path.join(WORK, 'ckpt')
OUT = os.path.join(REPORTS, 's10_external.md')
DEV = s6.DEV

# The roster the Gate 6 / Gate 7 checkpoints were actually trained on, PINNED as a literal.
# Not derived from `role == 'train'`: config.SPECS['Danenberg'] still carries role='train' from
# before D-24 repurposed it as the arrives-later cohort, and Stage 9 has now written it a wide
# value table - so `[c for c in s3.available() if role == 'train']` silently returns SIX cohorts
# on this machine and would compare a 6-cohort baseline against a 5-cohort model.
TRAIN = ['CRC', 'Keren', 'Phillips', 'Sorin', 'UPMC']

# --------------------------------------------------------------- MAPS, from the published Methods
MAPS_WIDTH, MAPS_DEPTH, MAPS_DROP = 512, 4, 0.10
MAPS_LR, MAPS_BATCH = 1e-3, 128
MAPS_EPOCHS, MAPS_PATIENCE = 100, 15      # the paper says 100-500 with early stopping on val loss;
                                          # 100 is its stated setting for cHL1 and bounds CPU cost.
                                          # epochs_used is reported per fold, so a run that hits
                                          # the ceiling is visible rather than hidden.
GBM_ITERS = 200


class MAPS(nn.Module):
    """Shaban et al.'s feedforward classifier, as described in its Methods section.

    Four fully connected hidden layers of 512 with ReLU and dropout 0.10, then a softmax output
    layer. Written out rather than imported so the exact architecture being compared is visible in
    this file and cannot drift.
    """

    def __init__(self, n_in, n_class):
        super().__init__()
        layers, d = [], n_in
        for _ in range(MAPS_DEPTH):
            layers += [nn.Linear(d, MAPS_WIDTH), nn.ReLU(), nn.Dropout(MAPS_DROP)]
            d = MAPS_WIDTH
        self.body = nn.Sequential(*layers)
        self.out = nn.Linear(d, n_class)

    def forward(self, x):
        return self.out(self.body(x))


# ----------------------------------------------------------------------------- data
def core_slots(train, tri2idx):
    """The triples EVERY training cohort measures - the only panel MAPS could actually be given.

    Read from panel.json's per-cohort lists, not recomputed, so it is the same intersection Gate 1
    used.
    """
    _, _, per, _, _ = s2.read_panel(train)
    inter = set(per[train[0]])
    for c in train[1:]:
        inter &= set(per[c])
    tl = sorted(inter)
    return tl, np.array([tri2idx[t] for t in tl])


def area_feature(c, cell_ids):
    """Per-cohort ECDF rank of cell area, aligned to the drawn cells.

    Ranked inside the cohort for the same reason every other value in this pipeline is: raw area
    in pixels is not comparable across a 0.38 um/px CODEX slide and a 1.0 um/px IMC one, and a
    baseline handed an uncomparable feature is not a fair baseline.
    """
    d = pd.read_parquet(config.raw_table(c), columns=['cell_id', 'area_px2'])
    d['u'] = d.area_px2.rank(pct=True, method='average').astype('float32')
    return d.set_index('cell_id').u.reindex(cell_ids).fillna(0.5).to_numpy('float32')


def load_fold(c, per_c, tri2idx, V, L, excl):
    """s6.load_cohort, plus the cell ids it does not return, ASSERTED identical to it (check 0).

    The whole value of this file is that the baseline sees exactly what the model saw. Rather than
    trust that a second loader draws the same cells, this one reproduces the draw and then
    compares the resulting tensors to the canonical loader element by element. If the assert ever
    fires the comparison is void, which is the correct outcome.
    """
    tl = list(per_c)
    v = pd.read_parquet(s2.full_table(c),
                        columns=['cell_id', 'image_id', 'native_label'] +
                                [f'u_coh::{t}' for t in tl])
    y = np.array([L['key'].get((c, str(lab)), -1) for lab in v.native_label])
    ok = y >= 0
    if not ok.any():
        return None
    v, y = v[ok].reset_index(drop=True), y[ok]
    U = v[[f'u_coh::{t}' for t in tl]].to_numpy('float32')
    img = np.array([f'{c}|{s}' for s in v.image_id])
    tr_s, va_s, te_s = s2.slide_split(c, np.unique(img))

    def draw(slides, cap, why):
        w = np.flatnonzero(np.isin(img, list(slides)))
        if len(w) > cap:
            w = np.sort(s6._rng('draw', c, why).choice(w, cap, replace=False))
        return w

    parts = dict(train=draw(tr_s, s6.N_TRAIN, 'train'),
                 val=draw(va_s, s6.N_TRAIN // 4, 'val'),
                 test=draw(te_s, s6.SCORE_CELLS, 'test'))

    slots = np.array([tri2idx[t] for t in tl])
    full = np.zeros((len(U), V), 'float32')
    full[:, slots] = U
    ids = v.cell_id.to_numpy()
    area = area_feature(c, ids)

    ref = s6.load_cohort(c, per_c, tri2idx, V, L, excl)
    for k in parts:
        assert np.array_equal(full[parts[k]], ref['U'][k].cpu().numpy()), \
            f'check 0 FAILED: {c}/{k} features differ from s6.load_cohort'
        assert np.array_equal(y[parts[k]], ref['y'][k].cpu().numpy()), \
            f'check 0 FAILED: {c}/{k} labels differ from s6.load_cohort'

    return dict(cohort=c,
                X={k: full[w] for k, w in parts.items()},
                y={k: y[w] for k, w in parts.items()},
                area={k: area[w] for k, w in parts.items()},
                n={k: len(w) for k, w in parts.items()})


def features(data, cohorts, split, arm, slots):
    """Assemble one arm's feature matrix. The ONLY thing that differs between arms."""
    X = np.concatenate([data[c]['X'][split] for c in cohorts]) if len(cohorts) > 1 \
        else data[cohorts[0]]['X'][split]
    if arm.endswith('core9'):
        X = X[:, slots]
    if arm.endswith('area'):
        A = np.concatenate([data[c]['area'][split] for c in cohorts]) if len(cohorts) > 1 \
            else data[cohorts[0]]['area'][split]
        X = np.concatenate([X, A[:, None]], axis=1)
    return X


def labels(data, cohorts, split):
    return np.concatenate([data[c]['y'][split] for c in cohorts]) if len(cohorts) > 1 \
        else data[cohorts[0]]['y'][split]


# ----------------------------------------------------------------------------- fitting
def fit_maps(Xtr, ytr, Xva, yva, n_class, epochs, seed=SEED):
    torch.manual_seed(seed)
    m = MAPS(Xtr.shape[1], n_class).to(DEV)
    opt = torch.optim.Adam(m.parameters(), lr=MAPS_LR)
    lossf = nn.CrossEntropyLoss()
    Xtr_t = torch.from_numpy(Xtr).to(DEV)
    ytr_t = torch.from_numpy(ytr).long().to(DEV)
    Xva_t = torch.from_numpy(Xva).to(DEV)
    yva_t = torch.from_numpy(yva).long().to(DEV)
    g = torch.Generator().manual_seed(seed)
    best, best_state, bad, used = np.inf, None, 0, 0
    for ep in range(epochs):
        m.train()
        order = torch.randperm(len(Xtr_t), generator=g).to(DEV)
        for i in range(0, len(order), MAPS_BATCH):
            b = order[i:i + MAPS_BATCH]
            opt.zero_grad()
            lossf(m(Xtr_t[b]), ytr_t[b]).backward()
            opt.step()
        m.eval()
        with torch.no_grad():
            vl = float(lossf(m(Xva_t), yva_t))
        used = ep + 1
        if vl < best - 1e-5:
            best, bad = vl, 0
            best_state = {k: v.detach().clone() for k, v in m.state_dict().items()}
        else:
            bad += 1
            if bad >= MAPS_PATIENCE:
                break
    if best_state is not None:
        m.load_state_dict(best_state)
    m.eval()
    return m, used, best


def predict_maps(m, X):
    out = []
    with torch.no_grad():
        T = torch.from_numpy(X).to(DEV)
        for i in range(0, len(T), 4096):
            out.append(m(T[i:i + 4096]).argmax(1).cpu().numpy())
    return np.concatenate(out)


def fit_gbm(Xtr, ytr, Xva, yva, n_class, iters):
    from sklearn.ensemble import HistGradientBoostingClassifier
    g = HistGradientBoostingClassifier(max_iter=iters, learning_rate=0.1,
                                       early_stopping=True, n_iter_no_change=15,
                                       validation_fraction=0.15, random_state=SEED)
    g.fit(Xtr, ytr)
    return g, int(g.n_iter_), np.nan


# ----------------------------------------------------------------------------- one fold
def run_fold(arm, held, train, data, slots, L, epochs, iters):
    t0 = time.time()
    rest = [c for c in train if c != held]
    Xtr, ytr = features(data, rest, 'train', arm, slots), labels(data, rest, 'train')
    Xva, yva = features(data, rest, 'val', arm, slots), labels(data, rest, 'val')
    Xte, yte = features(data, [held], 'test', arm, slots), labels(data, [held], 'test')

    if arm.startswith('maps'):
        m, used, vl = fit_maps(Xtr, ytr, Xva, yva, L['n'], epochs)
        yp = predict_maps(m, Xte)
    else:
        m, used, vl = fit_gbm(Xtr, ytr, Xva, yva, L['n'], iters)
        yp = m.predict(Xte)

    f1_core, _ = s3.macro_f1(yte, yp, L['n'], drop=L['unreliable'])
    f1_all, _ = s3.macro_f1(yte, yp, L['n'])
    r = dict(arm=arm, held=held, n_feat=Xtr.shape[1], n_train=len(ytr),
             f1_core=round(f1_core, 4), f1_all=round(f1_all, 4),
             iters=used, seconds=round(time.time() - t0, 1))
    print(f"    {arm:16s} held={held:9s} feat={Xtr.shape[1]:3d}  "
          f"F1core={f1_core:.4f}  iters={used:3d}  {r['seconds']:5.1f}s")
    return r


# ----------------------------------------------------------------------------- the model's number
def gate6_folds():
    """Gate 6's shipped arm, per fold, so the comparison is PAIRED rather than mean-vs-mean.

    proto2 = prototype head + 2 losses, which is what D-44 ships. Returns {} if the sweep file is
    not on disk, in which case the report prints the baseline alone and says so.
    """
    p = os.path.join(CKPT, 's6_sweep.pt')
    if not os.path.exists(p):
        return {}
    sw = torch.load(p, weights_only=False)
    return {r['held']: float(r['f1_core']) for r in sw if r['tag'].startswith('proto2_')}


def paired(model, base):
    """Mean difference over folds with a bootstrap interval - n=5, so no t-test is claimed.

    H9 is the standing complaint that no gate in this project carries an interval. Introducing a
    new comparison without one would repeat the mistake in the file written to fix it.
    """
    ks = sorted(set(model) & set(base))
    if len(ks) < 2:
        return None
    d = np.array([model[k] - base[k] for k in ks])
    rng = np.random.default_rng(SEED)
    bs = np.array([rng.choice(d, len(d), replace=True).mean() for _ in range(10_000)])
    return dict(folds=ks, diff=d, mean=float(d.mean()),
                lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                wins=int((d > 0).sum()), n=len(d))


# ----------------------------------------------------------------------------- report
def write_report(R, g6, mins, arms):
    L_, A = [], lambda s: L_.append(s)
    A('# Stage 10 - the external baseline (closes H13a)\n')
    A('MAPS (Shaban et al., *Nat Commun* 2023) reimplemented from its published Methods and run '
      'on the **identical LOCO folds, identical 25-cluster Stage 1b label space, identical slide '
      'splits and identical drawn cells** as Gate 6. Loader asserted bit-identical to '
      '`s6.load_cohort` (check 0). Nothing was tuned for either side.\n')
    piv = R.pivot_table(index='arm', columns='held', values='f1_core')
    piv['mean'] = piv.mean(axis=1)
    if g6:
        piv.loc['STAGE 6 (proto2, shipped)'] = pd.Series({**g6, 'mean': np.mean(list(g6.values()))})
    A('## macro-F1 (reliable clusters), per held-out cohort\n')
    A(piv.round(4).sort_values('mean', ascending=False).to_markdown())
    A('')
    if g6:
        A('## Paired comparison against Gate 6\n')
        A('Per-fold differences with a bootstrap 95% interval. n=5, so this is an interval, not '
          'a significance claim (H9).\n')
        A('| baseline | Stage 6 - baseline | 95% CI | folds Stage 6 wins |')
        A('|---|---|---|---|')
        for arm in arms:
            b = {r.held: r.f1_core for r in R[R.arm == arm].itertuples()}
            p = paired(g6, b)
            if p:
                A(f'| {arm} | **{p["mean"]:+.4f}** | [{p["lo"]:+.4f}, {p["hi"]:+.4f}] | '
                  f'{p["wins"]}/{p["n"]} |')
        A('')
        A('An interval that spans zero means the shipped model is **not** demonstrably better '
          'than that baseline on this roster.\n')
    A('## What each arm means\n')
    A('- `*_core9` - the 9 markers every training cohort measures. The only fixed panel a '
      'single-panel method could actually be given here.')
    A('- `*_full99` - all 99 vocabulary slots with unmeasured markers set to **0**. This is the '
      'failure mode Stage 2 exists to fix; the gap between core9 and full99 is its cost, measured '
      'against an outside architecture rather than asserted.')
    A('- `*_area` - adds cell area, which MAPS\'s published input includes and the token model '
      'does not, so the baseline cannot be said to have been starved.\n')
    A(f'\n{len(R)} fits, {mins:.1f} min, CPU.\n')
    os.makedirs(REPORTS, exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write('\n'.join(L_))
    return piv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arms', default='maps_core9,maps_full99,maps_full99_area,'
                                      'gbm_core9,gbm_full99')
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    arms = a.arms.split(',')
    epochs = 3 if a.quick else MAPS_EPOCHS
    iters = 10 if a.quick else GBM_ITERS

    train = list(TRAIN)
    missing = [c for c in train if not os.path.exists(s2.full_table(c))]
    assert not missing, f'no wide value table for {missing}'
    triples, tri2idx, per, _, _ = s2.read_panel(train)
    V = len(triples)
    L = s3.label_space()
    excl = s6.excluded_pairs()
    tl9, slots = core_slots(train, tri2idx)

    print(f'label space : {L["n"]} clusters, {len(L["unreliable"])} unreliable')
    print(f'vocabulary  : {V} triples | shared core: {len(tl9)}')
    print(f'folds       : {", ".join(train)}')
    print(f'device      : {DEV}\n')

    print('loading (each fold asserted identical to s6.load_cohort) ...')
    data = {c: load_fold(c, per[c], tri2idx, V, L, excl) for c in train}
    data = {c: d for c, d in data.items() if d is not None}
    print(f'  check 0: all {len(data)} cohorts bit-identical to s6.load_cohort: OK\n')

    t0, res = time.time(), []
    for arm in arms:
        print(f'  arm {arm}')
        for held in train:
            res.append(run_fold(arm, held, train, data, slots, L, epochs, iters))
    R = pd.DataFrame(res)
    mins = (time.time() - t0) / 60
    if a.quick:
        print(f'\n--quick: {mins:.1f} min, scores nothing, no report written')
        return
    piv = write_report(R, gate6_folds(), mins, arms)
    print()
    print(piv.round(4).sort_values('mean', ascending=False).to_string())
    print(f'\nreport -> {OUT}')


if __name__ == '__main__':
    main()

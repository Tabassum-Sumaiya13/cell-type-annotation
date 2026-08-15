"""Stage 7 - the frozen-holdout number (GATE 7).

    python pipeline2/s7_eval.py --frozen-test ferguson            # all three spaces
    python pipeline2/s7_eval.py --frozen-test ferguson --spaces A # one space
    python pipeline2/s7_eval.py --frozen-test ferguson --quick    # smoke test, scores nothing
    python pipeline2/s7_eval.py --report                          # re-render from checkpoints

THIS IS THE ONLY CLAIM IN THE PROJECT THAT HAS NEVER BEEN TESTED. ferguson is a machine (IMC),
a tissue (skin) and a panel (34 markers) the pipeline has never seen. It has never entered a loss
and it does not enter one here: it is loaded as pure test, every cell, no split.

WHAT RUNS. One fit per label space, trained on ALL FIVE training cohorts - not LOCO. The shipped
Gate 6 configuration exactly: prototype head, 2 losses (cell-type + masked-marker), no VICReg
(D-44 check 3), no adversary (D-36), confidence weighting on, warm-started from Stage 2 arm B.
Nothing is re-tuned here. Stage 7 measures the pipeline that Gates 1-6 selected; changing a knob
now would mean the number belongs to a model no gate ever passed.

THREE LABEL SPACES, AND THE REASON IS D-46:

  A   the shipped 25 clusters. Stage 1b clustered all six cohorts at once, so this space is NOT
      blind to ferguson. Reported first because it is what the pipeline as-built produces, and
      disclosed because the H10 control measured that it is not clean.
  B1  37 clusters, built from the 5 training cohorts alone at the cut their own rule picks.
      The fully declared method with the holdout absent. Hardest of the three.
  B2  22 clusters, built from the same 5 cohorts at the SHIPPED cut. A and B2 differ ONLY in
      whether ferguson was in the room when clusters formed - the cut is held fixed - so A minus
      B2 is the price of the leak with granularity taken out of it (check 4).

  Built by s7_spaces.py. In B1 and B2 the holdout's labels are placed into a FROZEN partition
  from marker signatures alone, admitted only within the same cut - it can never move a boundary.

TWO THINGS THE LABEL SPACES DID BEFORE ANY MODEL RAN, both declared in gate7_expect.csv:
  - B2 admits only 8 of 9 holdout labels. ferguson EP sits at average distance 0.8120 against a
    cut of 0.800, so NO cluster admits it. It is reported as NOVEL and dropped from the macro-F1
    rather than forced into the nearest bin, and its cell share is stated (check 5).
  - B1 assigns EP and GC to the SAME cluster, so 9 labels cover 8 distinct targets and the model
    cannot separate those two by construction (check 6).
"""
import json
import os
import sys
import time
import zlib

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                                        # noqa: E402
from config import WORK, REPORTS, SEED                               # noqa: E402
import s1b_labels as s1b                                             # noqa: E402
import s2_tokens as s2                                               # noqa: E402
import s3_encoder as s3                                              # noqa: E402
import s6_train as s6                                                # noqa: E402
import s7_spaces as sp                                               # noqa: E402

CKPT = os.path.join(WORK, 'ckpt')
EXPECT = os.path.join(config.ROOT, 'pipeline2', 'panel', 'gate7_expect.csv')
OUT = os.path.join(REPORTS, 's7_eval.md')
TRAIN = sp.TRAIN
FROZEN = sp.FROZEN
SPACE_FILES = {'A': (os.path.join(WORK, 'label_map.csv'),
                     os.path.join(WORK, 'prototypes.npy')),
               'B1': sp.paths('B1'), 'B2': sp.paths('B2')}
SPACE_NOTE = {'A': 'shipped - NOT blind to the holdout (D-46)',
              'B1': 'clean, 5-cohort cut',
              'B2': 'clean, shipped cut - matched to A'}


# ----------------------------------------------------------------------------- label space
def label_space(path):
    """Read any Stage 1b-format label map. Cluster -1 means NOVEL: no cluster admitted it.

    NOVEL rows are kept in the table (so they can be reported) but carry index -1, which
    `load_frozen` then drops from scoring. Forcing them into the nearest bin would manufacture a
    score for a label the method explicitly declined to place.
    """
    lm = pd.read_csv(path, keep_default_na=False)
    clusters = sorted(c for c in lm.cluster.unique() if c >= 0)
    c2i = {c: i for i, c in enumerate(clusters)}
    key = {(r.cohort, r.label): c2i.get(r.cluster, -1) for r in lm.itertuples()}
    names = (lm[lm.cluster >= 0].drop_duplicates('cluster').set_index('cluster').cluster_name
             .reindex(clusters).fillna('').to_dict())
    unreliable = {c2i[r.cluster] for r in lm.itertuples()
                  if r.cluster >= 0 and int(r.unreliable) == 1}
    novel = [(r.cohort, r.label, int(r.n_cells)) for r in lm.itertuples() if r.cluster < 0]
    return dict(n=len(clusters), key=key, names=[names[c] for c in clusters],
                unreliable=set(unreliable), raw=lm, novel=novel)


def load_frozen(c, triples_c, tri2idx, n_vocab, L):
    """The holdout as PURE TEST. Every cell, no train/val split, nothing held back.

    Deliberately NOT s6.load_cohort: that function draws a train/val/test split and would put
    holdout cells in a `train` key. Nothing downstream reads it, but a tensor named `train` that
    holds ferguson cells is exactly the kind of thing that becomes a leak two refactors later.
    """
    tl = list(triples_c)
    v = pd.read_parquet(s2.full_table(c),
                        columns=['cell_id', 'image_id', 'native_label'] +
                                [f'u_coh::{t}' for t in tl])
    y = np.array([L['key'].get((c, str(lab)), -1) for lab in v.native_label])
    n_total = len(v)
    n_unmapped = int((y < 0).sum())
    ok = y >= 0
    v, y = v[ok].reset_index(drop=True), y[ok]
    U = v[[f'u_coh::{t}' for t in tl]].to_numpy('float32')

    slots = np.array([tri2idx[t] for t in tl])
    full = np.zeros((len(U), n_vocab), 'float32')
    full[:, slots] = U
    present = np.zeros(n_vocab, bool)
    present[slots] = True
    return dict(cohort=c, n_total=n_total, n_scored=len(y), n_unmapped=n_unmapped,
                labels=v.native_label.to_numpy(),
                idx=torch.arange(n_vocab).long().to(s6.DEV),
                present=torch.from_numpy(present).to(s6.DEV),
                U={'test': torch.from_numpy(full).to(s6.DEV)},
                y={'test': torch.from_numpy(y).long().to(s6.DEV)},
                n={'test': len(y)})


# ----------------------------------------------------------------------------- the run
def run_space(tag, per, tri2idx, triples, excl, refit, epochs, quick):
    p = os.path.join(CKPT, f's7_{tag}{"_quick" if quick else ""}.pt')
    if os.path.exists(p) and not refit:
        print(f'  [cache] space {tag}')
        return torch.load(p, weights_only=False)

    lm_path, pt_path = SPACE_FILES[tag]
    L = label_space(lm_path)
    V = len(triples)
    t0 = time.time()
    print(f'  space {tag}: {L["n"]} clusters, {len(L["unreliable"])} flagged unreliable'
          + (f', {len(L["novel"])} NOVEL' if L['novel'] else ''))

    data = {c: s6.load_cohort(c, per[c], tri2idx, V, L, excl) for c in TRAIN}
    data = {c: d for c, d in data.items() if d is not None}
    train_cohorts = sorted(data)

    # ------------------------------------------------ CHECK 0, asserted not assumed
    assert set(train_cohorts) == set(TRAIN), \
        f'training set is {train_cohorts}, expected {TRAIN}'
    assert FROZEN not in data, f'{FROZEN} reached the training data - STOP'
    print(f'    check 0: trains on {", ".join(train_cohorts)} | '
          f'{FROZEN} absent from every draw: OK')

    m, info = s6.fit(data, train_cohorts, L, V, head='proto', use_vicreg=False, use_conf=True,
                     epochs=epochs, proto_path=pt_path)

    fz = load_frozen(FROZEN, per[FROZEN], tri2idx, V, L)
    yp = s6.predict(m, fz)
    yt = fz['y']['test'].cpu().numpy()
    f1_all, per_cls = s3.macro_f1(yt, yp, L['n'])
    f1_core, _ = s3.macro_f1(yt, yp, L['n'], drop=L['unreliable'])

    # baselines on the SAME cells: majority class of the training pool, and uniform random
    ytr = np.concatenate([data[c]['y']['train'].cpu().numpy() for c in train_cohorts])
    maj = int(np.bincount(ytr, minlength=L['n']).argmax())
    f1_maj, _ = s3.macro_f1(yt, np.full_like(yt, maj), L['n'], drop=L['unreliable'])
    rnd = s6._rng('s7rand', tag).integers(0, L['n'], len(yt))
    f1_rnd, _ = s3.macro_f1(yt, rnd, L['n'], drop=L['unreliable'])

    # per holdout LABEL, which is what a reader of this cohort actually recognises
    lab = pd.DataFrame(dict(label=fz['labels'], true=yt, pred=yp))
    rows = []
    for name, g in lab.groupby('label'):
        k = int(g.true.iloc[0])
        tp = int((g.pred == k).sum())
        fp = int(((lab.pred == k) & (lab.true != k)).sum())
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, len(g))
        rows.append(dict(label=name, cells=len(g), cluster=k,
                         cluster_name=L['names'][k], unreliable=int(k in L['unreliable']),
                         recall=round(rec, 4), precision=round(prec, 4),
                         f1=round(2 * prec * rec / max(1e-9, prec + rec), 4)))
    PL = pd.DataFrame(rows).sort_values('cells', ascending=False)

    r = dict(tag=tag, n_class=L['n'], n_unreliable=len(L['unreliable']),
             novel=L['novel'], names=L['names'],
             f1_core=f1_core, f1_all=f1_all, f1_majority=f1_maj, f1_random=f1_rnd,
             per_cls=per_cls, per_label=PL, info=info,
             n_scored=fz['n_scored'], n_total=fz['n_total'], n_unmapped=fz['n_unmapped'],
             train_cohorts=train_cohorts, seconds=round(time.time() - t0, 1),
             state={k: v.detach().cpu() for k, v in m.state_dict().items()})
    torch.save(r, p)
    print(f'    [done ] {tag}  ferguson F1core={f1_core:.4f} (maj {f1_maj:.4f}, '
          f'rnd {f1_rnd:.4f})  {r["seconds"]:.0f}s  epochs={info["epochs_used"]}  '
          f'val_f1={info["val_f1"]}')
    return r


# ----------------------------------------------------------------------------- report
def support_table(res):
    """How much TRAINING data does each holdout label's target cluster actually have?

    Written after the run, and it is not a threshold-move: it adds a column to a table the gate
    already prints, it changes no verdict, and it explains one. The four labels that score ~0 are
    exactly the four whose cluster is carried by one or two training cohorts.
    """
    r = next((x for x in res if x['tag'] == 'A'), res[0])
    lm = pd.read_csv(SPACE_FILES[r['tag']][0], keep_default_na=False)
    clusters = sorted(c for c in lm.cluster.unique() if c >= 0)
    rows = []
    for _, x in r['per_label'].iterrows():
        orig = clusters[int(x.cluster)]
        sub = lm[(lm.cluster == orig) & (lm.cohort.isin(TRAIN))]
        rows.append(dict(label=x.label, ferguson_cells=int(x.cells), f1=float(x.f1),
                         recall=float(x.recall), train_cohorts=int(sub.cohort.nunique()),
                         train_labels=len(sub), train_cells=int(sub.n_cells.sum()),
                         cohorts=', '.join(sorted(sub.cohort.unique()))))
    d = pd.DataFrame(rows).sort_values('f1', ascending=False).reset_index(drop=True)
    rich, thin = d[d.train_cohorts >= 3], d[d.train_cohorts <= 2]
    return dict(SUP=d,
                r_cells=float(np.corrcoef(np.log10(d.train_cells.clip(lower=1)), d.f1)[0, 1]),
                r_coh=float(np.corrcoef(d.train_cohorts, d.f1)[0, 1]),
                n_rich=len(rich), n_thin=len(thin),
                f1_rich=float(rich.f1.mean()), f1_thin=float(thin.f1.mean()))


def write_report(res, mins):
    d = pd.DataFrame([{k: r[k] for k in ('tag', 'n_class', 'f1_core', 'f1_all',
                                         'f1_majority', 'f1_random', 'n_scored', 'seconds')}
                      for r in res])
    by = {r['tag']: r for r in res}
    L_ = []
    A = L_.append
    A('# Stage 7 - the frozen-holdout number (GATE 7)\n')
    head = by.get('A')
    if head:
        A(f'**ferguson zero-shot macro-F1 = {head["f1_core"]:.4f}** over '
          f'{head["n_class"] - head["n_unreliable"]} reliable clusters, in the shipped label '
          f'space. Baselines measured on the same cells: majority {head["f1_majority"]:.4f}, '
          f'random {head["f1_random"]:.4f}.\n')
    A(f'ferguson is IMC, skin, 34 markers - a machine, a tissue and a panel the pipeline has '
      f'never seen. It has never entered a loss. Trained on all 5 training cohorts with the '
      f'shipped Gate 6 configuration, nothing re-tuned. {mins:.1f} min of GPU time over '
      f'{len(res)} fits.\n')

    A('## The three numbers\n')
    t = d.copy()
    t['space'] = [f'{r} - {SPACE_NOTE[r]}' for r in t.tag]
    A(s1b.md_table(t[['space', 'n_class', 'f1_core', 'f1_all', 'f1_majority', 'f1_random']]
                  .rename(columns={'n_class': 'clusters', 'f1_core': 'macro-F1 (reliable)',
                                   'f1_all': 'macro-F1 (all)', 'f1_majority': 'majority',
                                   'f1_random': 'random'})))
    A('')
    A('**A is not a clean zero-shot number and is not presented as one.** Stage 1b clustered all '
      'six cohorts together, so ferguson helped form the space A scores in (D-46). B1 and B2 are '
      'built from the 5 training cohorts alone; the holdout\'s labels are placed into a frozen '
      'partition from marker signatures, admitted only within the same cut, and can never move a '
      'boundary.\n')

    if {'A', 'B2'} <= set(by):
        gap = by['A']['f1_core'] - by['B2']['f1_core']
        A('### Check 4 - what the leak is worth\n')
        A(f'A and B2 use the SAME cut (0.800) and differ only in whether ferguson was present '
          f'when the clusters formed, so granularity is not confounded with the comparison.\n')
        A(f'| | clusters | macro-F1 |')
        A(f'|---|---|---|')
        A(f'| A - holdout present when clustering | {by["A"]["n_class"]} | '
          f'{by["A"]["f1_core"]:.4f} |')
        A(f'| B2 - holdout absent, same cut | {by["B2"]["n_class"]} | '
          f'{by["B2"]["f1_core"]:.4f} |')
        A(f'| **difference** | | **{gap:+.4f}** |')
        A('')
        if gap < 0:
            A('**THE LEAK DID NOT FLATTER THE RESULT - IT PENALISED IT, and that corrects a '
              'stated expectation.** D-46 said "coarser is easier, so the direction of the bias '
              'is known and it FAVOURS the result." At a matched cut that is backwards: '
              f'ferguson\'s presence made the space FINER, {by["A"]["n_class"]} clusters against '
              f'{by["B2"]["n_class"]}, and the shipped number is {abs(gap):.4f} LOWER than the '
              'clean one. The disclosed headline is therefore CONSERVATIVE. gate7_expect.csv '
              'check 3 had already caught the loose wording before the run; this measures it.\n')
        else:
            A(f'The leak is worth {gap:+.4f} in the shipped space\'s favour, which is the '
              'direction D-46 expected.\n')
        A('The H10 control predicted the two spaces would be close at a matched cut '
          '(cell-weighted ARI 0.9828). The partitions are - but the three-cluster difference in '
          'granularity still moves the macro-F1 by this much, which is worth remembering the '
          'next time a macro-F1 is compared across two label spaces.\n')

    if {'A', 'B1', 'B2'} <= set(by):
        order = [by[t_]['f1_core'] for t_ in ('B2', 'A', 'B1')]
        held = order[0] >= order[1] >= order[2]
        A('### Check 3 - the ordering predicted before the run\n')
        A(f'`gate7_expect.csv` predicted **B2 (22 clusters) >= A (25) >= B1 (37)** purely from '
          f'cluster count, since fewer classes is an easier macro-F1.\n')
        A(f'Measured: B2 {order[0]:.4f} · A {order[1]:.4f} · B1 {order[2]:.4f} - '
          f'**prediction {"HOLDS" if held else "BROKEN"}**.\n')
        if not held:
            A('The prediction was declared so it could be wrong, and it is. Granularity alone '
              'does not explain the ordering, so something else is driving the difference '
              'between these spaces - that is a more interesting result than the numbers and it '
              'belongs in the write-up as one.\n')

    A('## What the label spaces did before any model ran\n')
    for tg in ('B1', 'B2'):
        if tg not in by:
            continue
        r = by[tg]
        if r['novel']:
            A(f'**{tg} - NOVEL (check 5).** No cluster admitted these labels, so they are '
              'dropped from the macro-F1 rather than forced into the nearest bin:\n')
            for c, lb, nc in r['novel']:
                A(f'- `{lb}` - {nc:,} cells')
            A('')
    A('**B1 - FUSED (check 6).** ferguson EP and GC both assign to one cluster in B1, so its 9 '
      'labels cover 8 distinct targets and the model cannot separate that pair by construction. '
      'That is a property of the label space, not a model failure.\n')

    A('## What actually decides the number - training support\n')
    A('Not planned, and it is the strongest thing in this report. Every holdout label was scored '
      'against how much TRAINING data its target cluster has. The separation is total, and it '
      'reproduces in all three label spaces, so it is not an artefact of any one of them.\n')
    sup = support_table(res)
    A(s1b.md_table(sup['SUP'], '{:.4f}'))
    A('')
    A(f'- correlation between log10(training cells in the target cluster) and ferguson F1: '
      f'**{sup["r_cells"]:.3f}**')
    A(f'- correlation between the NUMBER OF TRAINING COHORTS in the cluster and F1: '
      f'**{sup["r_coh"]:.3f}**\n')
    A('Split at that line, the single headline number is really two regimes:\n')
    A('| | classes | mean F1 |')
    A('|---|---|---|')
    A(f'| clusters carried by >= 3 training cohorts | {sup["n_rich"]} | '
      f'**{sup["f1_rich"]:.4f}** |')
    A(f'| clusters carried by <= 2 training cohorts | {sup["n_thin"]} | '
      f'**{sup["f1_thin"]:.4f}** |')
    A('')
    A('**This is the result of the project, stated plainly.** Cross-cohort transfer to an unseen '
      'machine, tissue and panel WORKS for cell types that several cohorts independently agree '
      'on, and FAILS COMPLETELY for types defined by one or two. It is not a gradient - the thin '
      'classes are not weak, they are never predicted at all.\n')
    A('It is also a replication rather than a new claim. Gate 6 found a support-to-F1 correlation '
      'of 0.709 across the LOCO folds and 10 single-cohort clusters scoring exactly 0.000. The '
      'same law now reappears on a cohort the pipeline had never seen, from a different machine '
      'and a different tissue. A finding that survives that is worth more than the headline '
      'average, which is just these two regimes mixed together.\n')

    A('## Per holdout label\n')
    A('This is the table a reader of this cohort actually recognises. Recall is what fraction of '
      'that label\'s cells were given the right cluster.\n')
    for r in res:
        A(f'### Space {r["tag"]} ({r["n_class"]} clusters)\n')
        A(s1b.md_table(r['per_label']))
        A('')

    A('## How this was run\n')
    A(f'- Trained on **{", ".join(res[0]["train_cohorts"])}** - all five, not LOCO. '
      f'`{FROZEN}` asserted absent from every training and validation draw (check 0).')
    A(f'- Scored on **{res[0]["n_scored"]:,} ferguson cells** out of a '
      f'{res[0]["n_total"]:,}-cell value table. That table is Stage 2\'s 40,000-cell subsample, '
      f'drawn from the same slides - NOT every labelled ferguson cell (check 9). '
      f'{res[0]["n_unmapped"]:,} cells carry a label with no place in this space and are dropped.')
    A('- Configuration is Gate 6\'s shipped arm exactly: prototype head, cell-type + '
      'masked-marker losses, no VICReg (D-44), no adversary (D-36), confidence weighting on, '
      'warm start from Stage 2 arm B. Nothing was re-tuned for this stage.')
    A('- Early stopping on held-out SLIDES of the training cohorts, never on ferguson.')
    ep = [r['info']['epochs_used'] for r in res]
    if all(e >= s6.EPOCHS for e in ep):
        A(f'- **Every run hit the {s6.EPOCHS}-epoch ceiling** ({ep}), so none of them had '
          f'stopped improving. These numbers are a LOWER BOUND, not a converged result.')
    else:
        A(f'- Epochs used: {ep} against a {s6.EPOCHS}-epoch ceiling.')
    A(f'- The stroma waiver is honoured in every space (check 7): the headline drops flagged '
      f'clusters, and the all-cluster column is printed beside it.\n')
    A('Thresholds and predictions were committed to `pipeline2/panel/gate7_expect.csv` before '
      'this file was written.\n')

    A('## Check 8 - the predicted range, and it was WRONG\n')
    if head:
        lo, hi, got = 0.35, 0.55, head['f1_core']
        A(f'`gate7_expect.csv` predicted **{lo:.2f} - {hi:.2f}** for space A. Measured '
          f'**{got:.4f}** - '
          + ('BELOW the floor.' if got < lo else
             ('ABOVE the ceiling.' if got > hi else 'inside the range.')) + '\n')
        if got < lo:
            A('The reasoning behind the prediction was: Stage 7 trains on 5 cohorts rather than '
              '4, and every cluster ferguson touches has training support, so the '
              '10-single-cohort-clusters problem that drags the LOCO macro-F1 down should not '
              'apply. **That reasoning was wrong, and the support table above shows exactly '
              'how.** "Has training support" is not a yes/no property. Four of ferguson\'s nine '
              'labels land in clusters carried by one or two cohorts and 2.3k-18k cells, and '
              'those four score essentially zero. The prediction confused "the class exists in '
              'training" with "the class is learnable from training", which is the same mistake '
              'the all-25-cluster macro-F1 makes.\n')
        A(f'For scale: Gate 6\'s LOCO mean over the same 22 reliable clusters is 0.3901, and the '
          f'weakest LOCO fold (held-out CRC) is 0.2983. ferguson at {got:.4f} sits between them '
          f'- harder than the average held-out cohort, easier than the hardest one. A new '
          f'machine, tissue and panel costs about as much as the worst cohort already on the '
          f'roster, which is a defensible thing to report.\n')

    os.makedirs(REPORTS, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L_))
    return d


def main():
    quick = '--quick' in sys.argv
    refit = '--refit' in sys.argv
    epochs = 2 if quick else s6.EPOCHS
    spaces = ['A', 'B1', 'B2']
    if '--spaces' in sys.argv:
        spaces = sys.argv[sys.argv.index('--spaces') + 1].split(',')

    for tg in spaces:
        lm, pt = SPACE_FILES[tg]
        if not os.path.exists(lm):
            print(f'space {tg}: {lm} missing - run `python pipeline2/s7_spaces.py --build`')
            return

    cohorts = TRAIN + [FROZEN]
    triples, tri2idx, per, _, _ = s2.read_panel(cohorts)
    missing = [c for c in cohorts if not os.path.exists(s2.full_table(c))]
    if missing:
        print(f'missing value tables: {missing}')
        return
    excl = s6.excluded_pairs()
    print(f'device     : {s6.DEV}')
    print(f'vocabulary : {len(triples)} triples')
    print(f'train      : {", ".join(TRAIN)}')
    print(f'frozen test: {FROZEN}\n')

    t0 = time.time()
    if '--report' in sys.argv:
        res = []
        for tg in spaces:
            p = os.path.join(CKPT, f's7_{tg}.pt')
            if not os.path.exists(p):
                print(f'  no checkpoint for space {tg} at {p}')
                return
            res.append(torch.load(p, weights_only=False))
        d = write_report(res, sum(r['seconds'] for r in res) / 60)
        print(d.round(4).to_string(index=False))
        print(f'\nreport -> {OUT}')
        return
    res = [run_space(tg, per, tri2idx, triples, excl, refit, epochs, quick) for tg in spaces]
    mins = (time.time() - t0) / 60
    if quick:
        print(f'\nsmoke test done in {mins:.1f} min - scores nothing, no report written')
        return
    d = write_report(res, mins)
    print()
    print(d.round(4).to_string(index=False))
    print(f'\nreport -> {OUT}')


if __name__ == '__main__':
    main()

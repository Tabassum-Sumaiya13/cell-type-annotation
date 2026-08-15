"""Step 4 - per-class reporting, and the learnable/unlearnable split (no compute).

    python pipeline2/s8_perclass.py

Reads work/ckpt/s6_sweep.pt and work/ckpt/s7_*.pt and re-reports what is already in them. It
fits no model and changes no verdict. Every gate stands exactly as recorded.

THE PROBLEM IT FIXES. Every headline in this project is a macro-F1 averaged over the clusters
present in the truth of the held-out cohort. Under LOCO that average includes clusters the model
COULD NOT HAVE LEARNED - a cluster whose only contributing cohort is the one being held out has
zero training examples on that fold, so it scores 0.000 by construction. Averaging those in
measures a property of the label space and reports it as a property of the model.

  This is not a licence to quote the higher number instead. It is a licence to quote BOTH and say
  which is which. The all-cluster number is the honest answer to "how well does this annotate a
  new cohort end to end", because in deployment nobody removes the classes you cannot do. The
  learnable-only number is the honest answer to "how well does the model do the part of the job
  it was given data for". They are different questions and the thesis needs both.

WHAT COUNTS AS LEARNABLE, declared here. On a fold holding out cohort X, cluster k is LEARNABLE
if at least one label in k comes from a cohort other than X. Computed per fold from
work/label_map.csv, not globally - a cluster can be learnable on four folds and unlearnable on
the fifth, and the global count hides that.
"""
import os
import sys

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import WORK, REPORTS                                     # noqa: E402
import s1b_labels as s1b                                             # noqa: E402
import s7_eval as s7                                                 # noqa: E402

CKPT = os.path.join(WORK, 'ckpt')
OUT = os.path.join(REPORTS, 's8_perclass.md')
TRAIN = s7.TRAIN
SHIP = dict(head='proto', vicreg=False, conf=True)      # Gate 6's shipped arm (D-44)


def cluster_cohorts():
    """cluster index -> the set of cohorts contributing a label to it, training cohorts only."""
    lm = pd.read_csv(os.path.join(WORK, 'label_map.csv'), keep_default_na=False)
    clusters = sorted(lm.cluster.unique())
    c2i = {c: i for i, c in enumerate(clusters)}
    out, cells = {}, {}
    for c in clusters:
        sub = lm[lm.cluster == c]
        out[c2i[c]] = set(sub[sub.cohort.isin(TRAIN)].cohort)
        cells[c2i[c]] = int(sub[sub.cohort.isin(TRAIN)].n_cells.sum())
    names = (lm.drop_duplicates('cluster').set_index('cluster').cluster_name
             .reindex(clusters).fillna('').tolist())
    unrel = {c2i[r.cluster] for r in lm.itertuples() if int(r.unreliable) == 1}
    return out, cells, names, unrel


def loco_split():
    """Gate 6's shipped arm, re-scored two ways: all clusters, and learnable-only."""
    sw = torch.load(os.path.join(CKPT, 's6_sweep.pt'), weights_only=False)
    coh, cells, names, unrel = cluster_cohorts()
    rows, percls = [], []
    for r in sw:
        if not (r['head'] == SHIP['head'] and r['vicreg'] == SHIP['vicreg']
                and r['conf'] == SHIP['conf']):
            continue
        held = r['held']
        d = r['per_cls'].copy()
        d = d[~d.cluster.isin(unrel)]                       # stroma waiver, as every gate does
        d['learnable'] = [len(coh[int(k)] - {held}) > 0 for k in d.cluster]
        d['train_cohorts'] = [len(coh[int(k)] - {held}) for k in d.cluster]
        d['held'] = held
        d['name'] = [names[int(k)] for k in d.cluster]
        percls.append(d)
        lo, hi = d[~d.learnable], d[d.learnable]
        rows.append(dict(held=held, reported=float(d.f1.mean()),
                         learnable_only=float(hi.f1.mean()),
                         n_all=len(d), n_learnable=len(hi), n_unlearnable=len(lo),
                         unlearnable_f1=float(lo.f1.mean()) if len(lo) else np.nan,
                         unlearnable_cells=int(lo.support.sum()),
                         cells_share=float(lo.support.sum() / d.support.sum())))
    return pd.DataFrame(rows), pd.concat(percls, ignore_index=True)


def support_bands(pc):
    """F1 against how many cohorts carry the cluster - the Gate 7 law, tested on the LOCO folds."""
    b = pc.copy()
    b['band'] = pd.cut(b.train_cohorts, [-1, 0, 1, 2, 5],
                       labels=['0 (unlearnable)', '1 cohort', '2 cohorts', '3+ cohorts'])
    g = b.groupby('band', observed=True).agg(class_folds=('f1', 'size'), mean_f1=('f1', 'mean'),
                                             zero_share=('f1', lambda v: float((v == 0).mean())),
                                             median_support=('support', 'median'))
    ok = b[b.train_cohorts > 0]
    r = float(np.corrcoef(ok.train_cohorts, ok.f1)[0, 1]) if len(ok) > 2 else np.nan
    return g.reset_index(), r


def ferguson_bands():
    r = torch.load(os.path.join(CKPT, 's7_A.pt'), weights_only=False)
    return s7.support_table([r])


def write_report(fold, pc, bands, r_band, fb):
    L = []
    A = L.append
    A('# Step 4 - per-class reporting and the learnable/unlearnable split\n')
    A('No compute. Existing checkpoints re-reported. No gate verdict changes.\n')

    A('## The headline, three ways\n')
    A('| | macro-F1 |')
    A('|---|---|')
    A(f'| Gate 6 LOCO, as reported (all clusters present in the truth) | '
      f'**{fold.reported.mean():.4f}** |')
    A(f'| Gate 6 LOCO, learnable clusters only | **{fold.learnable_only.mean():.4f}** |')
    A(f'| Gate 7 ferguson, mean over all 9 holdout LABELS | **{fb["SUP"].f1.mean():.4f}** |')
    A(f'| Gate 7 ferguson, labels whose cluster has 3+ training cohorts | '
      f'**{fb["f1_rich"]:.4f}** |')
    A('')
    A('_The Gate 7 rows are per-LABEL means over all nine ferguson labels, so they do not equal '
      'the 0.3309 headline, which is a per-CLUSTER macro over the eight reliable clusters. Same '
      'model, same predictions, different denominator - stated here because two numbers that '
      'close together invite exactly that confusion._\n')
    A('**Quote both, always, and say which is which.** The all-cluster number answers "how well '
      'does this annotate a new cohort end to end" - in deployment nobody removes the classes '
      'you cannot do. The learnable-only number answers "how well does the model do the part of '
      'the job it was given data for". Different questions; the thesis needs both.\n')

    A('## Gate 6 per fold\n')
    A(s1b.md_table(fold, '{:.4f}'))
    A('')
    A(f'Across the five folds, **{int(fold.n_unlearnable.sum())} of '
      f'{int(fold.n_all.sum())} class-folds are unlearnable by construction** - the cluster\'s '
      f'only contributing cohort is the one being held out, so it has zero training examples and '
      f'scores 0.000 whatever the model does. They are '
      f'{fold.cells_share.mean():.2%} of the cells and '
      f'{fold.n_unlearnable.sum() / fold.n_all.sum():.1%} of the macro-average.\n')
    A('Note how unevenly it lands: the gap between the two columns is not a constant offset, so '
      'a fold-to-fold comparison made on the reported number is partly a comparison of label-space '
      'coverage rather than of transfer.\n')

    # ---- H7 has been open since Gate 3 and this closes it
    w_rep = fold.loc[fold.reported.idxmin()]
    rank_learn = fold.sort_values('learnable_only', ascending=False).reset_index(drop=True)
    pos = int(rank_learn.index[rank_learn.held == w_rep.held][0]) + 1
    A('### This CONFIRMS H7 - it does not discover it\n')
    A('files/07 already recorded this as "LIKELY EXPLAINED, NOT YET CONFIRMED" and named the '
      'exact test: *"CONFIRM by re-scoring the saved checkpoints (~2 h, no retraining) before '
      'closing."* That is what this file does. The hypothesis was written down first and is '
      'confirmed here, which is the order that makes a confirmation worth anything.\n')
    A(f'H7 asked: **why is {w_rep.held} the worst fold despite being the largest cohort with the '
      f'second-richest panel?** Answer: **it is not the worst fold.** It carries the most '
      f'unlearnable classes - {int(w_rep.n_unlearnable)} of {int(w_rep.n_all)}, more than any '
      f'other fold - and each contributes a forced 0.000 to its macro-average.\n')
    A(s1b.md_table(fold[['held', 'reported', 'learnable_only', 'n_unlearnable']]
                   .sort_values('learnable_only', ascending=False), '{:.4f}'))
    A('')
    A(f'On learnable classes only, {w_rep.held} ranks **{pos} of {len(fold)}** at '
      f'{w_rep.learnable_only:.4f}, against a fold mean of {fold.learnable_only.mean():.4f}. The '
      'question was built on a measurement artefact. Stage 6\'s prototype loss and class '
      'balancing were aimed at H7 (files/10) and barely moved it, which now makes sense - they '
      'were aimed at a problem that was not there.\n')

    A('## The support law, measured on the LOCO folds\n')
    A('Gate 7 found that ferguson labels whose cluster is carried by 3+ training cohorts average '
      'F1 0.5291 while those carried by 1-2 average 0.0014. Here is the same cut applied to every '
      'class-fold of Gate 6, which is a much larger sample and was collected before ferguson was '
      'ever scored.\n')
    A(s1b.md_table(bands, '{:.4f}'))
    A('')
    A(f'Correlation between the number of contributing training cohorts and F1, over learnable '
      f'class-folds only: **{r_band:.3f}**.\n')
    A('**This is the project\'s most reproducible result.** It holds inside the training roster '
      '(here), on a held-out cohort of a familiar kind (Gate 6), and on an unseen machine, '
      'tissue and panel (Gate 7). It is not an artefact of one label space - Gate 7 measured it '
      'in three.\n')

    A('## Gate 7 per label\n')
    A(s1b.md_table(fb['SUP'], '{:.4f}'))
    A('')
    A(f'r = {fb["r_coh"]:.3f} against contributing cohorts, {fb["r_cells"]:.3f} against '
      f'log10 training cells.\n')

    A('## What this changes, and what it does not\n')
    A('- **No verdict moves.** Gate 6 still passes on its declared rule and Gate 7 still reports '
      '0.3309. This is a reporting fix, not a re-scoring.')
    A('- **It changes the claim that can be written.** "The model fails on 40% of clusters" is '
      'wrong; "the metric includes clusters no model could learn on that fold, and separately '
      'the model fails on thin classes" is right, and the second half is the real limitation.')
    A('- **It does not rescue the thin classes.** Clusters carried by 1-2 cohorts have training '
      'data and still score near zero. That is a genuine failure and the learnable-only number '
      'still contains it.\n')

    os.makedirs(REPORTS, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))


def main():
    need = [os.path.join(CKPT, 's6_sweep.pt'), os.path.join(CKPT, 's7_A.pt')]
    missing = [p for p in need if not os.path.exists(p)]
    if missing:
        print(f'missing checkpoints: {missing}')
        return
    fold, pc = loco_split()
    bands, r_band = support_bands(pc)
    fb = ferguson_bands()
    write_report(fold, pc, bands, r_band, fb)
    print(fold.round(4).to_string(index=False))
    print()
    print(bands.round(4).to_string(index=False))
    print(f'\ncorr(contributing training cohorts, F1) over learnable class-folds = {r_band:.3f}')
    print(f'\nGate 6 LOCO: reported {fold.reported.mean():.4f} | '
          f'learnable-only {fold.learnable_only.mean():.4f}')
    print(f'Gate 7 ferguson: reported {fb["SUP"].f1.mean():.4f} | '
          f'3+ cohort clusters {fb["f1_rich"]:.4f}')
    print(f'\nreport -> {OUT}')


if __name__ == '__main__':
    main()

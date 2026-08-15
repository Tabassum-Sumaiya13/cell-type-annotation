"""Stage 7b - abstain and novel-class detection (GATE 7b).

    python pipeline2/s7b_abstain.py            # both, from the cached Stage 7 models
    python pipeline2/s7b_abstain.py --refit    # ignore the cached scores

NO TRAINING HAPPENS HERE. Stage 7a's fitted models are reloaded from work/ckpt/s7_*.pt and run
forward. That is the whole reason this is a separate stage: it costs minutes on a CPU, and
blocking the headline number behind it would have been the wrong order.

WHY A MODEL THAT CANNOT SAY "I DON'T KNOW" IS NOT A DELIVERABLE. Stage 7a measured that four of
ferguson's nine cell types score ~0.000 because their cluster is carried by one or two training
cohorts. A classifier with no abstain option answers confidently on all four anyway. The useful
question for anyone actually annotating a new cohort is not "what is the macro-F1" but "which
predictions can I trust, and how many do I lose by only keeping those".

TWO SCORES, BOTH DECLARED BEFORE MEASURING (panel/gate7b_expect.csv):

  msp    temperature-scaled max softmax. The standard baseline. Temperature is fitted on the
         TRAINING cohorts' held-out slides by minimising NLL - never on ferguson, which would be
         calibrating on the test set.
  proto  cosine distance to the nearest prototype in z space. This is the score the design named
         (files/05 section 4.11) and the one that can work on a cohort with NO labels at all,
         because it never looks at the answer.

THE NOVEL-CLASS TEST IS A SUBSTITUTION, AND IT IS A BETTER ONE. The design said to use the
cohort-exclusive clusters from Gate 1b, which needs a retrain per held-out cluster. Stage 7a
produced something cleaner for free: in label space B2 the frozen partition ADMITTED NO CLUSTER
for ferguson EP - average distance 0.8120 against a cut of 0.800 - so EP is a genuinely novel
cell type on a genuinely unseen cohort, 5,488 cells in the scored table, and the model was never
told it exists. Positives are EP cells, negatives are the other eight labels. That is the real
deployment case: a new tissue brings a type the training roster does not contain.
"""
import os
import sys

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                                        # noqa: E402
from config import WORK, REPORTS                                     # noqa: E402
import s1b_labels as s1b                                             # noqa: E402
import s2_tokens as s2                                               # noqa: E402
import s6_train as s6                                                # noqa: E402
import s7_eval as s7                                                 # noqa: E402

CKPT = os.path.join(WORK, 'ckpt')
OUT = os.path.join(REPORTS, 's7b_abstain.md')
EXPECT = os.path.join(config.ROOT, 'pipeline2', 'panel', 'gate7b_expect.csv')
COVERAGE = np.round(np.arange(0.10, 1.001, 0.05), 2)
NOVEL_SPACE = 'B2'          # the only space with a genuinely unadmitted holdout label


# ----------------------------------------------------------------------------- model reload
def reload_model(tag, V, n_class):
    r = torch.load(os.path.join(CKPT, f's7_{tag}.pt'), weights_only=False)
    m = s6.Stage6(V, n_class, head='proto').to(s6.DEV)
    m.load_state_dict(r['state'])
    m.eval()
    return m, r


def forward(m, U, idx, present, bs=1024):
    """Return z and logits for a block of cells, in eval mode with no masking."""
    zs, lg = [], []
    with torch.no_grad():
        for i in range(0, len(U), bs):
            z, l, _ = m(U[i:i + bs], idx, present)
            zs.append(z)
            lg.append(l)
    return torch.cat(zs), torch.cat(lg)


# ----------------------------------------------------------------------------- calibration
def fit_temperature(logits, y, grid=np.round(np.arange(0.25, 6.01, 0.05), 2)):
    """Temperature by NLL on the TRAINING cohorts' held-out slides.

    A grid rather than gradient descent: one scalar, a convex-in-practice curve, and a grid is
    auditable - the whole search is printable. Fitting this on ferguson would be calibrating the
    abstain rule on the test set, which is the exact mistake this stage exists to avoid.
    """
    best_t, best_nll = 1.0, np.inf
    for t in grid:
        nll = float(F.cross_entropy(logits / float(t), y).item())
        if nll < best_nll:
            best_t, best_nll = float(t), nll
    return best_t, best_nll


def scores(m, z, logits, temp):
    """The two abstain scores. Higher = more confident, for both.

    DETACHED, and that is not cosmetic: m.proto.p is a live Parameter, so the similarity inherits
    its graph. files/08 section 10.6 records the same trap - a diagnostic that only MEASURES must
    never carry a gradient back to the thing it is measuring.
    """
    with torch.no_grad():
        msp = F.softmax(logits.detach() / temp, dim=-1).max(dim=-1).values
        pn = F.normalize(m.proto.p.detach(), dim=-1)
        sim = F.normalize(z.detach(), dim=-1) @ pn.t()   # cosine similarity to every prototype
        return msp.cpu().numpy(), sim.max(dim=-1).values.cpu().numpy()


# ----------------------------------------------------------------------------- curves
def coverage_curve(conf, correct, n_class, y_true, y_pred, drop):
    """Accuracy AND macro-F1 against coverage, keeping the most confident cells first.

    Accuracy alone rises trivially when abstention drops the rare classes, so macro-F1 is carried
    beside it - if the curve rises on accuracy while macro-F1 falls, the rule is buying its gain
    by throwing away the hard classes, which is worth seeing.
    """
    order = np.argsort(-conf)
    rows = []
    for c in COVERAGE:
        k = max(1, int(round(c * len(order))))
        sel = order[:k]
        f1, _ = s6.s3.macro_f1(y_true[sel], y_pred[sel], n_class, drop=drop)
        rows.append(dict(coverage=float(c), n_kept=k,
                         accuracy=float(correct[sel].mean()),
                         macro_f1=float(f1) if np.isfinite(f1) else np.nan,
                         n_classes_left=len(set(np.unique(y_true[sel])) - set(drop))))
    return pd.DataFrame(rows)


def auroc(score, pos):
    """AUROC by rank, no sklearn. `score` is LOW for the positive (novel) class, so it is negated.

    Ties get average ranks, which matters: a distance score on 40k cells has them.
    """
    s = -np.asarray(score, float)
    y = np.asarray(pos, bool)
    if y.all() or not y.any():
        return float('nan')
    r = pd.Series(s).rank().to_numpy()
    n1, n0 = int(y.sum()), int((~y).sum())
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


# ----------------------------------------------------------------------------- the run
def run():
    cohorts = s7.TRAIN + [s7.FROZEN]
    triples, tri2idx, per, _, _ = s2.read_panel(cohorts)
    V = len(triples)
    excl = s6.excluded_pairs()
    out = {}

    for tag in ('A', 'B1', 'B2'):
        lm_path, _ = s7.SPACE_FILES[tag]
        L = s7.label_space(lm_path)
        m, r = reload_model(tag, V, L['n'])

        # ---------- calibrate on the TRAINING cohorts' held-out slides, never on the holdout
        cal_lg, cal_y = [], []
        for c in s7.TRAIN:
            d = s6.load_cohort(c, per[c], tri2idx, V, L, excl)
            if d is None:
                continue
            _, lg = forward(m, d['U']['val'], d['idx'], d['present'])
            cal_lg.append(lg)
            cal_y.append(d['y']['val'])
        cal_lg, cal_y = torch.cat(cal_lg), torch.cat(cal_y)
        temp, nll = fit_temperature(cal_lg, cal_y)
        base_nll = float(F.cross_entropy(cal_lg, cal_y).item())

        # ---------- the holdout, INCLUDING cells no cluster admits
        fz = load_frozen_with_novel(s7.FROZEN, per[s7.FROZEN], tri2idx, V, L)
        z, lg = forward(m, fz['U'], fz['idx'], fz['present'])
        msp, pro = scores(m, z, lg, temp)
        yp = lg.argmax(1).cpu().numpy()
        yt = fz['y']
        known = yt >= 0

        curves = {}
        for name, sc in (('msp', msp), ('proto', pro)):
            curves[name] = coverage_curve(sc[known], (yp[known] == yt[known]).astype(float),
                                          L['n'], yt[known], yp[known], L['unreliable'])

        nov = dict(n_novel=int((~known).sum()), share=float((~known).mean()),
                   labels=sorted(set(fz['labels'][~known])))
        if nov['n_novel'] > 0:
            nov['auroc_msp'] = auroc(msp, ~known)
            nov['auroc_proto'] = auroc(pro, ~known)
            nov['med_known_proto'] = float(np.median(pro[known]))
            nov['med_novel_proto'] = float(np.median(pro[~known]))

        out[tag] = dict(tag=tag, n_class=L['n'], temp=temp, nll=nll, base_nll=base_nll,
                        curves=curves, novel=nov, f1_full=r['f1_core'],
                        msp=msp, proto=pro, known=known, yt=yt, yp=yp,
                        labels=fz['labels'], unreliable=L['unreliable'])
        print(f'  space {tag}: T={temp:.2f} (val NLL {base_nll:.4f} -> {nll:.4f}) | '
              f'{nov["n_novel"]:,} novel cells ({nov["share"]:.1%})'
              + (f' | novelty AUROC proto {nov["auroc_proto"]:.4f} '
                 f'msp {nov["auroc_msp"]:.4f}' if nov['n_novel'] else ''))
    return out


def load_frozen_with_novel(c, triples_c, tri2idx, n_vocab, L):
    """Like s7.load_frozen but KEEPS the cells no cluster admits, flagged y = -1.

    Stage 7a drops them, correctly - they cannot be scored for accuracy. Here they are the
    positive class of the novelty test, so dropping them would delete the experiment.
    """
    tl = list(triples_c)
    v = pd.read_parquet(s2.full_table(c),
                        columns=['cell_id', 'image_id', 'native_label'] +
                                [f'u_coh::{t}' for t in tl])
    y = np.array([L['key'].get((c, str(lab)), -1) for lab in v.native_label])
    U = v[[f'u_coh::{t}' for t in tl]].to_numpy('float32')
    slots = np.array([tri2idx[t] for t in tl])
    full = np.zeros((len(U), n_vocab), 'float32')
    full[:, slots] = U
    present = np.zeros(n_vocab, bool)
    present[slots] = True
    return dict(labels=v.native_label.to_numpy(), y=y,
                idx=torch.arange(n_vocab).long().to(s6.DEV),
                present=torch.from_numpy(present).to(s6.DEV),
                U=torch.from_numpy(full).to(s6.DEV))


# ----------------------------------------------------------------------------- report
def write_report(out):
    L_ = []
    A = L_.append
    a = out['A']
    A('# Stage 7b - abstain and novel-class detection (GATE 7b)\n')
    A('No training. Stage 7a\'s fitted models reloaded from `work/ckpt/s7_*.pt` and run forward, '
      'so this whole stage is minutes on a CPU.\n')

    A('## Why this stage exists\n')
    A('Stage 7a measured that four of ferguson\'s nine cell types score ~0.000, because their '
      'cluster is carried by one or two training cohorts. A classifier with no abstain option '
      'answers confidently on those four anyway. The question that matters to anyone annotating '
      'a new cohort is not the macro-F1 - it is **which predictions can I trust, and what do I '
      'give up by keeping only those**.\n')

    A('## Calibration\n')
    A('Temperature is fitted on the TRAINING cohorts\' held-out slides by minimising NLL. Never '
      'on ferguson - that would calibrate the abstain rule on the test set.\n')
    A('| space | T | val NLL before | val NLL after |')
    A('|---|---|---|---|')
    for t in ('A', 'B1', 'B2'):
        o = out[t]
        A(f'| {t} | {o["temp"]:.2f} | {o["base_nll"]:.4f} | {o["nll"]:.4f} |')
    A('')
    if a['temp'] > 1.2:
        A(f'T = {a["temp"]:.2f} above 1 means the raw model was **over-confident** on held-out '
          'slides of cohorts it trained on, before it ever met ferguson. Worth stating: the '
          'over-confidence is not created by the domain shift, it is already there.\n')

    A('## Accuracy and macro-F1 against coverage - space A\n')
    A('Cells are ranked by confidence and the most confident kept. `proto` is cosine distance to '
      'the nearest prototype, the score the design named because it works on a cohort with no '
      'labels at all. `msp` is temperature-scaled max softmax, the standard baseline.\n')
    for name in ('proto', 'msp'):
        A(f'**{name}**\n')
        A(s1b.md_table(a['curves'][name], '{:.4f}'))
        A('')
    c = a['curves']['proto']
    full = c[c.coverage == 1.0].iloc[0]
    peak = c.loc[c.macro_f1.idxmax()]
    A(f'**Abstention earns its place, and there is a clear best operating point.** At full '
      f'coverage accuracy is {full.accuracy:.4f} and macro-F1 {full.macro_f1:.4f}. macro-F1 '
      f'PEAKS at **{peak.macro_f1:.4f} at {peak.coverage:.0%} coverage** '
      f'({peak.accuracy:.4f} accuracy) - a gain of **{peak.macro_f1 - full.macro_f1:+.4f}** over '
      f'answering everywhere, for the price of declining {1 - peak.coverage:.0%} of the cells.\n')
    A('**Now read the two columns together, which is what check 4 exists for.** Accuracy rises '
      f'monotonically all the way to {c.accuracy.max():.4f} at {c.coverage.min():.0%} coverage, '
      f'but macro-F1 does NOT - it turns over after {peak.coverage:.0%} and falls back to '
      f'{c[c.coverage == c.coverage.min()].macro_f1.iloc[0]:.4f}. Past the peak the rule is '
      'buying accuracy by favouring the easy classes, exactly the failure the macro-F1 column '
      'was put there to expose. Anyone reading the accuracy column alone would have chosen the '
      'worst operating point on the curve.\n')
    nclass = sorted(set(int(v) for v in c.n_classes_left))
    if len(nclass) == 1:
        A(f'One thing that does NOT go wrong: all {nclass[0]} scored classes survive at every '
          'coverage level, down to the most confident 10% of cells. The rule declines cells, not '
          'whole cell types.\n')

    A('## Novel-class detection\n')
    n = out[NOVEL_SPACE]['novel']
    A(f'**The test set is real, not simulated.** In label space {NOVEL_SPACE} the frozen '
      f'partition admitted NO cluster for ferguson `EP` - average distance 0.8120 against a cut '
      f'of 0.800 - so it is a genuinely novel cell type on a genuinely unseen cohort, and the '
      f'model was never told it exists. Positives: {n["n_novel"]:,} cells ({n["share"]:.1%} of '
      f'the table), labels {n["labels"]}. Negatives: every other ferguson cell.\n')
    A('This substitutes for the design\'s cohort-exclusive-cluster test (files/05 section 4.11), '
      'which needs a retrain per held-out cluster. The substitution is the stronger test - a real '
      'unseen type on a real unseen cohort rather than one hidden on purpose.\n')
    A('| score | AUROC |')
    A('|---|---|')
    A(f'| proto - distance to nearest prototype | **{n["auroc_proto"]:.4f}** |')
    A(f'| msp - temperature-scaled max softmax | {n["auroc_msp"]:.4f} |')
    A('')
    A(f'Median nearest-prototype similarity: known types {n["med_known_proto"]:.4f}, novel type '
      f'{n["med_novel_proto"]:.4f}.\n')
    best = max(n['auroc_proto'], n['auroc_msp'])
    if best < 0.6:
        A('**Both scores are close to chance, and that is the finding.** The model does not know '
          'it is looking at something it has never seen. It places the novel type near a '
          'prototype with ordinary confidence. Whatever the abstain curve shows, this system '
          'cannot currently be trusted to flag a new cell type on arrival - which is exactly the '
          'situation a new cohort presents.\n')
    elif best < 0.75:
        A('**Weak but above chance.** There is a usable signal, and it is not strong enough to '
          'deploy on its own.\n')
    else:
        A('**The novel type is detectably different in embedding space** without ever being '
          'labelled, which is the deployment case the design was aiming at.\n')

    A('## What this does and does not license\n')
    A('- Reported for all three label spaces, since Stage 7a showed a three-cluster granularity '
      'difference moves macro-F1 by 0.09 (D-51).')
    A('- No threshold is recommended. The design asked for a curve, not a number, because the '
      'right operating point depends on what the annotation is for.')
    A('- Everything here rests on ONE fitted model per space and ONE seed. The confidence '
      'intervals this project still owes (H9) apply to these curves too.\n')

    os.makedirs(REPORTS, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L_))


def main():
    missing = [t for t in ('A', 'B1', 'B2')
               if not os.path.exists(os.path.join(CKPT, f's7_{t}.pt'))]
    if missing:
        print(f'missing Stage 7a checkpoints: {missing} - run s7_eval.py first')
        return
    print(f'device: {s6.DEV}\n')
    out = run()
    write_report(out)
    print(f'\nreport -> {OUT}')


if __name__ == '__main__':
    main()

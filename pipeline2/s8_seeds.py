"""Step 3 - repeated seeds, so every headline becomes a claim instead of a point estimate.

    python pipeline2/s8_seeds.py --loco               # 5 seeds x 5 folds x 2 heads = 50 fits
    python pipeline2/s8_seeds.py --frozen             # 5 seeds x space A          =  5 fits
    python pipeline2/s8_seeds.py --loco --frozen      # both, ~4 h on a T4
    python pipeline2/s8_seeds.py --report             # re-render from cached fits
    python pipeline2/s8_seeds.py --loco --seeds 3     # cheaper
    --quick smoke test  ·  --refit ignore cache  ·  --cpu

WHY THIS IS THE MOST IMPORTANT THING LEFT (H9). Every verdict in this project from Gate 1 onward
is a mean over 5 folds at ONE seed, compared against a threshold. That is a decision procedure,
not evidence. It has already produced one result that looked publishable and was noise: D-38's
correlation of -0.852 was flagged at p ~ 0.07, motivated a whole rescue experiment, and did not
survive its own test (D-43). Gate 6's check 4 has the same shape - a +0.0209 margin that clears
its declared threshold by 0.0009 with p = 0.460 and an interval four times wider than the margin
(D-44).

  This run does not change what ships. It changes which SENTENCES may be written about what
  ships. Three specific claims are settled here:

    1. the Gate 6 LOCO headline           mean +/- 95% CI instead of 0.3901
    2. Gate 6 check 4, proto vs linear    the claim currently BANNED by D-44
    3. the support law                    the strongest result in the project, and so far
                                          measured on 9 ferguson labels from a single fit

EVERY FIT IS CACHED SEPARATELY, so this survives a Kaggle timeout and resumes fold by fold.

WHAT THE INTERVALS COVER, stated so they are not read as more than they are. Each seed varies the
model initialisation, the batch order, the mask draw AND the cells drawn per cohort (s6.load_cohort
`draw_seed`). It does NOT vary the slide split, which is fixed by config.SEED in s2.slide_split -
so these are intervals over training and sampling, not over which slides landed in which split.
A wider claim would need the split resampled too, and that changes what every earlier gate was
measured on.
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import WORK, REPORTS, SEED                               # noqa: E402
import s1b_labels as s1b                                             # noqa: E402
import s2_tokens as s2                                               # noqa: E402
import s3_encoder as s3                                              # noqa: E402
import s6_train as s6                                                # noqa: E402
import s7_eval as s7                                                 # noqa: E402

CKPT = os.path.join(WORK, 'ckpt')
OUT = os.path.join(REPORTS, 's8_seeds.md')
TRAIN = s7.TRAIN
N_SEEDS = 5
ARMS = ('proto', 'linear')          # check 4's two heads, both re-run at every seed


def seeds(n):
    return [SEED + 1000 * i for i in range(n)]


# ----------------------------------------------------------------------------- one fit
_DATA_CACHE = {}


def cohort_data(seed, per, tri2idx, V, L, excl):
    """Load the five training cohorts ONCE PER SEED, not once per fit.

    The draw depends only on the seed, so all 11 fits that share a seed - 5 folds x 2 heads, plus
    the frozen one - can share the tensors. Without this the run pays 55 parquet loads instead of
    5, and on the first CPU smoke test that was most of the wall clock. It does not change a
    single number: `data` is only read during fit, never mutated.
    """
    if seed not in _DATA_CACHE:
        _DATA_CACHE.clear()          # one seed's tensors at a time; five would not fit comfortably
        d = {c: s6.load_cohort(c, per[c], tri2idx, V, L, excl, draw_seed=seed) for c in TRAIN}
        _DATA_CACHE[seed] = {c: x for c, x in d.items() if x is not None}
    return _DATA_CACHE[seed]


def fit_one(kind, seed, held, head, per, tri2idx, triples, excl, epochs, refit, quick):
    tag = f's8_{kind}_{head}_{held}_s{seed}' + ('_quick' if quick else '')
    p = os.path.join(CKPT, f'{tag}.pt')
    if os.path.exists(p) and not refit:
        return torch.load(p, weights_only=False)

    t0 = time.time()
    V = len(triples)
    L = s7.label_space(s7.SPACE_FILES['A'][0])
    proto_path = s7.SPACE_FILES['A'][1]
    data = cohort_data(seed, per, tri2idx, V, L, excl)
    train_cohorts = sorted(c for c in data if c != held)
    assert s7.FROZEN not in data, 'the frozen holdout reached the training data - STOP'

    m, info = s6.fit(data, train_cohorts, L, V, head=head, use_vicreg=False, use_conf=True,
                     epochs=epochs, seed=seed, proto_path=proto_path)

    if kind == 'frozen':
        fz = s7.load_frozen(s7.FROZEN, per[s7.FROZEN], tri2idx, V, L)
        yp, yt = s6.predict(m, fz), fz['y']['test'].cpu().numpy()
    else:
        yp, yt = s6.predict(m, data[held]), data[held]['y']['test'].cpu().numpy()
    f1_all, per_cls = s3.macro_f1(yt, yp, L['n'])
    f1_core, _ = s3.macro_f1(yt, yp, L['n'], drop=L['unreliable'])

    r = dict(tag=tag, kind=kind, seed=seed, held=held, head=head,
             f1_core=f1_core, f1_all=f1_all, per_cls=per_cls,
             epochs=info['epochs_used'], val_f1=info['val_f1'],
             seconds=round(time.time() - t0, 1))
    torch.save(r, p)
    print(f'    [{kind}] seed {seed} · {head:6s} · held {held:9s} '
          f'F1core={f1_core:.4f}  {r["seconds"]:.0f}s  ep={info["epochs_used"]}')
    return r


# ----------------------------------------------------------------------------- statistics
def ci(v):
    """mean, half-width of the 95% CI, and n. t-based, because n is 5, not 500."""
    v = np.asarray([x for x in v if np.isfinite(x)], float)
    if len(v) < 2:
        return (float(v.mean()) if len(v) else np.nan), np.nan, len(v)
    from scipy import stats
    return float(v.mean()), float(stats.sem(v) * stats.t.ppf(0.975, len(v) - 1)), len(v)


def paired(a, b):
    """Paired test on matched pairs. Returns mean difference, CI half-width, t and p."""
    from scipy import stats
    d = np.asarray(a, float) - np.asarray(b, float)
    d = d[np.isfinite(d)]
    if len(d) < 2:
        return np.nan, np.nan, np.nan, np.nan
    t, p = stats.ttest_rel(np.asarray(a, float)[:len(d)], np.asarray(b, float)[:len(d)])
    return float(d.mean()), float(stats.sem(d) * stats.t.ppf(0.975, len(d) - 1)), float(t), float(p)


def cluster_cohorts():
    lm = pd.read_csv(os.path.join(WORK, 'label_map.csv'), keep_default_na=False)
    clusters = sorted(lm.cluster.unique())
    c2i = {c: i for i, c in enumerate(clusters)}
    return {c2i[c]: set(lm[(lm.cluster == c) & (lm.cohort.isin(TRAIN))].cohort) for c in clusters}


def support_law(res):
    """The support law across every class-fold of every seed - the point of doing this at all."""
    coh = cluster_cohorts()
    L = s7.label_space(s7.SPACE_FILES['A'][0])
    rows = []
    for r in res:
        if r['head'] != 'proto':
            continue
        d = r['per_cls']
        d = d[~d.cluster.isin(L['unreliable'])]
        for _, x in d.iterrows():
            n = len(coh[int(x.cluster)] - ({r['held']} if r['kind'] == 'loco' else set()))
            rows.append(dict(seed=r['seed'], held=r['held'], kind=r['kind'],
                             cluster=int(x.cluster), n_cohorts=n, f1=float(x.f1),
                             support=int(x.support)))
    b = pd.DataFrame(rows)
    b['band'] = pd.cut(b.n_cohorts, [-1, 0, 1, 2, 5],
                       labels=['0 (unlearnable)', '1 cohort', '2 cohorts', '3+ cohorts'])
    # one value per (band, seed) first, so the interval is over SEEDS not over class-folds -
    # class-folds inside a seed are not independent and would give a fake-narrow interval
    per_seed = b.groupby(['band', 'seed'], observed=True).f1.mean().reset_index()
    out = []
    for band, g in per_seed.groupby('band', observed=True):
        m, h, n = ci(g.f1.to_numpy())
        sub = b[b.band == band]
        out.append(dict(band=band, mean_f1=m, ci95=h, seeds=n,
                        class_folds=len(sub), zero_share=float((sub.f1 == 0).mean())))
    ok = b[b.n_cohorts > 0]
    r = float(np.corrcoef(ok.n_cohorts, ok.f1)[0, 1]) if len(ok) > 2 else np.nan
    return pd.DataFrame(out), r, b


# ----------------------------------------------------------------------------- report
def write_report(res, mins):
    d = pd.DataFrame([{k: r[k] for k in ('kind', 'seed', 'held', 'head', 'f1_core', 'f1_all',
                                         'epochs', 'val_f1', 'seconds')} for r in res])
    L = []
    A = L.append
    A('# Step 3 - repeated seeds and confidence intervals\n')
    A(f'{len(res)} fits, {mins:.1f} min. Nothing is re-tuned and no verdict moves. What changes '
      'is which sentences may be written about the verdicts that already exist.\n')

    loco = d[d.kind == 'loco']
    froz = d[d.kind == 'frozen']

    # ---------------------------------------------------------------- 1. the LOCO headline
    if len(loco):
        ship = loco[loco.head == 'proto']
        per_seed = ship.groupby('seed').f1_core.mean()
        m, h, n = ci(per_seed.to_numpy())
        A('## 1. The Gate 6 LOCO headline\n')
        A(f'Gate 6 reported **0.3901** from one seed. Over {n} seeds, each averaged across the 5 '
          f'LOCO folds:\n')
        A(f'> **{m:.4f} +/- {h:.4f}** (95% CI, n = {n} seeds)\n')
        A('Per fold, mean over seeds:\n')
        t = ship.groupby('held').f1_core.agg(['mean', 'std', 'min', 'max', 'count'])
        A(s1b.md_table(t.reset_index(), '{:.4f}'))
        A('')

    # ---------------------------------------------------------------- 2. check 4
    if len(loco) and loco.head.nunique() == 2:
        pv = loco.pivot_table(index=['seed', 'held'], columns='head', values='f1_core')
        pv = pv.dropna()
        md, hw, t_, p_ = paired(pv['proto'].to_numpy(), pv['linear'].to_numpy())
        A('## 2. Gate 6 check 4 - the claim D-44 banned\n')
        A('Check 4 asked whether the prototype head beats the plain linear head by >= 0.02. At '
          'one seed it measured +0.0209, cleared the threshold by 0.0009, and had p = 0.460 with '
          'the whole margin coming from the Sorin fold. D-44 recorded the PASS and BANNED the '
          'sentence "the prototype loss improves cross-cohort transfer".\n')
        A(f'| | value |')
        A(f'|---|---|')
        A(f'| paired mean difference (proto - linear) | **{md:+.4f}** |')
        A(f'| 95% CI | [{md - hw:+.4f}, {md + hw:+.4f}] |')
        A(f'| t | {t_:+.3f} |')
        A(f'| p | **{p_:.4f}** |')
        A(f'| pairs (seed x fold) | {len(pv)} |')
        A('')
        if p_ < 0.05 and md > 0:
            A(f'**The ban is LIFTED.** With {len(pv)} paired observations instead of 5 the '
              f'effect is significant at p = {p_:.4f}. The claim may now be written - as '
              f'{md:+.4f}, which is what it is, not as the +0.0209 the single seed showed.\n')
        elif p_ < 0.05:
            A(f'**Significant, and in the WRONG direction** ({md:+.4f}). The prototype head is '
              'measurably worse. Gate 6 passed its declared rule on a fluke of one seed. Record '
              'it and say so.\n')
        else:
            A(f'**The ban STANDS.** Even at {len(pv)} paired observations the difference is '
              f'{md:+.4f} with p = {p_:.4f} and an interval containing zero. The prototype head '
              'ships on a design argument - Stage 7b\'s abstain rule needs prototype distances - '
              'and NOT on a measured gain. That must be how it is written up.\n')

    # ---------------------------------------------------------------- 3. ferguson
    if len(froz):
        m, h, n = ci(froz.f1_core.to_numpy())
        A('## 3. The ferguson zero-shot number\n')
        A(f'Gate 7 reported **0.3309** from one seed. Over {n} seeds:\n')
        A(f'> **{m:.4f} +/- {h:.4f}** (95% CI, n = {n} seeds)\n')
        A(s1b.md_table(froz[['seed', 'f1_core', 'f1_all', 'epochs', 'val_f1']], '{:.4f}'))
        A('')

    # ---------------------------------------------------------------- 4. the support law
    bands, r_all, raw = support_law(res)
    A('## 4. The support law - the result that most needed this\n')
    A('Gate 7 measured it on 9 ferguson labels from a single fit. Here it is over every '
      'class-fold of every seed. Intervals are over SEEDS, not over class-folds: class-folds '
      'inside one seed are not independent and pooling them would give a fake-narrow interval.\n')
    A(s1b.md_table(bands, '{:.4f}'))
    A('')
    A(f'Correlation between contributing training cohorts and F1, over learnable class-folds: '
      f'**{r_all:.3f}** ({len(raw[raw.n_cohorts > 0]):,} class-folds).\n')
    b3 = bands[bands.band == '3+ cohorts']
    b12 = raw[(raw.n_cohorts.isin([1, 2]))]
    if len(b3):
        A(f'Clusters carried by 3+ training cohorts: **{b3.mean_f1.iloc[0]:.4f} +/- '
          f'{b3.ci95.iloc[0]:.4f}**, with {b3.zero_share.iloc[0]:.1%} of class-folds at exactly '
          f'zero. Clusters carried by 1-2: mean {b12.f1.mean():.4f}, '
          f'{float((b12.f1 == 0).mean()):.1%} at exactly zero.\n')
    A('**This is the claim the thesis should lead with.** It is monotone, it holds inside the '
      'training roster, on held-out cohorts, and on an unseen machine and tissue, and it now has '
      'intervals.\n')

    A('## What these intervals cover\n')
    A('Each seed varies the model initialisation, the batch order, the mask draw and the cells '
      'drawn per cohort. It does NOT vary the slide split, which is fixed by `config.SEED` in '
      '`s2.slide_split`. So these are intervals over training and sampling, not over which '
      'slides landed in which split - a wider claim would need the split resampled too, and that '
      'changes what every earlier gate was measured on.\n')

    os.makedirs(REPORTS, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    return d


def main():
    quick = '--quick' in sys.argv
    refit = '--refit' in sys.argv
    epochs = 2 if quick else s6.EPOCHS
    n_seeds = int(sys.argv[sys.argv.index('--seeds') + 1]) if '--seeds' in sys.argv else N_SEEDS
    do_loco, do_frozen = '--loco' in sys.argv, '--frozen' in sys.argv
    if '--report' not in sys.argv and not (do_loco or do_frozen):
        print(__doc__)
        return

    cohorts = TRAIN + [s7.FROZEN]
    triples, tri2idx, per, _, _ = s2.read_panel(cohorts)
    excl = s6.excluded_pairs()
    sd = seeds(n_seeds)
    print(f'device: {s6.DEV} | seeds: {sd}')

    # Grouped BY SEED, so every fit sharing a seed runs consecutively and hits the data cache.
    # Ordering the other way round would reload the five cohorts on almost every fit.
    jobs = []
    for s_ in sd:
        if do_loco:
            jobs += [('loco', s_, h, held) for h in ARMS for held in TRAIN]
        if do_frozen:
            jobs += [('frozen', s_, 'proto', 'ferguson')]
    print(f'{len(jobs)} fits planned, grouped by seed so each seed loads its cohorts once\n')

    t0 = time.time()
    if '--report' in sys.argv:
        res = []
        for kind, s_, h, held in jobs:
            p = os.path.join(CKPT, f's8_{kind}_{h}_{held}_s{s_}.pt')
            if os.path.exists(p):
                res.append(torch.load(p, weights_only=False))
        print(f'loaded {len(res)} cached fits of {len(jobs)}')
        if not res:
            return
        d = write_report(res, sum(r['seconds'] for r in res) / 60)
    else:
        res = [fit_one(k, s_, held, h, per, tri2idx, triples, excl, epochs, refit, quick)
               for k, s_, h, held in jobs]
        if quick:
            print(f'\nsmoke test done in {(time.time()-t0)/60:.1f} min - no report written')
            return
        d = write_report(res, (time.time() - t0) / 60)
    print()
    print(d.groupby(['kind', 'head']).f1_core.agg(['mean', 'std', 'count']).round(4).to_string())
    print(f'\nreport -> {OUT}')


if __name__ == '__main__':
    main()

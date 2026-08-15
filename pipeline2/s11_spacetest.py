"""Stage 11 - IS THE DERIVED LABEL SPACE AS GOOD AS A CURATED ONE? Closes H13(b).

    python pipeline2/s11_spacetest.py --build      # build the three label spaces, no training
    python pipeline2/s11_spacetest.py              # build + 9 LOCO fits (needs a GPU)
    python pipeline2/s11_spacetest.py --quick      # smoke test, scores nothing

THIS IS THE THESIS CLAIM, TESTED AS AN OUTCOME. The project claims label harmonisation can be
LEARNED from marker profiles instead of hand-written. So far that claim has been measured exactly
once, as AGREEMENT between the learned mapping and the hand one (0.928, Gate 1b check 1). Agreement
is not the claim. The claim is that a model trained on the derived space annotates a new cohort as
well as one trained on the curated space. H13 calls this "the single most important experiment left
in the project". Nothing here is new architecture; it is Gate 6's shipped configuration run twice.

SCOPE IS FORCED BY THE DATA, NOT CHOSEN. `_validation/hand_mapping_reference.csv` covers CRC,
Keren, UPMC and ferguson only - Phillips and Sorin were never hand-mapped. ferguson is the frozen
holdout. So the experiment is 3-fold LOCO over CRC/Keren/UPMC, and BOTH arms are restricted to
those three. Comparing a 5-cohort derived arm against a 3-cohort hand arm would measure training
set size, not label space.

THREE SPACES, AND THE MIDDLE ONE CARRIES THE VERDICT:

  hand      the curated `target` level, keep==1. The human answer.
  derived   Stage 1b's own clustering of these 3 cohorts, at the cut its own rule picks. What the
            method actually produces when left alone. Confounded with granularity if its cluster
            count differs from hand's, and it is reported WITH that caveat, never without.
  matched   the same clustering forced to the cut that yields the SAME NUMBER of scored classes as
            hand. Granularity held fixed, so the only thing that varies is WHO drew the boundaries.
            This is the paired test. It is the B2 trick from Stage 7 reused deliberately: Gate 7
            check 4 measured that a three-cluster granularity difference moves macro-F1 by more
            than the effect being looked for, so an unmatched comparison here would be unreadable.

BOTH ARMS SCORE THE IDENTICAL CELLS. `L['key']` is built over only the (cohort, label) pairs that
have BOTH a hand target and a derived cluster, so `s6.load_cohort` draws the same rows in every
arm. A cell that only one space can place would otherwise silently change the denominator.

PROTOTYPES COME FROM THE SAME FUNCTION FOR EVERY ARM. `s1b.name_clusters` computes each class's
mean marker signature over the 99-triple vocabulary; the hand space is passed through it exactly as
the derived one is. Giving the derived arm an informed prototype init and the hand arm a random one
would decide the experiment before it ran.

n = 3 FOLDS. That is far too few for an interval, and the report says so rather than dressing it
up. The per-CLASS-per-fold differences are reported alongside, which gives roughly 60 paired points
instead of 3 - still not independent, but readable. H9 is the standing complaint that this project
puts point estimates under decisions they cannot support; this file must not add another.
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                                        # noqa: E402
from config import WORK, REPORTS, SEED                               # noqa: E402
import s1b_labels as s1b                                             # noqa: E402
import s1b_control as ctl                                            # noqa: E402
import s2_tokens as s2                                               # noqa: E402
import s3_encoder as s3                                              # noqa: E402
import s6_train as s6                                                # noqa: E402

COHORTS = ['CRC', 'Keren', 'UPMC']          # every cohort the hand mapping covers, minus holdout
LEVEL = 'target'                            # the finest hand level; L2/L1 are its coarsenings
OUT = os.path.join(REPORTS, 's11_spacetest.md')
CKPT = os.path.join(WORK, 'ckpt')
PROTO = os.path.join(WORK, 'proto_s11_{}.npy')
LMAP = os.path.join(WORK, 'label_map_s11_{}.csv')
TAGS = ('hand', 'derived', 'matched')


def write_space(tag, nodes, memb, names, unrel, tau, usable):
    """Persist a space as a label-map CSV, so the GPU run never needs the signature file.

    THIS IS WHY IT EXISTS, and it is the same split s7_spaces/s7_eval already use: building a
    space needs work/s1b_signatures.npz (100 MB, and make_upload.py deliberately excludes it
    because no GPU stage reads it), while TRAINING in that space needs only the finished mapping
    and the prototype centroids. Recomputing the clustering on Kaggle would ship 100 MB to
    reproduce a partition that is already decided - and would make the space depend on which
    files reached the GPU box, which is exactly the D-39 failure.
    """
    rows = [dict(cohort=nodes.cohort[i], label=nodes.label[i], n_cells=int(nodes.n_cells[i]),
                 cluster=int(memb[i]), cluster_name=(names[int(memb[i])] if memb[i] >= 0 else ''),
                 unreliable=int(unrel.get(int(memb[i]), 0)) if memb[i] >= 0 else 1)
            for i in range(len(nodes)) if memb[i] >= 0]
    d = pd.DataFrame(rows)
    d.to_csv(LMAP.format(tag), index=False)
    return d


def read_space(tag):
    """A space as Stage 6 needs it, from the CSV alone. No signatures, no clustering."""
    p = LMAP.format(tag)
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p, keep_default_na=False)
    clusters = sorted(d.cluster.unique())
    c2i = {c: i for i, c in enumerate(clusters)}
    names = (d.drop_duplicates('cluster').set_index('cluster').cluster_name
             .reindex(clusters).fillna('').tolist())
    # tau and the usable-window flag are provenance, not inputs - they change no computation, but
    # the report's pre-training finding is stated from them, so they travel in the sidecar rather
    # than being silently lost when the space is read back on the GPU box.
    j = os.path.join(WORK, 's11_spaces.json')
    meta = json.load(open(j)).get(tag, {}) if os.path.exists(j) else {}
    return dict(n=len(clusters),
                key={(r.cohort, r.label): c2i[r.cluster] for r in d.itertuples()},
                names=names,
                unreliable={c2i[r.cluster] for r in d.itertuples() if int(r.unreliable) == 1},
                n_labels=len(d), proto=PROTO.format(tag),
                tau=meta.get('tau'), usable=meta.get('usable'))


# ----------------------------------------------------------------------------- label spaces
def waiver():
    """The stroma waiver (D-23/D-32) as a per-LABEL flag, read from the shipped map.

    It lives on labels, not clusters, so it survives any re-clustering. A class is flagged when
    the MAJORITY OF ITS CELLS come from flagged labels - the same majority-of-cells rule
    s7_spaces.py uses, reused so the two files cannot drift apart.
    """
    lm = pd.read_csv(os.path.join(WORK, 'label_map.csv'), keep_default_na=False)
    return {(r.cohort, r.label): int(r.unreliable) for r in lm.itertuples()}


def flag_classes(nodes, memb, flags, n_cl):
    out = {}
    for c in range(n_cl):
        w = np.flatnonzero(memb == c)
        cells = nodes.n_cells.to_numpy()[w].astype(float)
        bad = np.array([flags.get((nodes.cohort[i], nodes.label[i]), 0) for i in w], float)
        out[c] = int((bad * cells).sum() > 0.5 * cells.sum()) if len(w) else 0
    return out


def hand_membership(nodes):
    """Hand target index per node, -1 where the human never mapped that label."""
    h = s1b.load_hand()
    h = h[(h.keep == 1) & (h.cohort.isin(COHORTS))]
    key = {(r.cohort, r.native_label): r._asdict()[LEVEL] for r in h.itertuples()}
    tg = [key.get((c, l)) for c, l in zip(nodes.cohort, nodes.label)]
    names = sorted({t for t in tg if t is not None})
    idx = {t: i for i, t in enumerate(names)}
    return np.array([idx.get(t, -1) for t in tg]), names


def memb_at(S3, SIM, EV, C, tau):
    """cluster -> refine -> nesting at a GIVEN cut.

    This is ctl.run()'s body with `choose_cut` removed. The cut sweep is a LOCO stability
    computation over the whole grid; running it once per candidate tau would repeat that ~35
    times to answer a question that does not depend on it. The three steps that DO decide the
    partition are called in the same order with the same arguments, so a forced cut here and a
    forced cut through ctl.run give the same membership.
    """
    m0 = s1b.cluster(np.arange(len(S3['nodes'])), SIM, EV, tau)
    m1, _ = s1b.refine(S3, m0, SIM, EV)
    m, _, _ = s1b.nesting(S3, m1, C, EV, SIM=SIM, cut=tau)
    return m


def n_scored(memb, shared):
    """Distinct classes among the SHARED nodes - the count macro-F1 will actually average over."""
    return len(set(int(x) for x in np.asarray(memb)[shared] if x >= 0))


def build_spaces():
    """Three label spaces over the same nodes and the same shared label set."""
    S6 = s1b.load_signatures()
    S3, _ = ctl.subset(S6, COHORTS)
    nodes = S3['nodes'].reset_index(drop=True)
    Z3, P3, W3 = s1b.rescale(S3)
    ncoh = np.array([nodes.cohort[np.isfinite(P3[:, t])].nunique() for t in range(P3.shape[1])])
    flags = waiver()

    hand_m, hand_names = hand_membership(nodes)
    # the derived arm's OWN cut still goes through ctl.run, because choosing it is part of the
    # method under test and must not be short-circuited
    r_der = ctl.run(S3, 'derived')
    der_m, der_tau, der_usable = r_der['memb'], r_der['tau'], r_der['usable']
    if not der_usable:
        print('\n  *** FINDING, before any model runs: on 3 cohorts NO cut satisfies Stage 1b\'s'
              '\n      three hard guards, so the method cannot choose a granularity here at all.'
              '\n      The `derived` arm below is therefore degenerate and is reported as such;'
              '\n      the `matched` arm tests the BOUNDARIES with granularity supplied. ***')
    SIM, EV = r_der['SIM'], r_der['EV']
    _, C, _, _ = s1b.containment(S3, (Z3, P3, W3))

    # SHARED = a label both spaces can place. Everything is scored on exactly these.
    shared = np.flatnonzero((hand_m >= 0) & (der_m >= 0))
    k_hand = n_scored(hand_m, shared)
    k_der = n_scored(der_m, shared)
    print(f'\n  shared labels: {len(shared)} of {len(nodes)} | '
          f'hand {k_hand} classes | derived {k_der} classes at its own cut {der_tau:.3f}')

    # ---- matched arm: search the declared cut grid for the tau giving k_hand scored classes
    best, mat_m, mat_tau = None, None, None
    for t in s1b.CUT_GRID:
        m = memb_at(S3, SIM, EV, C, float(t))
        k = n_scored(m, shared)
        d = abs(k - k_hand)
        if best is None or d < best:
            best, mat_m, mat_tau = d, m, float(t)
        if d == 0:
            break
    k_mat = n_scored(mat_m, shared)
    print(f'  matched arm: cut {mat_tau:.3f} gives {k_mat} scored classes '
          f'(target {k_hand}, |gap| {best})')

    spaces = {}
    for tag, memb, names_or_none in (('hand', hand_m, hand_names),
                                     ('derived', der_m, None),
                                     ('matched', mat_m, None)):
        m = np.asarray(memb).copy()
        keep = np.zeros(len(nodes), bool)
        keep[shared] = True
        m[~keep] = -1
        present = sorted({int(x) for x in m if x >= 0})
        remap = {c: i for i, c in enumerate(present)}
        m2 = np.array([remap.get(int(x), -1) for x in m])
        n_cl = len(present)

        # prototypes from the SAME function for every arm - see the module docstring
        full = np.where(m2 >= 0, m2, 0)
        names, cen, _ = s1b.name_clusters(S3, full, P3, ncoh)
        if names_or_none is not None:
            names = [names_or_none[c] for c in present]
        np.save(PROTO.format(tag), cen)

        unrel = flag_classes(nodes, m2, flags, n_cl)
        key = {(nodes.cohort[i], nodes.label[i]): int(m2[i])
               for i in range(len(nodes)) if m2[i] >= 0}
        write_space(tag, nodes, m2, names, unrel,
                    (der_tau if tag == 'derived' else (mat_tau if tag == 'matched' else None)),
                    der_usable if tag == 'derived' else None)
        spaces[tag] = dict(n=n_cl, key=key, names=names,
                           unreliable={c for c, v in unrel.items() if v},
                           tau=(None if tag == 'hand' else
                                (der_tau if tag == 'derived' else mat_tau)),
                           usable=(der_usable if tag == 'derived' else None),
                           n_labels=len(key), proto=PROTO.format(tag))
        print(f'    {tag:8s} {n_cl:2d} classes | {len(key):2d} labels | '
              f'{len(spaces[tag]["unreliable"])} flagged unreliable')
    return spaces, nodes, shared


# ----------------------------------------------------------------------------- the run
def loco(tag, L, per, tri2idx, V, excl, epochs, refit):
    res = []
    for held in COHORTS:
        p = os.path.join(CKPT, f's11_{tag}_{held}.pt')
        if os.path.exists(p) and not refit:
            print(f'    [cache] {tag}/{held}')
            res.append(torch.load(p, weights_only=False))
            continue
        t0 = time.time()
        rest = [c for c in COHORTS if c != held]
        data = {c: s6.load_cohort(c, per[c], tri2idx, V, L, excl) for c in COHORTS}
        data = {c: d for c, d in data.items() if d is not None}
        m, info = s6.fit(data, [c for c in rest if c in data], L, V, head='proto',
                         use_vicreg=False, use_conf=True, epochs=epochs,
                         proto_path=L['proto'])
        yp = s6.predict(m, data[held])
        yt = data[held]['y']['test'].cpu().numpy()
        f1_core, per_cls = s3.macro_f1(yt, yp, L['n'], drop=L['unreliable'])
        f1_all, _ = s3.macro_f1(yt, yp, L['n'])
        r = dict(space=tag, held=held, n_class=L['n'], f1_core=round(f1_core, 4),
                 f1_all=round(f1_all, 4), per_cls=per_cls, epochs=info['epochs_used'],
                 n_test=len(yt), seconds=round(time.time() - t0, 1))
        torch.save(r, p)
        print(f"    [done ] {tag:8s} held={held:6s} F1core={f1_core:.4f}  "
              f"epochs={info['epochs_used']}  {r['seconds']:.0f}s")
        res.append(r)
    return res


def per_class_pairs(a, b):
    """Paired per-(class, fold) F1 differences between two arms.

    3 folds give 3 paired points, which is not an interval. Classes are not independent of each
    other, so this is not one either - but it is ~60 points instead of 3 and it shows WHERE the
    difference lives rather than only how big it is. Reported as a spread, never as a p-value.
    """
    rows = []
    for ra, rb in zip(a, b):
        pa = ra['per_cls'].set_index('cluster').f1
        pb = rb['per_cls'].set_index('cluster').f1
        n = min(len(pa), len(pb))
        for i in range(n):
            rows.append(dict(held=ra['held'], rank=i,
                             a=float(pa.sort_values(ascending=False).iloc[i]),
                             b=float(pb.sort_values(ascending=False).iloc[i])))
    d = pd.DataFrame(rows)
    d['diff'] = d.a - d.b
    return d


def write_report(spaces, R, mins):
    L_, A = [], lambda s: L_.append(s)
    A('# Stage 11 - derived label space vs curated label space (closes H13b)\n')
    A('The thesis claim tested as an OUTCOME rather than as an agreement score. Gate 6\'s shipped '
      'configuration, run once per label space, on identical folds and identical cells.\n')
    A('## The spaces\n')
    A('| space | classes | labels | cut | note |')
    A('|---|---|---|---|---|')
    for t, s in spaces.items():
        note = {'hand': 'the curated answer',
                'derived': 'Stage 1b alone, its own cut - granularity NOT matched',
                'matched': 'Stage 1b forced to the same class count - **the paired test**'}[t]
        A(f'| {t} | {s["n"]} | {s["n_labels"]} | '
          f'{"-" if s["tau"] is None else f"{s['tau']:.3f}"} | {note} |')
    A('')
    if spaces['derived'].get('usable') is False:
        A('## A finding that landed before any model ran\n')
        A('**On these 3 cohorts, NO cut satisfies Stage 1b\'s three hard guards.** The method '
          'cannot choose a granularity from 3 cohorts at all; it falls back to the bottom of the '
          f'grid ({spaces["derived"]["tau"]:.3f}) and returns {spaces["derived"]["n"]} classes '
          f'over {spaces["derived"]["n_labels"]} labels - very nearly all singletons.\n')
        A('So the claim splits in two, and only one half survives here:\n')
        A('- **granularity selection FAILS at 3 cohorts.** It worked at 5-6. This is the same '
          'weakness H11 records - the cut is an argmax over a stability curve whose whole range '
          'is 0.062 - showing up as an outright failure once the roster shrinks.')
        A('- **boundary derivation is still testable**, with the granularity supplied from '
          'outside. That is the `matched` arm, and it is the only arm whose comparison to `hand` '
          'means anything.\n')
        A('The `derived` row is kept in the table because deleting a degenerate arm and reporting '
          'only the working one is how results get flattered.\n')
    d = pd.DataFrame([{k: r[k] for k in ('space', 'held', 'n_class', 'f1_core', 'f1_all')}
                      for r in R])
    piv = d.pivot_table(index='space', columns='held', values='f1_core')
    piv['mean'] = piv.mean(axis=1)
    A('## macro-F1 (reliable classes), per held-out cohort\n')
    A(piv.round(4).to_markdown())
    A('')
    by = {t: [r for r in R if r['space'] == t] for t in spaces}
    if 'matched' in by and 'hand' in by:
        dm = np.array([x['f1_core'] for x in by['matched']])
        dh = np.array([x['f1_core'] for x in by['hand']])
        gap = dm - dh
        A('## The verdict - matched granularity\n')
        A(f'| held out | derived (matched) | hand | difference |')
        A(f'|---|---|---|---|')
        for i, c in enumerate([x['held'] for x in by['matched']]):
            A(f'| {c} | {dm[i]:.4f} | {dh[i]:.4f} | {gap[i]:+.4f} |')
        A(f'| **mean** | **{dm.mean():.4f}** | **{dh.mean():.4f}** | **{gap.mean():+.4f}** |')
        A('')
        A(f'**n = 3 folds. This is not an interval and is not presented as one.** The per-class '
          f'spread below carries more information.\n')
        pc = per_class_pairs(by['matched'], by['hand'])
        A(f'Per-(class, fold) differences, {len(pc)} paired points: '
          f'mean {pc["diff"].mean():+.4f}, median {pc["diff"].median():+.4f}, '
          f'{int((pc["diff"] > 0).sum())} favour derived, '
          f'{int((pc["diff"] < 0).sum())} favour hand.\n')
        if abs(gap.mean()) < 0.02:
            A('**The two spaces perform equivalently.** That is the result the thesis needs: the '
              'derived space costs nothing against a curated one, so the curation step it '
              'replaces was not doing work the markers could not do. Note this is an EQUIVALENCE '
              'claim on n=3 - it is evidence the difference is small, not proof it is zero.\n')
        elif gap.mean() > 0:
            A('**The derived space is BETTER.** Unexpected, and worth stating as such before it '
              'is explained.\n')
        else:
            A('**The derived space is WORSE.** This is the outcome that would falsify the '
              'central claim as currently written, and it must be reported as the headline, not '
              'as a limitation.\n')
    A(f'\n## How this was run\n')
    A(f'- **{", ".join(COHORTS)}** only - the hand mapping covers no other trainable cohort.')
    A(f'- Both arms score IDENTICAL cells: `key` is built over the {spaces["hand"]["n_labels"]} '
      f'labels both spaces can place.')
    A('- Prototypes for every arm come from `s1b.name_clusters`, so no arm gets a better init.')
    A('- Gate 6 shipped configuration: prototype head, cell-type + masked-marker losses, no '
      'VICReg (D-44), no adversary (D-36), confidence weighting on.')
    A(f'- {len(R)} fits, {mins:.1f} min.\n')
    os.makedirs(REPORTS, exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write('\n'.join(L_))
    return piv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', action='store_true', help='build the spaces and stop')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--refit', action='store_true')
    a = ap.parse_args()

    print(f'STAGE 11 - derived vs curated label space   (device {s6.DEV})')
    print(f'cohorts: {", ".join(COHORTS)} | hand level: {LEVEL}')
    cached = {t: read_space(t) for t in TAGS}
    if all(cached.values()) and not a.build:
        # the GPU path: everything the fits need is in the CSVs, so work/s1b_signatures.npz
        # (100 MB, excluded from the Kaggle upload by design) is never opened here
        spaces = cached
        print('  [cached] spaces read from work/label_map_s11_*.csv - no signature file needed')
        for t, s in spaces.items():
            print(f'    {t:8s} {s["n"]:2d} classes | {s["n_labels"]:2d} labels | '
                  f'{len(s["unreliable"])} flagged unreliable')
    else:
        spaces, nodes, shared = build_spaces()
        json.dump({t: dict(n=s['n'], names=s['names'], tau=s['tau'], usable=s.get('usable'),
                           n_labels=s['n_labels'], unreliable=sorted(s['unreliable']))
                   for t, s in spaces.items()},
                  open(os.path.join(WORK, 's11_spaces.json'), 'w'), indent=1)
        if a.build:
            print('\n--build: wrote work/label_map_s11_{hand,derived,matched}.csv, '
                  'work/proto_s11_*.npy and work/s11_spaces.json. Nothing trained.')
            print('  These are what ship to Kaggle - the signature file does not.')
            return

    triples, tri2idx, per, _, _ = s2.read_panel(COHORTS)
    V = len(triples)
    excl = s6.excluded_pairs()
    epochs = 2 if a.quick else s6.EPOCHS
    if a.quick:
        s6.N_TRAIN, s6.SCORE_CELLS = 1_500, 800

    t0, R = time.time(), []
    for tag, L in spaces.items():
        print(f'\n  space {tag} ({L["n"]} classes)')
        R += loco(tag, L, per, tri2idx, V, excl, epochs, a.refit)
    mins = (time.time() - t0) / 60
    if a.quick:
        print(f'\n--quick: {mins:.1f} min, scores nothing, no report written')
        return
    piv = write_report(spaces, R, mins)
    print()
    print(piv.round(4).to_string())
    print(f'\nreport -> {OUT}')


if __name__ == '__main__':
    main()

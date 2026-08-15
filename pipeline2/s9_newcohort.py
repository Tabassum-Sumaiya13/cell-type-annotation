"""Stage 9 - score a NEW cohort on the already-trained model. No training, no re-tuning.

    python pipeline2/s9_newcohort.py --cohort Danenberg               # prepare + score, space A
    python pipeline2/s9_newcohort.py --cohort Danenberg --spaces A,B2
    python pipeline2/s9_newcohort.py --cohort Danenberg --prepare     # build tables only

THIS IS D-24'S DEMONSTRATION. Danenberg was downloaded, its spec registered, and then deliberately
left out of the roster so it could play "a new cohort arrives later". The claim being tested is not
"the model is accurate on breast IMC" - it is "adding a cohort needs no code change". So nothing
here trains, nothing re-tunes, and no gate threshold moves. The shipped Stage 7 checkpoint is
loaded as-is and asked to label 1.1M cells it has never seen, from a machine/tissue/panel
combination that entered no loss.

FOUR THINGS ARE HELD FROZEN, and each one is asserted rather than assumed:

  1. THE VOCABULARY. work/panel.json's 99 triples, in that exact index order (D-39). The new
     cohort's markers are INTERSECTED with it: a marker the vocabulary does not contain is
     DROPPED (the model owns no embedding for it), and a vocabulary slot the cohort never
     measured is [ABSENT] - which is precisely the case Stage 2 arm B was built for. Growing the
     vocabulary would resize `ident.weight` and silently invalidate every checkpoint.
  2. THE PARTITION. The shipped 25-cluster space from work/label_map.csv. The new cohort's labels
     are placed INTO it by the s7_spaces rule - a label joins the cluster whose members are
     closest on average, admitted only within the same cut tau - and can never move a boundary.
     A label no cluster admits is marked NOVEL and dropped from the macro-F1, not forced into the
     nearest bin.
  3. THE WEIGHTS. work/ckpt/s7_A.pt, trained on the five training cohorts. Forward pass only.
  4. THE SIGNATURE BLOCK. rescale() is per-cohort and containment() is pairwise, so adding a 7th
     cohort cannot disturb the existing six. That is checked bit-for-bit (check 2) rather than
     argued, because if it were false every distance in the placement would be contaminated.

KNOWN DEFECT IN THE FROZEN VOCABULARY, carried deliberately. Keren's bare `SMA` resolves through
HGNC's PREVIOUS-symbol route to SMN1 (spinal muscular atrophy), not ACTA2 - the same failure mode
as the `Na` -> XK case that check 3c was written for, which that check does not catch because it
only guards declared non-protein channels. `HGNC:11117|pan|none` is therefore a real slot in the
99-triple vocabulary the model was trained on. Danenberg also ships a bare `SMA`, so it lands in
the same wrong slot. Repairing it would move Keren's marker to ACTA2, drop the vocabulary to 98,
and invalidate every checkpoint from Stage 2 onward, so it is REPORTED here and not repaired.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                                        # noqa: E402
from config import SPECS, WORK, VALUES, raw_table, value_table       # noqa: E402
import s1b_labels as s1b                                             # noqa: E402
import s1_values as s1                                               # noqa: E402
import s2_tokens as s2                                               # noqa: E402
import s3_encoder as s3                                              # noqa: E402
import s6_train as s6                                                # noqa: E402

CKPT = os.path.join(WORK, 'ckpt')
TRAIN = ['CRC', 'Keren', 'Phillips', 'Sorin', 'UPMC']       # what the checkpoint actually saw
SHIPPED_TAU = 0.800                                         # the cut space A was built at
SIG_PLUS = os.path.join(WORK, 's1b_signatures_plus.npz')    # 7-cohort signatures, separate file
SPACE_FILES = {'A': (os.path.join(WORK, 'label_map.csv'), os.path.join(CKPT, 's7_A.pt')),
               'B1': (os.path.join(WORK, 'label_map_B1.csv'), os.path.join(CKPT, 's7_B1.pt')),
               'B2': (os.path.join(WORK, 'label_map_B2.csv'), os.path.join(CKPT, 's7_B2.pt'))}
N_SUB = 40_000                                              # same draw size every cohort got


def hr(s):
    print(f'\n{"=" * 78}\n{s}\n{"=" * 78}')


# ------------------------------------------------------------------ 1. prepare the tables
def frozen_vocab():
    p = json.load(open(os.path.join(WORK, 'panel.json')))
    return p['index'], p['gene'], p['cohorts_measuring']


def cohort_triples(c, index):
    """The new cohort's markers, INTERSECTED with the frozen vocabulary.

    Returns (kept, dropped) where `dropped` are real proteins the cohort measures that the model
    has no slot for. They are listed, never quietly discarded - a reader needs to know how much of
    the panel was thrown away to make the run possible.
    """
    r = pd.read_csv(os.path.join(WORK, 'marker_registry.csv'), keep_default_na=False)
    r = r[(r.cohort == c) & (r.kind != 'non_protein') & (r.triple != '')]
    dup = r.triple.value_counts()
    dup = {t: n for t, n in dup.items() if n > 1}
    r = r.drop_duplicates('triple')
    kept = sorted(t for t in r.triple if t in index)
    dropped = r[~r.triple.isin(index)][['raw_column', 'core', 'gene', 'triple']]
    return kept, dropped, dup


def prepare(c, index):
    """Stages 0 -> 0b -> 1 -> 2 for one cohort. Every step is skipped if its output exists."""
    if not os.path.exists(raw_table(c)):
        print(f'  [stage 0 ] building {raw_table(c)} ...')
        import loaders
        loaders.build(c)
    else:
        print(f'  [stage 0 ] cached')

    reg = os.path.join(WORK, 'marker_registry.csv')
    have = pd.read_csv(reg, keep_default_na=False) if os.path.exists(reg) else pd.DataFrame()
    if not len(have) or c not in set(have.cohort):
        print(f'  [stage 0b] resolving {c} markers (HGNC/UniProt, cached where possible) ...')
        import s0b_markers as s0b
        s0b.build()                       # writes marker_registry.csv; the GATE 0b report is NOT
        print(f'            cache {s0b._stats["hit"]} hits / '   # rewritten, so it still describes
              f'{s0b._stats["miss"]} network calls')             # the 6-cohort run it was made for
    else:
        print(f'  [stage 0b] cached')

    kept, dropped, dup = cohort_triples(c, index)
    print(f'  [vocab   ] {len(kept)}/{len(index)} frozen slots filled by {c}; '
          f'{len(dropped)} of its markers have no slot and are dropped')
    if len(dropped):
        print('             dropped: ' + ', '.join(sorted(dropped.raw_column)))
    if dup:
        print(f'             duplicate triples inside {c}: {dup} (first column kept)')

    if not os.path.exists(value_table(c)):
        print(f'  [stage 1 ] ECDF over every cell, {N_SUB:,}-cell stratified table ...')
        info = s1.build(c, kept, n_sub=N_SUB)
        print(f'            {info}')
    else:
        print(f'  [stage 1 ] cached')

    if not os.path.exists(s2.full_table(c)):
        print(f'  [stage 2 ] wide token table ...')
        dyn, info = s2.build(c, kept)
        dead = dyn[dyn.rank_spread < s6.SPREAD_MIN]
        print(f'            {info}')
        print(f'            {len(dead)}/{len(dyn)} markers below the rank_spread floor '
              f'({s6.SPREAD_MIN}): {sorted(dead.triple.map(lambda t: t.split("|")[0]))}')
        dyn.to_csv(os.path.join(WORK, f's2_dynrange_{c}.csv'), index=False)
    else:
        print(f'  [stage 2 ] cached')
    return kept, dropped


# ------------------------------------------------------------------ 2. place the labels
def signatures(c):
    """Signatures over all 7 cohorts, written to a SEPARATE file so the shipped one is untouched.

    check 2 asserts the existing six cohorts' signatures are bit-identical to the shipped build.
    They must be: build_signatures() runs one independent pass per cohort. If this ever fires, the
    placement below is comparing the new cohort against a moved target.
    """
    cohorts = sorted(set(TRAIN + ['ferguson', c]))
    if not os.path.exists(SIG_PLUS):
        print(f'  building signatures for {len(cohorts)} cohorts -> {os.path.basename(SIG_PLUS)}')
        old = s1b.SIG_CACHE
        s1b.SIG_CACHE = SIG_PLUS
        try:
            S = s1b.build_signatures(cohorts)
        finally:
            s1b.SIG_CACHE = old
    else:
        old, s1b.SIG_CACHE = s1b.SIG_CACHE, SIG_PLUS
        S = s1b.load_signatures()
        s1b.SIG_CACHE = old
        print(f'  [cached ] {os.path.basename(SIG_PLUS)}')

    S6 = s1b.load_signatures()                                   # the shipped 6-cohort build
    n7, n6 = S['nodes'], S6['nodes']
    t7 = {t: i for i, t in enumerate(S['triples'])}
    key7 = {(r.cohort, r.label): i for i, r in enumerate(n7.itertuples())}
    bad = []
    for i, r in enumerate(n6.itertuples()):
        j = key7.get((r.cohort, r.label))
        if j is None:
            bad.append((r.cohort, r.label, 'missing from the 7-cohort build'))
            continue
        cols = [t7[t] for t in S6['triples']]
        if not np.allclose(S['MEAN'][j][cols], S6['MEAN'][i], equal_nan=True):
            bad.append((r.cohort, r.label, 'MEAN moved'))
    assert not bad, f'check 2 FAILED - the existing cohorts moved: {bad[:5]}'
    print(f'  check 2: all {len(n6)} existing signatures bit-identical after adding {c}: OK')
    return S


def place(c, S, lm_path, tau):
    """Put the new cohort's labels into the FROZEN partition, from marker signatures alone.

    Identical rule to s7_spaces.assign_frozen: nearest cluster by AVERAGE distance to its members,
    admitted only if that average is within the same cut the partition was built at. The new
    cohort contributes no node to any cluster and cannot move a boundary.
    """
    lm = pd.read_csv(lm_path, keep_default_na=False)
    lm = lm[lm.cluster >= 0]
    clusters = sorted(lm.cluster.unique())
    c2i = {k: i for i, k in enumerate(clusters)}
    memb = {(r.cohort, r.label): c2i[r.cluster] for r in lm.itertuples()}
    names = (lm.drop_duplicates('cluster').set_index('cluster').cluster_name
             .reindex(clusters).fillna('').tolist())
    unreliable = {c2i[r.cluster] for r in lm.itertuples() if int(r.unreliable) == 1}

    nodes = S['nodes'].reset_index(drop=True)
    Z, P, Wm = s1b.rescale(S)
    SIM, _, EV, _ = s1b.containment(S, (Z, P, Wm))
    D = s1b.distance(np.arange(len(nodes)), SIM, EV)

    members = {k: [] for k in range(len(clusters))}
    for i, r in enumerate(nodes.itertuples()):
        k = memb.get((r.cohort, r.label))
        if k is not None:
            members[k].append(i)

    rows = []
    for i, r in enumerate(nodes.itertuples()):
        if r.cohort != c:
            continue
        best_k, best_d = -1, np.inf
        for k, mem in members.items():
            d = float(np.mean(D[i, mem])) if mem else np.inf
            if d < best_d:
                best_k, best_d = k, d
        ok = bool(np.isfinite(best_d) and best_d <= tau and best_d < s1b.FAR)
        rows.append(dict(label=r.label, n_cells=int(r.n_cells), avg_dist=round(best_d, 4),
                         admitted=ok, cluster=(best_k if ok else -1),
                         cluster_name=(names[best_k] if ok else 'NOVEL - no cluster admits it'),
                         unreliable=int(best_k in unreliable) if ok else 1))
    A = pd.DataFrame(rows).sort_values('n_cells', ascending=False).reset_index(drop=True)
    return A, dict(n=len(clusters), names=names, unreliable=unreliable, lm=lm, c2i=c2i)


# ------------------------------------------------------------------ 3. score
def load_model(ck_path, V, n_class):
    ck = torch.load(ck_path, weights_only=False)
    assert ck['n_class'] == n_class, \
        f'checkpoint has {ck["n_class"]} classes, label space has {n_class}'
    m = s6.Stage6(V, n_class, head='proto').to(s6.DEV)
    m.load_state_dict(ck['state'])
    m.eval()
    return m, ck


def score(c, triples_c, index, A, L, ck_path):
    """Every cell of the new cohort's table, as pure test. Forward pass only."""
    V = len(index)
    key = {r.label: int(r.cluster) for r in A.itertuples()}
    tl = list(triples_c)
    v = pd.read_parquet(s2.full_table(c),
                        columns=['cell_id', 'image_id', 'native_label'] +
                                [f'u_coh::{t}' for t in tl])
    lab = v.native_label.astype(str)
    y = np.array([key.get(s_, -1) for s_ in lab])
    n_total, n_novel = len(v), int((y < 0).sum())
    ok = y >= 0
    v, y, lab = v[ok].reset_index(drop=True), y[ok], lab[ok].reset_index(drop=True)

    U = v[[f'u_coh::{t}' for t in tl]].to_numpy('float32')
    slots = np.array([index[t] for t in tl])
    full = np.zeros((len(U), V), 'float32')
    full[:, slots] = U
    present = np.zeros(V, bool)
    present[slots] = True

    m, ck = load_model(ck_path, V, L['n'])
    d = dict(idx=torch.arange(V).long().to(s6.DEV),
             present=torch.from_numpy(present).to(s6.DEV),
             U={'test': torch.from_numpy(full).to(s6.DEV)})
    yp = s6.predict(m, d)

    f1_all, per_cls = s3.macro_f1(y, yp, L['n'])
    f1_core, _ = s3.macro_f1(y, yp, L['n'], drop=L['unreliable'])
    maj = int(np.bincount(y, minlength=L['n']).argmax())
    f1_maj, _ = s3.macro_f1(y, np.full_like(y, maj), L['n'], drop=L['unreliable'])
    rnd = s6._rng('s9rand', c).integers(0, L['n'], len(y))
    f1_rnd, _ = s3.macro_f1(y, rnd, L['n'], drop=L['unreliable'])

    rows = []
    for name, g in pd.DataFrame(dict(label=lab, true=y, pred=yp)).groupby('label'):
        k = int(g.true.iloc[0])
        tp = int((g.pred == k).sum())
        fp = int(((yp == k) & (y != k)).sum())
        prec, rec = tp / max(1, tp + fp), tp / max(1, len(g))
        rows.append(dict(label=name, cells=len(g), cluster=k, cluster_name=L['names'][k],
                         unreliable=int(k in L['unreliable']), recall=round(rec, 4),
                         precision=round(prec, 4),
                         f1=round(2 * prec * rec / max(1e-9, prec + rec), 4)))
    PL = pd.DataFrame(rows).sort_values('cells', ascending=False).reset_index(drop=True)

    # the support law: how many TRAINING cohorts carry each target cluster
    inv = {i: k for k, i in L['c2i'].items()}
    sup = []
    for r in PL.itertuples():
        sub = L['lm'][(L['lm'].cluster == inv[r.cluster]) & (L['lm'].cohort.isin(TRAIN))]
        sup.append(dict(train_cohorts=int(sub.cohort.nunique()),
                        train_cells=int(sub.n_cells.sum()),
                        cohorts=', '.join(sorted(sub.cohort.unique()))))
    PL = pd.concat([PL, pd.DataFrame(sup)], axis=1)
    return dict(f1_core=f1_core, f1_all=f1_all, f1_majority=f1_maj, f1_random=f1_rnd,
                per_cls=per_cls, per_label=PL, n_scored=len(y), n_total=n_total,
                n_novel_cells=n_novel, epochs=ck['info']['epochs_used'])


# ------------------------------------------------------------------ driver
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cohort', required=True)
    ap.add_argument('--spaces', default='A')
    ap.add_argument('--prepare', action='store_true', help='build the tables and stop')
    a = ap.parse_args()
    c = a.cohort
    assert c in SPECS, f'{c} is not in config.SPECS'
    assert c not in TRAIN, f'{c} is a TRAINING cohort - this stage is for unseen cohorts only'

    index, gene, ncoh = frozen_vocab()
    hr(f'STAGE 9 - {c} on the frozen model   (device {s6.DEV})')
    print(f'vocabulary : {len(index)} triples, frozen (panel.json)')
    print(f'trained on : {", ".join(TRAIN)}   |   {c} entered no loss\n')

    triples_c, dropped = prepare(c, index)
    if a.prepare:
        return

    hr('label placement into the FROZEN partition')
    S = signatures(c)

    for tag in a.spaces.split(','):
        lm_path, ck_path = SPACE_FILES[tag]
        if not os.path.exists(ck_path):
            print(f'  space {tag}: no checkpoint at {ck_path} - skipped')
            continue
        A, L = place(c, S, lm_path, SHIPPED_TAU)
        adm = int(A.admitted.sum())
        print(f'\n  space {tag}: {L["n"]} clusters, tau {SHIPPED_TAU} | '
              f'{adm}/{len(A)} {c} labels admitted | '
              f'{len(L["unreliable"])} clusters flagged unreliable')
        pd.set_option('display.width', 200, 'display.max_colwidth', 44)
        print(A.to_string(index=False))

        r = score(c, triples_c, index, A, L, ck_path)
        hr(f'RESULT - {c} zero-shot, space {tag}')
        print(f'  macro-F1 (reliable clusters) : {r["f1_core"]:.4f}')
        print(f'  macro-F1 (all clusters)      : {r["f1_all"]:.4f}')
        print(f'  majority-class baseline      : {r["f1_majority"]:.4f}')
        print(f'  random baseline              : {r["f1_random"]:.4f}')
        print(f'  cells scored                 : {r["n_scored"]:,} of {r["n_total"]:,} '
              f'({r["n_novel_cells"]:,} in NOVEL labels, dropped)')
        print(f'  markers used                 : {len(triples_c)}/{len(index)} vocabulary slots\n')
        print(r['per_label'].to_string(index=False))

        d = r['per_label']
        rich, thin = d[d.train_cohorts >= 3], d[d.train_cohorts <= 2]
        if len(rich) and len(thin):
            print(f'\n  SUPPORT LAW on {c}:')
            print(f'    labels whose cluster is carried by >=3 training cohorts: '
                  f'{len(rich):2d}  mean F1 {rich.f1.mean():.4f}')
            print(f'    labels whose cluster is carried by <=2 training cohorts: '
                  f'{len(thin):2d}  mean F1 {thin.f1.mean():.4f}')
            rr = np.corrcoef(d.train_cohorts, d.f1)[0, 1]
            print(f'    correlation (n training cohorts, F1) = {rr:.3f}')


if __name__ == '__main__':
    main()

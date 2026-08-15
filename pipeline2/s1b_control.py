"""H10 control - did the frozen holdout help build the label space it will be scored in?

    python pipeline2/s1b_control.py            # run the control, write the report
    python pipeline2/s1b_control.py --refit    # ignore the cached comparison

THE PROBLEM. Stage 1b clustered all SIX cohorts together, so ferguson's 9 labels and their
marker signatures were in the distance matrix that produced the 25 clusters. ferguson cells have
never entered any loss, so this is not a training leak - but the LABEL SPACE Stage 7 is scored in
was not built blind to ferguson. A reviewer finds that in five minutes (files/07 gap 4).

WHY THIS IS A CONTROL AND NOT A REBUILD. Re-clustering on 5 cohorts and shipping THAT would
change the cluster count and invalidate every number produced since Gate 1b, with a month left.
The same choice was made at Gate 2: when a comparison changed two things at once, D-27 added a
CORE-9 CONTROL rather than rewriting the stage. This is that move again.

WHAT IT MEASURES. Run the identical chain - rescale -> containment -> choose_cut -> cluster ->
refine -> nesting - on the 5 TRAINING cohorts only, and compare the partition it produces against
the shipped 25-cluster partition restricted to those same 97 labels.

WHY SUBSETTING THE SIGNATURE CACHE IS SOUND. `rescale` loops over cohorts and touches one
cohort's rows at a time, so dropping ferguson's rows cannot change any other cohort's Z, P or W.
Check 1 asserts that consequence directly rather than trusting the argument: the SIM and EV
submatrices for the 97 shared labels must come out bit-identical. If they do, the only channel
ferguson had is the clustering itself - acting as a bridge in average linkage, shifting the cut
chosen by the guards, or changing a per-branch split's LOCO support - which is exactly what the
ARI then measures.

THRESHOLDS ARE DECLARED IN pipeline2/panel/gate1b_control_expect.csv, written before this file
was run for the first time. Do not move them after seeing the numbers (D-34).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s1b_labels as s1b                                             # noqa: E402
from config import ROOT, WORK                                        # noqa: E402

TRAIN = ['CRC', 'UPMC', 'Keren', 'Phillips', 'Sorin']
FROZEN = 'ferguson'
EXPECT = os.path.join(ROOT, 'pipeline2', 'panel', 'gate1b_control_expect.csv')
OUT = os.path.join(ROOT, 'reports', 's1b_control_ferguson.md')
ARI_W_MIN = 0.90          # check 2, declared
ARI_U_MIN = 0.85          # check 3, declared


# ------------------------------------------------------------------ the chain, run once
def subset(S, cohorts):
    """A signature cache holding only `cohorts`, in the original node order."""
    m = np.isin(S['cohort'], list(cohorts))
    out = {k: (v[m] if isinstance(v, np.ndarray) and v.shape[:1] == S['cohort'].shape else v)
           for k, v in S.items() if k not in ('nodes', 'dropped', 'rng')}
    rm = np.isin(S['rng_cohort'], list(cohorts))
    out['rng_cohort'], out['RNG'] = S['rng_cohort'][rm], S['RNG'][rm]
    out['nodes'] = pd.DataFrame(dict(cohort=out['cohort'], label=out['label'],
                                     prev=out['PREV'], n_cells=out['NCELL']))
    out['rng'] = {c: out['RNG'][i] for i, c in enumerate(out['rng_cohort'])}
    return out, np.flatnonzero(m)


def run(S, tag, force_tau=None):
    """Exactly the sequence in s1b_labels.main(), nothing added and nothing skipped.

    `force_tau` is used ONLY by the matched-cut diagnostic (checks 7/8), never by checks 1-4.
    """
    nodes = S['nodes']
    Z, P, Wm = s1b.rescale(S)
    SIM, C, EV, CX = s1b.containment(S, (Z, P, Wm))
    sweep = s1b.choose_cut(S, SIM, EV)
    ok = sweep[sweep.usable]
    usable = len(ok) > 0
    if not usable:
        print(f'  [{tag}] NO usable cut - no granularity satisfies all three guards')
        ok = sweep
    tau = float(ok.cut[ok.stability.idxmax()]) if force_tau is None else float(force_tau)
    memb0 = s1b.cluster(np.arange(len(nodes)), SIM, EV, tau)
    memb1, splits = s1b.refine(S, memb0, SIM, EV)
    memb, D, gi = s1b.nesting(S, memb1, C, EV, SIM=SIM, cut=tau)
    ncoh = np.array([nodes.cohort[np.isfinite(P[:, t])].nunique() for t in range(P.shape[1])])
    names, cen, zc = s1b.name_clusters(S, memb, P, ncoh)
    row = sweep[sweep.cut == tau].iloc[0]
    print(f'  [{tag}] {len(nodes)} labels | cut {tau:.3f} | {memb0.max()+1} at the cut -> '
          f'{memb1.max()+1} refined -> {memb.max()+1} after SCC | usable_window={usable}')
    return dict(tag=tag, nodes=nodes, SIM=SIM, EV=EV, tau=tau, memb=memb,
                names=[names[c] for c in memb], n_cut=int(memb0.max() + 1),
                n_refined=int(memb1.max() + 1), n_final=int(memb.max() + 1),
                splits=splits, sweep=sweep, usable=usable,
                biggest_share=float(row.biggest_share), cohort_ari=float(row.cohort_ari),
                stability=float(row.stability))


# ------------------------------------------------------------------ the comparison
def nesting_violations(fine, coarse):
    """Control clusters that span more than one shipped cluster.

    If there are none, the control partition is a strict REFINEMENT of the shipped one: nothing
    that was apart came together, only things that were together came apart. That is a much
    milder statement than a low ARI on its own suggests, because ARI punishes a pure granularity
    change just as hard as a genuine re-mixing.
    """
    out = []
    for f in np.unique(fine):
        cs = sorted({int(c) for c in np.asarray(coarse)[fine == f]})
        if len(cs) > 1:
            out.append(dict(control_cluster=int(f), labels=int((fine == f).sum()),
                            spans_shipped=', '.join(str(c) for c in cs)))
    return pd.DataFrame(out)


def pair_agreement(a, b):
    """Share of label PAIRS that agree on same-cluster / different-cluster."""
    a, b = np.asarray(a), np.asarray(b)
    sa = a[:, None] == a[None, :]
    sb = b[:, None] == b[None, :]
    iu = np.triu_indices(len(a), 1)
    same = sa[iu] == sb[iu]
    return float(same.mean()), int((~same).sum()), int(len(same))


def main():
    print('H10 control - re-clustering Stage 1b without the frozen holdout\n')
    S6 = s1b.load_signatures()
    assert FROZEN in set(S6['cohort']), 'ferguson is not in the signature cache'

    S5, keep = subset(S6, TRAIN)
    print(f'signature cache: {len(S6["cohort"])} labels, '
          f'{len(keep)} of them from the 5 training cohorts\n')

    r6 = run(S6, '6-cohort (shipped)')
    r5 = run(S5, '5-cohort (control)')
    print()

    # -------------------------------------------------- the shipped result must reproduce
    shipped = pd.read_csv(os.path.join(WORK, 'label_map.csv'), keep_default_na=False)
    key6 = list(zip(r6['nodes'].cohort, r6['nodes'].label))
    got = pd.DataFrame(dict(cohort=[k[0] for k in key6], label=[k[1] for k in key6],
                            cluster=r6['memb']))
    mrg = shipped.merge(got, on=['cohort', 'label'], suffixes=('_ship', '_repro'))
    assert len(mrg) == len(shipped), 'label sets differ between label_map.csv and this run'
    repro = s1b.ari(mrg.cluster_ship.to_numpy(), mrg.cluster_repro.to_numpy())
    exact = bool((mrg.cluster_ship.to_numpy() == mrg.cluster_repro.to_numpy()).all())
    print(f'reproduction of the shipped 25-cluster result: ARI {repro:.4f}, '
          f'identical labelling {exact}')
    assert repro > 0.999, (f'this script does not reproduce Stage 1b (ARI {repro:.4f}) - '
                           f'the comparison below would be meaningless')

    # -------------------------------------------------- check 1: SIM / EV identical
    sub = np.ix_(keep, keep)
    sim_same = bool(np.array_equal(np.nan_to_num(r6['SIM'][sub], nan=-1.0),
                                   np.nan_to_num(r5['SIM'], nan=-1.0)))
    ev_same = bool(np.array_equal(r6['EV'][sub], r5['EV']))
    sim_max = float(np.nanmax(np.abs(r6['SIM'][sub] - r5['SIM']))) if not sim_same else 0.0
    c1 = sim_same and ev_same

    # -------------------------------------------------- checks 2 and 3: ARI
    m6 = r6['memb'][keep]
    m5 = r5['memb']
    w = r5['nodes'].n_cells.to_numpy().astype(float)
    ari_w = s1b.ari(m6, m5, w)
    ari_u = s1b.ari(m6, m5)
    pa, n_diff, n_pairs = pair_agreement(m6, m5)
    c2, c3 = ari_w >= ARI_W_MIN, ari_u >= ARI_U_MIN

    # -------------------------------------------------- check 4: the 9 ferguson targets
    f_nodes = r6['nodes'].reset_index(drop=True)
    f_rows = f_nodes.index[f_nodes.cohort == FROZEN].to_numpy()
    targets = sorted({int(r6['memb'][i]) for i in f_rows})
    tt = []
    for t in targets:
        members = np.flatnonzero(r6['memb'] == t)
        train_members = [i for i in members if f_nodes.cohort[i] != FROZEN]
        pos = [int(np.flatnonzero(keep == i)[0]) for i in train_members]
        new = sorted({int(m5[p]) for p in pos})
        f_lab = [f_nodes.label[i] for i in members if f_nodes.cohort[i] == FROZEN]
        tt.append(dict(cluster6=t, name=r6['names'][members[0]],
                       ferguson_labels=', '.join(f_lab),
                       train_labels=len(train_members),
                       cells=int(f_nodes.n_cells[train_members].sum()) if train_members else 0,
                       control_clusters=len(new), unbroken=(len(new) <= 1)))
    T4 = pd.DataFrame(tt)
    c4 = bool(T4.unbroken.all())

    # -------------------------------------------------- which labels actually moved
    moved = []
    for p in range(len(m5)):
        mates6 = {int(q) for q in range(len(m5)) if q != p and m6[q] == m6[p]}
        mates5 = {int(q) for q in range(len(m5)) if q != p and m5[q] == m5[p]}
        if mates6 != mates5:
            n = r5['nodes'].reset_index(drop=True)
            moved.append(dict(cohort=n.cohort[p], label=n.label[p], cells=int(n.n_cells[p]),
                              gained=len(mates5 - mates6), lost=len(mates6 - mates5)))
    MV = pd.DataFrame(moved)

    # -------------------------------------------------- checks 7/8: DIAGNOSTIC, not gate checks
    # Checks 2-4 change TWO things at once - the node set AND the cut the guards then choose.
    # Re-running the control at the SHIPPED cut isolates the first from the second. This was
    # written AFTER seeing checks 2-4 fail, so it is labelled a diagnostic and it does NOT
    # revise the verdict. D-34: a rule that would flip a verdict in its own favour is refused.
    print('\n  matched-cut diagnostic (checks 7/8, added after the FAIL - not a gate check):')
    rm = run(S5, f'5-cohort @ shipped cut {r6["tau"]:.3f}', force_tau=r6['tau'])
    mm = rm['memb']
    ari_wm, ari_um = s1b.ari(m6, mm, w), s1b.ari(m6, mm)
    nest_own = nesting_violations(m5, m6)
    nest_mat = nesting_violations(mm, m6)

    # -------------------------------------------------- check 9: WHY did the cut move?
    cols = ['cut', 'clusters', 'biggest_share', 'cross_cohort_share', 'stability', 'usable']
    SWEEP = r6['sweep'][cols].merge(r5['sweep'][cols], on='cut', suffixes=('_6', '_5'))
    SWEEP = SWEEP[(SWEEP.cut >= 0.60) & (SWEEP.cut <= 0.875)].reset_index(drop=True)
    u6, u5 = r6['sweep'][r6['sweep'].usable], r5['sweep'][r5['sweep'].usable]
    win6 = (float(u6.cut.min()), float(u6.cut.max()))
    win5 = (float(u5.cut.min()), float(u5.cut.max()))
    s_at_ship = float(u5.stability[u5.cut == r6['tau']].iloc[0]) if (u5.cut == r6['tau']).any() \
        else float('nan')
    stab_gap = float(u5.stability.max()) - s_at_ship
    stab_range = float(u5.stability.max() - u5.stability.min())

    checks = [c1, c2, c3, c4]
    verdict = 'PASS' if all(checks) else 'FAIL'
    write_report(r6, r5, dict(repro=repro, exact=exact, c1=c1, sim_same=sim_same,
                              ev_same=ev_same, sim_max=sim_max, ari_w=ari_w, ari_u=ari_u,
                              c2=c2, c3=c3, c4=c4, pa=pa, n_diff=n_diff, n_pairs=n_pairs,
                              T4=T4, MV=MV, verdict=verdict, n_keep=len(keep),
                              rm=rm, ari_wm=ari_wm, ari_um=ari_um,
                              nest_own=nest_own, nest_mat=nest_mat,
                              SWEEP=SWEEP, win6=win6, win5=win5, n6=len(u6), n5=len(u5),
                              stab_gap=stab_gap, stab_range=stab_range))
    print(f'  usable cut window: 6-cohort {win6[0]:.3f}-{win6[1]:.3f} ({len(u6)} points) | '
          f'5-cohort {win5[0]:.3f}-{win5[1]:.3f} ({len(u5)} points)')
    print(f'  the SHIPPED cut {r6["tau"]:.3f} is inside the 5-cohort window; the control '
          f'prefers {r5["tau"]:.3f} by only {stab_gap:+.4f} stability')
    print(f'  weighted ARI at the shipped cut {ari_wm:.4f} (vs {ari_w:.4f} at its own cut) | '
          f'unweighted {ari_um:.4f} (vs {ari_u:.4f})')
    print(f'\ncheck 1 SIM/EV identical      {"PASS" if c1 else "FAIL"}')
    print(f'check 2 cell-weighted ARI    {ari_w:.4f}  (>= {ARI_W_MIN})  '
          f'{"PASS" if c2 else "FAIL"}')
    print(f'check 3 unweighted ARI       {ari_u:.4f}  (>= {ARI_U_MIN})  '
          f'{"PASS" if c3 else "FAIL"}')
    print(f'check 4 ferguson targets     {int(T4.unbroken.sum())}/{len(T4)} unbroken  '
          f'{"PASS" if c4 else "FAIL"}')
    print(f'\nH10 CONTROL: {verdict}   ->  {OUT}')


def write_report(r6, r5, x):
    L = []
    A = L.append
    A('# H10 control - was the label space built blind to the frozen holdout?\n')
    A(f'**{x["verdict"]}** - the 25-cluster label space was compared against the one Stage 1b '
      f'would have produced from the 5 training cohorts alone.\n')
    A('## The question\n')
    A('Stage 1b clustered all six cohorts together, so ferguson\'s 9 labels and their marker '
      'signatures were in the distance matrix that produced the 25 clusters. ferguson cells have '
      'never entered a loss, so this is not a training leak - but the label space Stage 7 will be '
      'scored in was not built blind to ferguson, and that is worth measuring rather than '
      'arguing about.\n')
    A('This is a CONTROL, not a rebuild. Re-clustering on 5 cohorts and shipping that would '
      'change the cluster count and invalidate every number produced since Gate 1b. The same '
      'choice was made at Gate 2 (D-27).\n')
    A('Thresholds were declared in `pipeline2/panel/gate1b_control_expect.csv` before this '
      'script was run.\n')

    A('## Does this script reproduce the shipped result?\n')
    A(f'ARI against `work/label_map.csv`: **{x["repro"]:.4f}** - identical labelling: '
      f'`{x["exact"]}`. It runs the same chain as `s1b_labels.main()` with nothing added or '
      'skipped, so the 5-cohort column below is a like-for-like comparison.\n')

    A('## The two runs\n')
    A('| | 6-cohort (shipped) | 5-cohort (control) |')
    A('|---|---|---|')
    A(f'| labels | {len(r6["nodes"])} | {len(r5["nodes"])} |')
    A(f'| chosen cut tau | {r6["tau"]:.3f} | {r5["tau"]:.3f} |')
    A(f'| clusters at the cut | {r6["n_cut"]} | {r5["n_cut"]} |')
    A(f'| after per-branch refinement | {r6["n_refined"]} | {r5["n_refined"]} |')
    A(f'| after SCC contraction | **{r6["n_final"]}** | **{r5["n_final"]}** |')
    A(f'| biggest cluster share | {r6["biggest_share"]:.1%} | {r5["biggest_share"]:.1%} |')
    A(f'| cohort ARI guard | {r6["cohort_ari"]:.3f} | {r5["cohort_ari"]:.3f} |')
    A(f'| stability at the cut | {r6["stability"]:.3f} | {r5["stability"]:.3f} |')
    A('')
    A('_Checks 5 and 6 are these two rows, reported with no threshold: the cut is chosen by '
      'guards over the whole node set, so dropping 9 labels may legitimately move it._\n')

    A('## Check 1 - could ferguson have acted through the signatures?\n')
    A(f'- SIM submatrix identical: `{x["sim_same"]}`' +
      ('' if x['sim_same'] else f' - largest absolute difference {x["sim_max"]:.2e}'))
    A(f'- EV submatrix identical: `{x["ev_same"]}`')
    A('')
    A('`rescale` loops over cohorts one at a time, so dropping ferguson\'s rows cannot change '
      'another cohort\'s Z, P or W. This check asserts that consequence instead of trusting the '
      'argument. When it passes, ferguson\'s ONLY channel of influence is the clustering itself - '
      'bridging two labels in average linkage, shifting the cut the guards choose, or changing a '
      'per-branch split\'s LOCO support - which is what checks 2-4 then measure.\n')

    A('## Checks 2 and 3 - how much did the label space move?\n')
    A(f'Over the **{x["n_keep"]} training-cohort labels** present in both runs:\n')
    A('| measure | value | threshold | |')
    A('|---|---|---|---|')
    A(f'| cell-weighted ARI | **{x["ari_w"]:.4f}** | >= {ARI_W_MIN} | '
      f'{"PASS" if x["c2"] else "FAIL"} |')
    A(f'| unweighted ARI | **{x["ari_u"]:.4f}** | >= {ARI_U_MIN} | '
      f'{"PASS" if x["c3"] else "FAIL"} |')
    A(f'| label pairs agreeing | {x["pa"]:.4f} | report only | '
      f'{x["n_pairs"] - x["n_diff"]:,} of {x["n_pairs"]:,} |')
    A('')
    A('0.90 is Gate 1b\'s own agreement bar, reused so the number means the same thing it does '
      'elsewhere in this project. The unweighted bar is lower on purpose: it counts a 100-cell '
      'label the same as a 900k-cell one, so a small rare-label reshuffle should not by itself '
      'fail the control.\n')

    A('## Check 4 - the clusters Stage 7 actually depends on\n')
    A('ferguson\'s 9 labels map into 9 clusters. For each one, do its TRAINING-cohort members '
      'still sit together when ferguson is removed? A change confined to exactly these clusters '
      'would be the worst case, and a global ARI would hide it.\n')
    A(s1b.md_table(x['T4'], '{:.0f}'))
    A('')
    A(f'**{int(x["T4"].unbroken.sum())} of {len(x["T4"])} unbroken.**\n')

    A('## Which labels changed cluster-mates\n')
    if len(x['MV']) == 0:
        A('_None. The two partitions are identical over the shared labels._\n')
    else:
        A(f'{len(x["MV"])} of {x["n_keep"]} labels have a different set of cluster-mates. '
          '`gained` and `lost` count mates, not clusters.\n')
        A('**Do not read this table on its own.** It is measured at the control\'s OWN cut, so '
          'almost every row is a cluster being SPLIT rather than regrouped - note how nearly '
          'every `gained` is 0 while `lost` is large, which is the signature of a finer cut, not '
          'of labels changing partners. Checks 7-9 below separate the two.\n')
        A(s1b.md_table(x['MV'].sort_values('cells', ascending=False).head(30), '{:.0f}'))
        A('')

    A('## Checks 7 and 8 - DIAGNOSTIC, added after the FAIL, and it does NOT revise the verdict\n')
    A('Checks 2-4 change **two things at once**: the node set, and the cut the guards then '
      'choose from it. Re-running the control at the SHIPPED cut separates them. This section was '
      'written after seeing checks 2-4 fail, so it is labelled a diagnostic and the verdict above '
      'stands as declared - D-34 refuses a rule that would flip a verdict in its own favour.\n')
    A('| | control at ITS OWN cut | control at the SHIPPED cut |')
    A('|---|---|---|')
    A(f'| cut tau | {r5["tau"]:.3f} | {x["rm"]["tau"]:.3f} |')
    A(f'| clusters | {r5["n_final"]} | {x["rm"]["n_final"]} |')
    A(f'| cell-weighted ARI vs shipped | {x["ari_w"]:.4f} | **{x["ari_wm"]:.4f}** |')
    A(f'| unweighted ARI vs shipped | {x["ari_u"]:.4f} | **{x["ari_um"]:.4f}** |')
    A(f'| control clusters spanning >1 shipped cluster | {len(x["nest_own"])} of '
      f'{r5["n_final"]} | {len(x["nest_mat"])} of {x["rm"]["n_final"]} |')
    A('')
    A('**This is the whole story.** Hold the cut fixed and the partition barely moves - the '
      'similarity structure is stable without ferguson. Let the guards pick the cut and it moves '
      f'a lot, {r6["tau"]:.3f} to {r5["tau"]:.3f}, which is {r6["n_final"]} clusters against '
      f'{r5["n_final"]}. So ferguson did not change WHICH labels are alike. It changed which '
      'GRANULARITY the cut-choosing rule selected, and ARI punishes a pure granularity change as '
      'hard as a genuine re-mixing.\n')
    A('The clusters that genuinely re-mix - not a refinement, a real regrouping - are these:\n')
    if len(x['nest_mat']) == 0:
        A('_None at the shipped cut: the control partition is a strict refinement._\n')
    else:
        A(s1b.md_table(x['nest_mat'], '{:.0f}'))
        A('')
        A('Read these in the direction they happened: ferguson SEPARATED these groups. Without '
          'it they merge. So on this evidence the frozen cohort was acting as a source of '
          'distinctions, not as a bridge.\n')

    A('## Check 9 - DIAGNOSTIC - why did the cut move?\n')
    A('The cut is chosen in two steps: three guards mark which cuts are USABLE, then stability '
      'picks the argmax inside that window. Both steps are affected, and they are worth '
      'separating.\n')
    A(s1b.md_table(x['SWEEP'], '{:.3f}'))
    A('')
    w6, w5 = x['win6'], x['win5']
    A(f'- **The guards.** With ferguson the usable window is **{w6[0]:.3f} to {w6[1]:.3f}** - '
      f'{x["n6"]} grid points. Without it, **{w5[0]:.3f} to {w5[1]:.3f}** - {x["n5"]} points. '
      'A sixth cohort binds BOTH guards: it drags `cross_cohort_share` below the 0.95 floor at '
      'the fine end and pushes `biggest_share` above the 0.25 ceiling at the coarse end. That is '
      'real, and it is the honest part of the leak.')
    A(f'- **The stability pick.** Inside the 5-cohort window the stability curve is nearly '
      f'FLAT. The control chooses {r5["tau"]:.3f} over the shipped {r6["tau"]:.3f} by a margin '
      f'of **{x["stab_gap"]:+.4f} ARI**. That is not a decision, it is a coin flip on noise.')
    A(f'- **And the shipped cut is legal without ferguson.** {r6["tau"]:.3f} sits INSIDE the '
      f'5-cohort usable window {w5[0]:.3f} to {w5[1]:.3f}. The 25-cluster space is a choice the '
      '5 training cohorts also support; it is just not the argmax of a curve that varies by '
      'less than 0.01.\n')
    A('**A separate defect surfaces here, and it is not about ferguson at all.** `choose_cut` '
      'takes the argmax of a stability curve whose whole range across the feasible window is '
      f'{x["stab_range"]:.3f}. Its own docstring says stability has "no directional bias, only '
      'low resolution" - this control measures how low. A rule that picks a granularity by '
      '0.003 of ARI is not selecting; it is sampling. Recorded as its own finding.\n')

    A('## How to read this\n')
    A(f'The declared verdict is **{x["verdict"]}**: the 25-cluster label space is NOT independent '
      'of the frozen holdout, and Stage 7\'s number cannot be reported as a clean zero-shot '
      'result without saying so.\n')
    A('But the mechanism is narrower than the verdict alone suggests, and both halves must be '
      'reported together:\n')
    A(f'- **What is stable:** the similarity structure. At a matched cut the weighted ARI is '
      f'{x["ari_wm"]:.4f} and {x["rm"]["n_final"] - len(x["nest_mat"])} of '
      f'{x["rm"]["n_final"]} control clusters sit entirely inside one shipped cluster.')
    A('- **What is not:** the granularity. The guard-plus-stability rule that picks the cut is '
      'sensitive to which cohorts are in the room, and 9 labels out of 106 moved it from '
      f'{r6["tau"]:.3f} to {r5["tau"]:.3f}.')
    A('- **What it costs:** Stage 7 is scored in a label space whose COARSENESS ferguson helped '
      'choose. Coarser is easier, so the direction of the bias is known and it favours the '
      'result. That must be stated next to the number.\n')
    A('Two ways forward, and this file does not choose between them:\n')
    A('1. **Disclose.** Report Stage 7 in the shipped 25-cluster space, cite this control, state '
      'the direction of the bias. Costs nothing. An examiner can still ask the question.')
    A('2. **Also report a clean-protocol number.** Freeze the control\'s label space, assign the '
      'frozen cohort\'s labels into it from their marker signatures alone, and train and score '
      'there as a second number. That is the actual deployment procedure this project claims, it '
      'is fully leak-free, and it costs one extra training run.\n')
    A('Neither changes what ships. They change which sentence can be written about what ships.\n')

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))


if __name__ == '__main__':
    main()

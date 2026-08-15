"""Stage 7 label spaces - build the CLEAN ones, the shipped one is read as-is.

    python pipeline2/s7_spaces.py --build      # write the B1/B2 spaces + their prototypes
    python pipeline2/s7_spaces.py              # print what exists, build nothing

WHY THIS FILE EXISTS. The H10 control (D-46) measured that the shipped 25-cluster label space is
not independent of the frozen holdout: ferguson was in the room when Stage 1b chose the
granularity, and coarser is easier, so the bias favours the result. The user's decision was to
report BOTH numbers - the shipped one, disclosed, and a second one produced by the protocol this
project actually claims. This file builds the second one.

THE CLEAN PROTOCOL, stated before any of it was run:

  1. Cluster the 5 TRAINING cohorts alone. ferguson contributes nothing - not a node, not a
     signature, not a vote on the cut. This is exactly `s1b_control.run(S5)`, reused rather than
     rewritten so the two files cannot drift apart.
  2. FREEZE that partition.
  3. Assign ferguson's 9 native labels into the frozen clusters from their MARKER SIGNATURES
     alone. The rule is the clustering rule: a label joins the cluster whose members are the
     closest on average, admitted only if that average distance is within the same cut `tau` the
     partition was built at. This is precisely what average linkage would have done if the label
     had arrived last, which is the point - a new cohort arriving later must be handled by the
     same rule, not a new one.
  4. A label that no cluster admits is NOT forced anywhere. It is marked NOVEL and reported. That
     is a real answer, and on a genuinely unseen cohort it is the answer that should sometimes
     come back.

  Nothing in steps 1-3 lets ferguson move a cluster boundary. That is the whole difference from
  the shipped space.

TWO CLEAN SPACES, NOT ONE, and the second is the more informative:

  B1  tau = the 5-cohort rule's own pick (0.650, 37 clusters). What the declared method chooses
      when the holdout is absent.
  B2  tau = the SHIPPED cut (0.800, 22 clusters). Same cohorts as B1, same cut as A. Holding the
      cut fixed is what separates "ferguson changed the label space" from "ferguson changed the
      granularity" - the H10 control showed the second is the real effect (matched-cut ARI
      0.9828), and B2 is the row that carries that into the final number.

  D-47 is the reason B2 is not optional: the 5-cohort stability curve is flat to within 0.0035
  across the feasible window, so B1's cut is a coin flip among legal options and a single clean
  number resting on it would be resting on noise.

CARRY-OVER OF THE STROMA WAIVER (D-23/D-32), declared here because it is a judgement call. The
`unreliable` flag lives on LABELS in label_map.csv, not on clusters, so it survives re-clustering
unchanged. A NEW cluster is flagged unreliable when the MAJORITY OF ITS CELLS come from flagged
labels. Majority-of-cells rather than any-member: a 3-label cluster with one small flagged member
is not thereby unreliable, and "any" would spread the waiver over most of the space at the finer
B1 cut.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s1b_labels as s1b                                             # noqa: E402
import s1b_control as ctl                                            # noqa: E402
from config import WORK                                              # noqa: E402

FROZEN = ctl.FROZEN
TRAIN = ctl.TRAIN
SPACES = {'B1': None, 'B2': 0.800}          # None = let the 5-cohort rule choose its own cut


def paths(tag):
    return (os.path.join(WORK, f'label_map_{tag}.csv'),
            os.path.join(WORK, f'prototypes_{tag}.npy'))


def assign_frozen(S6, keep, memb5, tau, SIM, EV):
    """Place the holdout's labels into a FROZEN partition, from marker signatures alone.

    Returns (cluster_of_frozen_row, avg_distance, admitted). `cluster_of_frozen_row` is -1 for a
    label no cluster admits - marked NOVEL, never forced into the nearest bin.
    """
    nodes = S6['nodes'].reset_index(drop=True)
    f_rows = np.flatnonzero((nodes.cohort == FROZEN).to_numpy())
    D = s1b.distance(np.arange(len(nodes)), SIM, EV)      # FAR where evidence is below the floor
    out, dist, adm = [], [], []
    for r in f_rows:
        best_c, best_d = -1, np.inf
        for c in range(int(memb5.max()) + 1):
            members = keep[memb5 == c]                    # rows of the 6-cohort node table
            d = float(np.mean(D[r, members]))
            if d < best_d:
                best_c, best_d = c, d
        ok = bool(np.isfinite(best_d) and best_d <= tau and best_d < s1b.FAR)
        out.append(best_c if ok else -1)
        dist.append(best_d)
        adm.append(ok)
    return np.array(out), np.array(dist), np.array(adm), f_rows


def build(tag, force_tau):
    S6 = s1b.load_signatures()
    S5, keep = ctl.subset(S6, TRAIN)

    # ---------------------------------------------------------------- 1+2: cluster and freeze
    r5 = ctl.run(S5, f'clean {tag}', force_tau=force_tau)
    memb5, tau = r5['memb'], r5['tau']
    n_cl = int(memb5.max()) + 1

    # SIM/EV from the 6-cohort build. The H10 control proved (check 1) that its training-cohort
    # block is BIT-IDENTICAL to the 5-cohort build's, so reusing it introduces nothing - and the
    # holdout-to-training block, which is what the assignment needs, only exists here.
    Z, P, Wm = s1b.rescale(S6)
    SIM, C, EV, CX = s1b.containment(S6, (Z, P, Wm))

    # ---------------------------------------------------------------- 3+4: assign the holdout
    f_cl, f_d, f_ok, f_rows = assign_frozen(S6, keep, memb5, tau, SIM, EV)

    # ---------------------------------------------------------------- names and prototypes
    # Prototypes are the 5-cohort centroids: the holdout contributes NOTHING to them, which is
    # the entire point. names/cen come from the same call Stage 1b uses (s1b_labels.py:1213).
    Z5, P5, W5 = s1b.rescale(S5)
    ncoh = np.array([S5['nodes'].cohort[np.isfinite(P5[:, t])].nunique()
                     for t in range(P5.shape[1])])
    names, cen, _ = s1b.name_clusters(S5, memb5, P5, ncoh)

    # ---------------------------------------------------------------- the waiver carry-over
    shipped = pd.read_csv(os.path.join(WORK, 'label_map.csv'), keep_default_na=False)
    flag = {(r.cohort, r.label): int(r.unreliable) for r in shipped.itertuples()}
    reason = {(r.cohort, r.label): r.unreliable_reason for r in shipped.itertuples()}
    n5 = S5['nodes'].reset_index(drop=True)
    unrel = {}
    for c in range(n_cl):
        w = np.flatnonzero(memb5 == c)
        cells = n5.n_cells.to_numpy()[w].astype(float)
        bad = np.array([flag.get((n5.cohort[i], n5.label[i]), 0) for i in w], float)
        unrel[c] = int((bad * cells).sum() > 0.5 * cells.sum())

    # ---------------------------------------------------------------- write the label map
    rows = []
    for i in range(len(n5)):
        c = int(memb5[i])
        rows.append(dict(cohort=n5.cohort[i], label=n5.label[i], prev=n5.prev[i],
                         n_cells=int(n5.n_cells[i]), cluster=c, cluster_name=names[c],
                         unreliable=unrel[c],
                         unreliable_reason=reason.get((n5.cohort[i], n5.label[i]), '')))
    nodes6 = S6['nodes'].reset_index(drop=True)
    for j, r in enumerate(f_rows):
        c = int(f_cl[j])
        rows.append(dict(cohort=FROZEN, label=nodes6.label[r], prev=nodes6.prev[r],
                         n_cells=int(nodes6.n_cells[r]), cluster=c,
                         cluster_name=(names[c] if c >= 0 else 'NOVEL - no cluster admits it'),
                         unreliable=(unrel[c] if c >= 0 else 1),
                         unreliable_reason=('' if c >= 0 else
                                            f'unassigned: nearest cluster at {f_d[j]:.3f} > '
                                            f'tau {tau:.3f}')))
    out = pd.DataFrame(rows)
    lm_path, pt_path = paths(tag)
    out.to_csv(lm_path, index=False)
    np.save(pt_path, cen)

    # ---------------------------------------------------------------- what was decided
    A = pd.DataFrame(dict(
        label=[nodes6.label[r] for r in f_rows],
        n_cells=[int(nodes6.n_cells[r]) for r in f_rows],
        avg_dist=np.round(f_d, 4), tau=round(tau, 3), admitted=f_ok,
        cluster=f_cl,
        cluster_name=[names[c] if c >= 0 else 'NOVEL' for c in f_cl],
        shipped_cluster=[int(shipped[(shipped.cohort == FROZEN) &
                                     (shipped.label == nodes6.label[r])].cluster.iloc[0])
                         for r in f_rows]))
    print(f'\n  [{tag}] tau {tau:.3f} | {n_cl} clusters | '
          f'{int(f_ok.sum())}/{len(f_ok)} holdout labels admitted | '
          f'{sum(unrel.values())} clusters flagged unreliable')
    print(A.to_string(index=False))
    print(f'  wrote {os.path.basename(lm_path)} ({len(out)} rows) and '
          f'{os.path.basename(pt_path)} {cen.shape}')
    return dict(tag=tag, tau=tau, n_cl=n_cl, assign=A, unreliable=unrel,
                n_admitted=int(f_ok.sum()), n_frozen=len(f_ok), proto_shape=cen.shape)


def status():
    print('label spaces for Stage 7:\n')
    lm = pd.read_csv(os.path.join(WORK, 'label_map.csv'), keep_default_na=False)
    print(f'  A  (shipped)  work/label_map.csv          {lm.cluster.nunique()} clusters, '
          f'{len(lm)} labels, {lm.cohort.nunique()} cohorts  '
          f'-- NOT blind to {FROZEN} (D-46)')
    for tag in SPACES:
        p, q = paths(tag)
        if os.path.exists(p):
            d = pd.read_csv(p, keep_default_na=False)
            nov = int((d.cluster < 0).sum())
            print(f'  {tag} (clean)    work/label_map_{tag}.csv       '
                  f'{d[d.cluster >= 0].cluster.nunique()} clusters, {len(d)} labels'
                  + (f', {nov} NOVEL' if nov else ''))
        else:
            print(f'  {tag} (clean)    NOT BUILT - run with --build')


def main():
    if '--build' not in sys.argv:
        status()
        return
    res = [build(tag, force_tau) for tag, force_tau in SPACES.items()]
    print()
    status()
    return res


if __name__ == '__main__':
    main()

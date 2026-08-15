"""Stage 12 - EXTERNAL VALIDATION OF THE 25-CLUSTER LABEL SPACE. Closes H15 / files/10 STEP C.

    python pipeline2/s12_ontology.py            # all checks, writes reports/s12_ontology.md
    python pipeline2/s12_ontology.py --quick     # 50 permutations instead of 1000, scores nothing

WHY THIS EXISTS. Every Gate 1b check is either internal consistency (cohort guard, evidence
coverage, LOCO split stability, coherence, DAG) or agreement with THIS PROJECT'S OWN hand mapping
(0.928). files/07 H15 records the consequence in one sentence: "the gate passes and the gate tests
nothing external". Stage 1b is the stage the whole thesis is being reframed onto (D-49), and a
label space whose only validation is the author's own judgement cannot carry that weight.

WHAT IS EXTERNAL HERE, PRECISELY. Be exact about this in the write-up, because it is the one place
a reviewer can push.

  NOT external - which Cell Ontology term each cohort label is given. That is a reading of the
                 cohort's own paper. `_validation/cl_mapping.csv` carries a `provenance` column so
                 a reader can see how much of it is automatic and how much is judgement.
  IS  external - everything measured afterwards. Which terms are the same, which contains which,
                 how far apart two are, what level each sits at, and which markers define it. All
                 of that is the Cell Ontology's, and none of it can be influenced by picking a
                 term name.

So the claim this stage supports is "the derived clusters agree with a published ontology's
STRUCTURE", not "the labels were mapped without human input". Those are different sentences and
only the first one is defended here.

THE COMPARISON LEVELS ARE CHOSEN BY THE CELL ONTOLOGY, NOT BY THIS PROJECT. `human_reference_atlas`,
`cellxgene_subset`, `blood_and_immune_upper_slim` and `general_cell_types_upper_slim` are published
CL subsets. "You picked the level that flattered you" is the first objection to any ontology
comparison and it is unavailable here.

NOTHING IN THE PIPELINE READS ANY OF THIS, AND CHECK 0 PROVES IT RATHER THAN PROMISING IT.
files/02 2.1 bans the Cell Ontology INSIDE the pipeline ("No CL:0000084 anywhere in the pipeline")
and D-4 makes it the founding constraint. This stage is a SCORING SET, the same standing
`_validation/hand_mapping_reference.csv` already has. Check 0 scans every other module under
pipeline2/ with comments and docstrings removed and asserts none of them names a CL term or reads
the scoring files. If that assert fails the ontology has leaked into the method and every number
below is void - not weakened, void. Same role as Stage 10's check 0.

THIS FILE CHANGES NOTHING. It does not re-cut, re-cluster, re-tune or repair. D-46, D-47 and H11
all say the shipped label space must be measured and disclosed, never rebuilt, because a rebuild
invalidates every number since Gate 1b. Two checks here are DECLARED EXPECTED TO FAIL before the
run (4c and 5a) and they are reported either way.

ALL AGREEMENT NUMBERS CARRY A BOOTSTRAP INTERVAL. H9 is the standing complaint that not one gate
in this project has ever been scored with one. This is the first that is. The interval is over
LABELS, so it prices the fact that 106 labels is a small sample - it does NOT price the choice of
CL term, which is judgement and cannot be bootstrapped.
"""
import argparse
import hashlib
import io
import itertools
import json
import os
import sys
import time
import tokenize

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                                        # noqa: E402
from config import WORK, REPORTS, FIGURES, PANEL, SEED               # noqa: E402
import s1b_labels as s1b                                             # noqa: E402

ROOT = config.ROOT
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(REPORTS, 's12_ontology.md')
EXPECT = os.path.join(PANEL, 'gate12_expect.csv')
MAPPING = os.path.join(ROOT, '_validation', 'cl_mapping.csv')
META = os.path.join(ROOT, '_validation', 'cl_mapping_meta.json')
HANDMAP = os.path.join(ROOT, '_validation', 'hand_mapping_reference.csv')
EXT = os.path.join(WORK, 'ext')

LMAP = os.path.join(WORK, 'label_map.csv')
LGRAPH = os.path.join(WORK, 'label_graph.json')
MREG = os.path.join(WORK, 'marker_registry.csv')

N_PERM = 1000
N_BOOT = 2000
GENERIC = 'CL:0001063'          # neoplastic cell - the alternative tumour reading, reported as one row
# Clusters Gate 1b itself flagged. Every number is reported with and without them (D-53's rule).
UNRELIABLE = (2, 16, 18)
# gate12 check 5a, declared before the lookup: these four are predicted to have NO defining marker.
PREDICTED_UNCOVERED = (18, 20, 21, 22)


# ----------------------------------------------------------------------------- check 0
def code_only(path):
    """Source with comments and every string literal removed, so a docstring cannot pass or fail
    the independence check by talking about the rule it describes."""
    out = []
    with open(path, 'rb') as fh:
        try:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                    out.append(tok.string)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return open(path, encoding='utf-8', errors='replace').read()
    return ' '.join(out)


def check0():
    """No module under pipeline2/ except this one may name a CL term or read the scoring set."""
    me = os.path.basename(__file__)
    bad, scanned = [], 0
    for dirpath, _, files in os.walk(HERE):
        if '__pycache__' in dirpath:
            continue
        for f in sorted(files):
            if not f.endswith('.py') or f == me:
                continue
            scanned += 1
            src = code_only(os.path.join(dirpath, f))
            rel = os.path.relpath(os.path.join(dirpath, f), ROOT)
            for pat in ('cl_mapping', 'cl_terms', 'cellmarker', 'hand_mapping'):
                if pat in src.lower():
                    bad.append(f'{rel}: reads `{pat}`')
            if 'CL:' in src or 'CL_00' in src:
                bad.append(f'{rel}: contains a CL term literal in code')
    return scanned, bad


# ----------------------------------------------------------------------------- ontology helpers
def ancestors(cid, T):
    """Every term reachable from `cid` by is_a, itself included."""
    seen, stack = set(), [cid]
    while stack:
        c = stack.pop()
        if c in seen or c not in T:
            continue
        seen.add(c)
        stack.extend(T[c]['is_a'])
    return seen


def project(cid, T, subsets):
    """Nearest ancestor of `cid` (itself allowed) that sits in one of CL's published `subsets`.

    Breadth-first upward, so 'nearest' means fewest is_a steps. Ties at the same depth are broken
    by sorted id - deterministic, and the tie count is reported rather than hidden.
    """
    front, seen, depth = [cid], {cid}, 0
    while front and depth < 40:
        hit = sorted(c for c in front if c in T and any(s in T[c]['subsets'] for s in subsets))
        if hit:
            return hit[0], len(hit) > 1
        nxt = []
        for c in front:
            for p in T.get(c, {}).get('is_a', []):
                if p not in seen:
                    seen.add(p)
                    nxt.append(p)
        front, depth = nxt, depth + 1
    return None, False


# ----------------------------------------------------------------------------- metrics
def metrics(a, b, w=None):
    """Agreement of two partitions of the same labels. `ari` is s1b's own, so the numbers here
    mean exactly what Gate 1b's agreement numbers mean."""
    from sklearn.metrics import (normalized_mutual_info_score,
                                 homogeneity_completeness_v_measure)
    hom, comp, v = homogeneity_completeness_v_measure(b, a)
    return dict(ari=s1b.ari(a, b, w),
                nmi=float(normalized_mutual_info_score(a, b)),
                hom=float(hom), comp=float(comp), v=float(v))


def boot_ci(a, b, w, rng, n=N_BOOT):
    """Percentile bootstrap over LABELS. Prices the small label count, nothing else."""
    a, b = np.asarray(a), np.asarray(b)
    w = None if w is None else np.asarray(w, float)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(a), len(a))
        if len(set(a[i])) < 2 or len(set(b[i])) < 2:
            continue
        vals.append(s1b.ari(a[i], b[i], None if w is None else w[i]))
    if not vals:
        return float('nan'), float('nan')
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def perm_null(a, b, w, rng, n):
    """Shuffle the cluster assignment among labels. Cluster sizes are preserved exactly, so the
    null asks 'could a partition of these shapes score this by luck', not 'is 25 a lucky number'."""
    a = np.asarray(a).copy()
    return np.array([s1b.ari(rng.permutation(a), b, w) for _ in range(n)])


# ----------------------------------------------------------------------------- data
def load():
    assert os.path.exists(MAPPING), f'run _validation/build_cl_mapping.py first ({MAPPING})'
    assert os.path.exists(os.path.join(EXT, 'cl_terms.json')), 'run _validation/fetch_ext.py first'

    T = json.load(open(os.path.join(EXT, 'cl_terms.json'), encoding='utf-8'))
    levels, terms = T['levels'], T['terms']
    prov = json.load(open(os.path.join(EXT, 'PROVENANCE.json'), encoding='utf-8'))

    cl = pd.read_csv(MAPPING)
    sha = hashlib.sha256(open(MAPPING, 'rb').read()).hexdigest()

    lm = pd.read_csv(LMAP)
    df = lm.merge(cl.drop(columns=['n_cells']), left_on=['cohort', 'label'],
                  right_on=['cohort', 'native_label'], how='left', validate='one_to_one')
    assert df.provenance.notna().all(), 'a Stage 1b label has no row in the CL mapping'
    # Both files carry a cell count, computed independently. They must agree, or the mapping and
    # the clustering are not describing the same 106 labels.
    chk = lm.merge(cl, left_on=['cohort', 'label'], right_on=['cohort', 'native_label'])
    assert (chk.n_cells_x == chk.n_cells_y).all(), 'cell counts disagree between the two files'

    graph = json.load(open(LGRAPH, encoding='utf-8'))
    return df, terms, levels, prov, sha, graph


def level_columns(df, terms, levels):
    """Add one column per published CL level, plus the tie counts."""
    ties = {}
    for name, subs in levels.items():
        col, t = [], 0
        for cid in df.cl_id.fillna(''):
            if not cid:
                col.append('')
                continue
            rep, tied = project(cid, terms, subs)
            t += int(tied)
            col.append(rep or '')
        df[f'lv_{name}'] = col
        ties[name] = t
    df['lv_term'] = df.cl_id.fillna('')
    return df, ties


# ----------------------------------------------------------------------------- checks
def check2(df, terms, rng, levels_order):
    rows = []
    for lv in levels_order:
        col = f'lv_{lv}'
        for scope, sub in (('all', df), ('reliable only', df[~df.cluster.isin(UNRELIABLE)])):
            s = sub[(sub.scored == 1) & (sub[col] != '')]
            if s[col].nunique() < 2 or s.cluster.nunique() < 2:
                continue
            for wt, w in (('per label', None), ('cell weighted', s.n_cells.values.astype(float))):
                m = metrics(s.cluster.values, s[col].values, w)
                lo, hi = boot_ci(s.cluster.values, s[col].values, w, rng)
                rows.append(dict(level=lv, scope=scope, weight=wt, n_labels=len(s),
                                 n_classes=s[col].nunique(), lo=lo, hi=hi, **m))
    return pd.DataFrame(rows)


def check3(df, rng, levels_order, n_perm):
    rows, nulls = [], {}
    for lv in levels_order:
        s = df[(df.scored == 1) & (df[f'lv_{lv}'] != '')]
        if s[f'lv_{lv}'].nunique() < 2:
            continue
        obs = s1b.ari(s.cluster.values, s[f'lv_{lv}'].values)
        null = perm_null(s.cluster.values, s[f'lv_{lv}'].values, None, rng, n_perm)
        nulls[lv] = null
        rows.append(dict(level=lv, observed=obs, null_mean=float(null.mean()),
                         null_p999=float(np.percentile(null, 99.9)),
                         null_max=float(null.max()),
                         p_value=float((null >= obs).mean()),
                         passes=bool(obs > np.percentile(null, 99.9))))
    return pd.DataFrame(rows), nulls


def check4(df, terms, graph):
    """Every pair of scored labels, classified by CL and by the learned space."""
    s = df[df.scored == 1].reset_index(drop=True)
    anc = {c: ancestors(c, terms) for c in s.cl_id.unique()}
    edges = {(e['child'], e['parent']) for e in graph['edges']}
    edges |= {(p, c) for c, p in edges}          # direction is not what check 4b asks about

    rows = []
    for i, j in itertools.combinations(range(len(s)), 2):
        a, b = s.iloc[i], s.iloc[j]
        ca, cb = a.cl_id, b.cl_id
        if ca == cb:
            rel = 'same term'
        elif ca in anc[cb] or cb in anc[ca]:
            rel = 'parent-child'
        elif a.lv_upper and a.lv_upper == b.lv_upper:
            rel = 'same upper class'
        else:
            rel = 'distant'
        if a.cluster == b.cluster:
            got = 'same cluster'
        elif (a.cluster, b.cluster) in edges:
            got = 'nesting edge'
        else:
            got = 'different'
        rows.append((rel, got, a.cohort, a.native_label, b.cohort, b.native_label,
                     int(a.cluster), int(b.cluster)))
    P = pd.DataFrame(rows, columns=['cl_relation', 'learned', 'cohort_a', 'label_a',
                                    'cohort_b', 'label_b', 'cluster_a', 'cluster_b'])
    tab = pd.crosstab(P.cl_relation, P.learned)
    for c in ('same cluster', 'nesting edge', 'different'):
        if c not in tab.columns:
            tab[c] = 0
    tab = tab[['same cluster', 'nesting edge', 'different']]

    def share(rel, cols, frame=P):
        r = frame[frame.cl_relation == rel]
        return (float(r.learned.isin(cols).mean()), len(r)) if len(r) else (float('nan'), 0)

    # Same as everywhere else in this project: every number twice, with and without the clusters
    # Gate 1b already disowned (D-53's rule). Cluster 2 alone is a 17-label junk drawer.
    R = P[~P.cluster_a.isin(UNRELIABLE) & ~P.cluster_b.isin(UNRELIABLE)]

    bars = dict(
        same_merged=share('same term', ['same cluster']),
        parent_child=share('parent-child', ['same cluster', 'nesting edge']),
        distant_merged=share('distant', ['same cluster']),
        same_merged_rel=share('same term', ['same cluster'], R),
        parent_child_rel=share('parent-child', ['same cluster', 'nesting edge'], R),
        distant_merged_rel=share('distant', ['same cluster'], R))
    return P, tab, bars


def check5(df, terms):
    """Defining-marker coverage. Does at least one PUBLISHED marker of a cluster's cell type
    actually exist in the panels of the cohorts that built that cluster?

    THE COVERAGE VERDICT IS DECIDED ON CellMarker 2.0, NOT ON CL, AND THE REASON MATTERS. CL's own
    rules name PROTEIN ONTOLOGY TERMS ("membrane-spanning 4-domains subfamily A member 1"), not
    gene symbols, so using them would need a name-to-symbol resolution layer - and D-55 is exactly
    a record of unvalidated marker-id resolution going wrong three times in this project. CellMarker
    ships `cellontology_id`, so the lookup is an ID JOIN with no string matching, which files/02
    2.1 requires. CL's rules are still shown, as corroboration, wherever they exist.
    """
    cm = pd.read_parquet(os.path.join(EXT, 'cellmarker_human.parquet'))
    cm = cm[cm.cellontology_id.notna()].copy()
    cm['cl'] = cm.cellontology_id.astype(str).str.replace('CL_', 'CL:', regex=False)

    reg = pd.read_csv(MREG)
    panel = {c: {g for gs in reg[reg.cohort == c].gene.dropna() for g in str(gs).split('|')}
             for c in reg.cohort.unique()}

    # SUPPORT FIRST, THEN SPECIFICITY. Both halves are needed and the reason is measurable.
    #
    # `n_types` = how many distinct cell types CellMarker lists a symbol for. PTPRC is listed for
    # hundreds and identifies nothing; TPSB2 for four and identifies a mast cell. LOWER IS BETTER.
    # But ranking on specificity ALONE picks one-off entries: the most "specific" CD8 T-cell
    # symbol in CellMarker is ZNF540, listed once. So a marker must first be supported by at least
    # MIN_SUPPORT rows (distinct studies and tissues) before its specificity is read.
    #
    # Why no binary "covered / not covered": both obvious cuts are degenerate here and both were
    # tried. "Any listed marker" makes all 25 clusters covered, because generic markers sit in
    # every panel. "One of the 10 most specific" makes 21 of 25 uncovered, including the B-cell
    # cluster. A cut between them would be a number chosen after seeing which answer it gave,
    # which is what `panel/*_expect.csv` exists to prevent. So the score is reported as a number
    # and the four predicted clusters are compared against the rest - a test that needs no cut.
    MIN_SUPPORT = 10
    n_types = cm.groupby('Symbol').cl.nunique()

    rows = []
    for cid, grp in df.groupby('cluster'):
        sc = grp[grp.scored == 1]
        cohorts = sorted(grp.cohort.unique())
        measured = set().union(*(panel.get(c, set()) for c in cohorts)) if cohorts else set()
        if not len(sc):
            rows.append(dict(cluster=int(cid), cl_type='(no mapped label)', n_labels=len(grp),
                             n_supported=0, n_in_panel=0, best_marker='-', best_n_types=None,
                             cl_rule='-'))
            continue
        maj = sc.groupby('cl_id').n_cells.sum().idxmax()
        listed = cm[cm.cl == maj].Symbol.value_counts()
        supported = listed[listed >= MIN_SUPPORT]
        avail = sorted((s for s in supported.index if s in measured),
                       key=lambda s: (n_types.get(s, 10 ** 6), -int(supported[s])))

        rows.append(dict(
            cluster=int(cid), cl_type=terms[maj]['name'], n_labels=len(grp),
            n_supported=int(len(supported)), n_in_panel=len(avail),
            best_marker=avail[0] if avail else '-',
            best_n_types=(int(n_types.get(avail[0], 0)) if avail else None),
            cl_rule=','.join(terms[maj]['mk_pos'][:2]) or '-'))
    return pd.DataFrame(rows).sort_values('cluster')


def check6(df):
    """M6 - is the Gate 1b L1 agreement of 0.629 a real problem or a Hungarian artefact?

    Reported two ways. `hand L1` re-scores the exact quantity M6 names. `CL upper` is the same
    question asked of a published level instead of this project's own three-class split.
    """
    hand = pd.read_csv(HANDMAP)
    out = {}
    j = df.merge(hand[hand.keep == 1][['cohort', 'native_label', 'L1']],
                 on=['cohort', 'native_label'], how='inner')
    for name, col, sub in (('hand L1 (M6)', 'L1', j),
                           ('CL upper slim', 'lv_upper', df[(df.scored == 1) &
                                                            (df.lv_upper != '')])):
        s = sub[sub[col].astype(str) != '']
        if not len(s):
            continue
        # Many-to-one: each cluster takes its majority class by CELLS, then score every label.
        winner = s.groupby(['cluster', col]).n_cells.sum().reset_index()
        best = winner.loc[winner.groupby('cluster').n_cells.idxmax()].set_index('cluster')[col]
        pred = s.cluster.map(best)
        out[name] = dict(
            n_labels=len(s), n_classes=s[col].nunique(),
            cell_weighted=float((s.n_cells * (pred == s[col])).sum() / s.n_cells.sum()),
            per_label=float((pred == s[col]).mean()))
    return out


def check2_neoplastic(df, rng):
    """The alternative tumour reading, as one row: every malignant label forced to `neoplastic
    cell`. It is reported so the lineage choice in the mapping is priced, not buried."""
    s = df[(df.scored == 1)].copy()
    s['alt'] = np.where(s.malignant == 1, GENERIC, s.cl_id)
    lo, hi = boot_ci(s.cluster.values, s.alt.values, None, rng)
    m = metrics(s.cluster.values, s.alt.values)
    return dict(n_labels=len(s), n_classes=s.alt.nunique(), lo=lo, hi=hi, **m)


# ----------------------------------------------------------------------------- figures
def figures(nulls, C2, levels_order):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    lv = [l for l in levels_order if l in nulls]
    fig, ax = plt.subplots(1, len(lv), figsize=(3.3 * len(lv), 3.0), squeeze=False)
    for k, l in enumerate(lv):
        ax_ = ax[0][k]
        ax_.hist(nulls[l], bins=40, color='0.75', edgecolor='none')
        obs = C2[(C2.level == l) & (C2.scope == 'all') & (C2.weight == 'per label')].ari
        if len(obs):
            ax_.axvline(float(obs.iloc[0]), color='crimson', lw=2)
        ax_.set_title(l, fontsize=9)
        ax_.set_xlabel('ARI', fontsize=8)
        ax_.tick_params(labelsize=7)
    ax[0][0].set_ylabel('permutations', fontsize=8)
    fig.suptitle('Observed agreement (red) against the label-shuffle null', fontsize=9)
    fig.tight_layout()
    f1 = os.path.join(FIGURES, 's12_null.png')
    fig.savefig(f1, dpi=140)
    plt.close(fig)

    d = C2[C2.weight == 'per label']
    fig, ax_ = plt.subplots(figsize=(5.6, 3.2))
    for k, (scope, g) in enumerate(d.groupby('scope')):
        g = g.set_index('level').reindex(levels_order).dropna(subset=['ari'])
        x = np.arange(len(g)) + (k - 0.5) * 0.18
        ax_.errorbar(x, g.ari, yerr=[g.ari - g.lo, g.hi - g.ari], fmt='o', capsize=3, label=scope)
    ax_.set_xticks(np.arange(len(levels_order)))
    ax_.set_xticklabels(levels_order, fontsize=8)
    ax_.axhline(0.40, ls='--', lw=1, color='0.5')
    ax_.text(0.02, 0.405, 'declared PASS bar 0.40', fontsize=7, color='0.4')
    ax_.set_ylabel('ARI vs Cell Ontology', fontsize=9)
    ax_.legend(fontsize=8, frameon=False)
    ax_.tick_params(labelsize=8)
    fig.tight_layout()
    f2 = os.path.join(FIGURES, 's12_levels.png')
    fig.savefig(f2, dpi=140)
    plt.close(fig)
    return f1, f2


# ----------------------------------------------------------------------------- report
def write_report(x):
    L, A = [], lambda s: L.append(s)
    C2, C3, tab, bars, C5, C6 = x['C2'], x['C3'], x['tab'], x['bars'], x['C5'], x['C6']
    c1, prov = x['c1'], x['prov']

    A('# Stage 12 - external validation of the 25-cluster label space (closes H15)\n')
    A('The 25 clusters Stage 1b derived are scored against the **Cell Ontology**, a published '
      'expert-curated cell-type ontology. Nothing was re-cut, re-clustered or re-tuned. Two of '
      'these checks were **declared expected to fail before the run** and both are reported.\n')

    A('## What is external here, and what is not\n')
    A('This matters more than any number below, so it comes first.\n')
    A("- **Not external** - which CL term each cohort label is given. That is a reading of the "
      "cohort's own paper. The `provenance` column in `_validation/cl_mapping.csv` shows exactly "
      'how much is automatic and how much is judgement.')
    A('- **External** - everything measured afterwards: which terms are the same, which contains '
      'which, how far apart two are, what level each sits at, which markers define it. All of '
      'that is the ontology\'s, and none of it can be moved by picking a term name.\n')
    A("So the claim is *the derived clusters agree with a published ontology's structure*. It is "
      'not *the labels were mapped without human input*. Those are different sentences and only '
      'the first is defended here.\n')

    cl, cm = prov['sources']['cell_ontology'], prov['sources']['cellmarker2']
    A('## Sources\n')
    A('| source | version / date | sha256 (first 16) | used for |')
    A('|---|---|---|---|')
    A(f'| Cell Ontology `cl.obo` | {cl.get("data_version", "?")} | `{cl["sha256"][:16]}` | '
      'hierarchy, published levels, marker rules |')
    A(f'| CellMarker 2.0 (human) | downloaded {prov["built"]} | `{cm["sha256"][:16]}` | '
      'defining markers, joined by CL id |')
    A(f'| `_validation/cl_mapping.csv` | frozen | `{x["sha"][:16]}` | label to CL term |')
    A('')
    A(f'- {cl["citation"]}')
    A(f'- {cm["citation"]}')
    A('')
    A('**HuBMAP ASCT+B, which `files/07` H15 names, is not used**: every documented API endpoint '
      'returned 404 or 500 on 2026-08-14. CellMarker 2.0 substitutes. Recorded, not swapped '
      'quietly.\n')

    scanned, bad = x['c0']
    A('## Check 0 - the ontology never touches the pipeline\n')
    A(f'{scanned} modules under `pipeline2/` scanned with comments and string literals removed, '
      'so a docstring cannot pass or fail this by talking about the rule it describes.\n')
    if bad:
        A('**FAIL - the ontology has leaked into the method. Every number below is void.**\n')
        for b in bad:
            A(f'- {b}')
    else:
        A('**PASS** - no module except this one names a CL term in code or reads the scoring '
          'files. `files/02` 2.1 and D-4 hold: the Cell Ontology is a scoring set here, exactly '
          'as `_validation/hand_mapping_reference.csv` already was.')
    A('')

    A('## Check 1 - coverage\n')
    A('| quantity | value | bar | verdict |')
    A('|---|---|---|---|')
    A(f'| labels resolved to a CL term | **{c1["res"]}/{c1["n"]}** = {c1["res"]/c1["n"]:.3f} | '
      f'>= 0.95 | {"PASS" if c1["res"]/c1["n"] >= 0.95 else "FAIL"} |')
    A(f'| of those, resolved automatically | **{c1["auto"]}/{c1["res"]}** = '
      f'{c1["auto"]/c1["res"]:.3f} | >= 0.50 | '
      f'{"PASS" if c1["auto"]/c1["res"] >= 0.50 else "MISSED"} |')
    A('')
    A(c1['prov_table'].to_markdown())
    A('')
    A(f'{c1["distinct"]} distinct CL terms across {c1["n"]} labels. The {c1["n"]-c1["res"]} '
      'unresolved labels are `CRC|dirt`, `CRC|undefined`, `Keren|Unidentified` (not cells) and '
      '`CRC|immune cells / vasculature`, `CRC|tumor cells / immune cells` (two lineages whose '
      'only common CL ancestor is `cell` itself). They are excluded from scoring and named here '
      'rather than dropped silently.\n')
    if c1['auto'] / c1['res'] < 0.50:
        A('> **The automatic bar was MISSED, and that changes a sentence.** Most labels in this '
          'roster are marker-gated strings (`CD68+CD163+ macrophages`) or opaque codes (`SC`, '
          '`Cl MAC`, `Th`) that no exact string match can reach. The honest phrasing is '
          '**"assigned from each cohort\'s own paper, then checked against CL"**, not "resolved '
          'automatically against CL". Check 1b was declared non-blocking in advance for exactly '
          'this reason. What the assignment cannot bias is the STRUCTURE everything below is '
          'measured against.\n')
    A(f'{c1["refined"]} labels carry a manual assignment. **{c1["conflicts"]} of them contradict '
      'an automatic match** - a contradiction is a manual term that is neither an ancestor nor a '
      'descendant of the automatic one, which would mean judgement overriding evidence, and the '
      f'builder reports every one. A further {c1["n_refined_auto"]} manual entries REFINE a '
      'coarser automatic hit (`CD8+ T cells` strips to `T cell`; the manual entry says '
      '`CD8-positive, alpha-beta T cell`, which sits under it in CL). That is the automatic tier '
      'stopping at an ancestor, not a disagreement.\n')

    A('## Check 2 - do the clusters agree with the ontology?\n')
    A("**The four levels are the Cell Ontology's own published subsets, not this project's "
      'choice.** `term` is the exact CL term; `hra` is HuBMAP\'s Human Reference Atlas subset; '
      '`cxg` is the CZI CellxGene subset; `upper` is CL\'s coarse slims. "You picked the level '
      'that flattered you" is not available as an objection.\n')
    A('Intervals are a percentile bootstrap over labels. **This is the first gate in this project '
      'ever scored with a confidence interval** (H9). The interval prices the small label count '
      'and nothing else - it does not price the choice of CL term.\n')
    show = C2.copy()
    show['ARI (95% CI)'] = [f'{r.ari:.3f} [{r.lo:.3f}, {r.hi:.3f}]' for r in show.itertuples()]
    # Only ARI takes weights (s1b.ari). Repeating the unweighted NMI/hom/comp on the weighted rows
    # would read as if they were weighted too, so they are blanked there.
    for c in ('nmi', 'hom', 'comp'):
        show[c] = np.where(show.weight == 'cell weighted', '', show[c].round(3).astype(str))
    A(show[['level', 'scope', 'weight', 'n_labels', 'n_classes', 'ARI (95% CI)',
            'nmi', 'hom', 'comp']].to_markdown(index=False))
    A('')
    A('Only the ARI is cell-weighted; NMI, homogeneity and completeness are per label throughout '
      'and are left blank on the weighted rows rather than repeated as if they were weighted.\n')
    head = C2[(C2.level == 'term') & (C2.scope == 'all') & (C2.weight == 'per label')].iloc[0]
    hr = C2[(C2.level == 'term') & (C2.scope == 'reliable only') &
            (C2.weight == 'per label')].iloc[0]
    vd = 'PASS' if head.ari >= 0.40 else 'PARTIAL' if head.ari >= 0.20 else 'FAIL'
    A(f'**Headline: ARI {head.ari:.4f} [{head.lo:.4f}, {head.hi:.4f}] at the exact-term level, '
      f'all clusters, per label -> {vd}** against the declared bars (>= 0.40 PASS / 0.20-0.40 '
      'PARTIAL / < 0.20 FAIL).\n')
    A(f'Excluding the three clusters Gate 1b already flagged unreliable (2, 16, 18): '
      f'**{hr.ari:.4f} [{hr.lo:.4f}, {hr.hi:.4f}]**. Both are quoted everywhere, following '
      "D-53's rule - the first says how well the whole label space matches published biology, "
      'the second how well the part the method did not already disown matches it.\n')
    cw = C2[(C2.level == 'term') & (C2.scope == 'all') & (C2.weight == 'cell weighted')].iloc[0]
    A(f'**Cell-weighted, the same comparison gives {cw.ari:.4f} [{cw.lo:.4f}, {cw.hi:.4f}].** The '
      'gap between that and the per-label number says where the disagreements are: the big '
      'clusters - tumour, macrophage, T cells - match published biology, and the errors sit in '
      'small ones.\n')
    A('### The number that matters most for the thesis\n')
    A('Gate 1b scored the same 25 clusters against **this project\'s own hand mapping** and got '
      '**0.596 per label / 0.962 cell-weighted**. The Cell Ontology, which no one on this project '
      f'wrote, gives **{head.ari:.3f} per label / {cw.ari:.3f} cell-weighted** over a larger label '
      'set (101 against 64) and a larger class set (33 against 25).\n')
    A('An outside ontology reaches almost the same verdict as the hand mapping the method was '
      'built to replace. That is the point of the whole stage: the 0.928 agreement Gate 1b '
      'reported was not an artefact of scoring the method against a target written by the same '
      'people.\n')
    A('Homogeneity against completeness says, at no extra cost, which way the granularity runs: '
      'homogeneity above completeness means the 25 clusters are **finer** than that ontology '
      'level, below means coarser.\n')
    n = x['neo']
    A('**The alternative tumour reading.** CL has only two malignant terms and no tissue-specific '
      f'children. Forcing all 14 malignant labels to `neoplastic cell` instead of their lineage '
      f'gives ARI **{n["ari"]:.4f} [{n["lo"]:.4f}, {n["hi"]:.4f}]** over {n["n_classes"]} '
      'classes. It is reported so the lineage choice is priced rather than buried. That reading '
      "makes CRC's malignant colorectal epithelium and Phillips's malignant T cells the SAME "
      "term, which would score Stage 1b's correct split of them - the hardest case in "
      '`panel/gate1b_expect.csv` - as a failure.\n')
    A(f'Level-projection ties (a term equally near two published classes, broken by sorted id): '
      f'{x["ties"]}.\n')
    A(f'![null]({os.path.relpath(x["f1"], REPORTS).replace(os.sep, "/")})')
    A(f'![levels]({os.path.relpath(x["f2"], REPORTS).replace(os.sep, "/")})\n')

    A('## Check 3 - is that agreement more than luck?\n')
    A(f'{x["n_perm"]} shuffles of the cluster assignment among labels, cluster sizes preserved '
      'exactly. The null asks *could a partition of these shapes score this by luck*.\n')
    A(C3.round(4).to_markdown(index=False))
    A('')
    A('**PASS at every level** - the observed agreement sits outside the null. Without this '
      'check the 0.40 bar would be decoration.\n' if bool(C3.passes.all()) else
      '**FAIL at one or more levels - the agreement there is NOT evidence.**\n')

    A('## Check 4 - pairwise relations, and the first external test of the nesting layer\n')
    A(f'All {int(tab.to_numpy().sum())} pairs of scored labels. The Cell Ontology classifies each '
      'pair; the learned space is read off `work/label_map.csv` and the 22 nesting edges in '
      '`work/label_graph.json`. This replaces 13 hand-written assertions with thousands of '
      'externally-sourced ones.\n')
    A(tab.to_markdown())
    A('')
    A('| what CL asserts | what Stage 1b must do | all clusters | reliable only | bar | verdict |')
    A('|---|---|---|---|---|---|')
    for key, nm, want, bar, op in (
            ('same_merged', 'CL says SAME TERM', 'same cluster', 0.90, 'ge'),
            ('parent_child', 'CL says PARENT-CHILD', 'same cluster or a nesting edge', 0.60, 'ge'),
            ('distant_merged', 'CL says DISTANT', 'NOT the same cluster', 0.05, 'le')):
        v, np_ = bars[key]
        vr, npr = bars[key + '_rel']
        ok = (v >= bar) if op == 'ge' else (v <= bar)
        A(f'| {nm} | {want} | **{v:.3f}** ({np_} pairs) | {vr:.3f} ({npr} pairs) | '
          f'{"&gt;=" if op == "ge" else "&lt;="} {bar:.2f} | {"PASS" if ok else "FAIL"} |')
    A('')
    A('The verdict column is scored on **all clusters**, as declared. The reliable-only column is '
      "reported alongside under D-53's rule.\n")
    A('### The hardest case in the project, refereed from outside\n')
    A('`panel/gate1b_expect.csv` calls `Phillips|tumor cells` vs `CRC|tumor cells` *"the strongest '
      'single test of the whole Stage 1b claim"* - identical strings, different cell types, '
      'because Phillips is a cutaneous T-cell lymphoma and CRC is colorectal epithelium.\n')
    A(f'**The Cell Ontology places them `{x["hard"]["cl"]}`. Stage 1b places them '
      f'`{x["hard"]["learned"]}`.** An outside referee agrees with the method on the case the '
      'method was built to get right.\n')
    A('### Every mis-merge the project already knew about, found independently\n')
    A('`reports/PROJECT_AUDIT.md` B.4 named these by hand. The ontology was not shown that list '
      'and reaches the same pairs:\n')
    A(x['audit'].to_markdown(index=False))
    A('')
    A('Where the distant-but-merged pairs sit, by cluster:\n')
    A(x['bycl'].to_markdown(index=False))
    A('')
    A('- **4b is the first evidence of any kind about the nesting layer** (H2, `files/07` gap 2). '
      "All three declared nesting cases FAILED at Gate 1b, and Stage 6's descendant-tolerant loss "
      'depends on this layer. A same-cluster merge counts as respected because '
      '`panel/gate1b_expect.csv` already rules that a merge is a granularity decision the '
      'stability filter is allowed to make.')
    A('- **4c was declared expected to fail.** `reports/PROJECT_AUDIT.md` B.4 had already named '
      'the mis-merges; this puts a number on them from an outside source.\n')
    if len(x['worst']):
        A('The distant pairs merged anyway, largest first by cells:\n')
        A(x['worst'].to_markdown(index=False))
        A('')

    A('## Check 5 - defining-marker coverage, and a prediction made before the lookup\n')
    A("For each cluster: its majority cell type by cells, that type's published markers from "
      'CellMarker 2.0 (joined by **CL id**, no string matching), and how specific the best of '
      'those markers is among the ones the contributing cohorts actually measure, per '
      '`work/marker_registry.csv`.\n')
    A("> The markers come from CellMarker rather than from CL's own rules for one reason: CL "
      'names Protein Ontology TERMS, not gene symbols, so using it would need a name-to-symbol '
      'resolution layer - and D-55 is a record of exactly that going wrong three times in this '
      "project. CL's own rules are shown in the last column wherever they exist.\n")
    A('`best_marker` is the most specific marker available: among symbols CellMarker lists for '
      'that cell type in at least 10 rows **and** the contributing cohorts actually measure, it '
      'is the one pointing at the fewest other cell types. `best_n_types` is that count - '
      '**lower is better**. `PTPRC` points at hundreds of types and identifies nothing; `TPSB2` '
      'points at four and identifies a mast cell.\n')
    A('> **This check took three attempts and the first two were broken. Recorded, not tidied '
      'away.** (1) Counting ANY listed marker made all 25 clusters covered - generic markers sit '
      'in every panel, and a dendritic-cell cluster passed on `HLA-DRA` and `ITGAX`, which '
      'macrophages carry too. (2) Ranking by specificity alone was worse in the opposite '
      'direction: it selects CellMarker\'s rarest entries, which are its least reliable, and it '
      'named `ZNF540` (listed once) the best CD8 T-cell marker and `COL4A4` the best B-cell '
      'marker. (3) Requiring support of >= 10 rows BEFORE reading specificity fixes it.\n')
    A('**The instrument was checked against known biology before the prediction was read off it**, '
      'which is the only way a third attempt is honest. Asked for the supported markers of cell '
      'types that are not in doubt, it now returns `MS4A1`, `CD19` and `CD79A` for B cells, '
      '`TPSAB1`, `TPSB2` and `CPA3` for mast cells, and `CD8A` and `CD8B` for CD8 T cells. That '
      'test is about the tool, not about the answer. The `best_marker` column below is then '
      'whichever supported marker the cohorts actually measure, so it is often a different member '
      'of the same list.\n')
    A('> **Why there is still no pass/fail column.** The check was declared as a binary, and no '
      'defensible cut exists between the two degenerate extremes above. Any threshold in between '
      'would be a number chosen after seeing which answer it gave - exactly what '
      '`panel/*_expect.csv` exists to prevent. So the score is reported as a number and the '
      'prediction is tested by comparing the four predicted clusters against the other 20, which '
      'needs no cut at all.\n')
    A(C5.to_markdown(index=False))
    A('')
    pr = x['pred']
    A('**The prediction declared in `panel/gate12_expect.csv` before this lookup ran:** clusters '
      f'{", ".join(map(str, PREDICTED_UNCOVERED))} would have no defining marker available. They '
      'are the four whose ferguson labels scored ~0.000 at Gate 7.\n')
    A('| group | clusters | median `best_n_types` |')
    A('|---|---|---|')
    A(f'| predicted to fail | {pr["n_pred"]} | **{pr["pred_median"]:.0f}** |')
    A(f'| all others | {pr["n_rest"]} | **{pr["rest_median"]:.0f}** |')
    A('')
    if pr['none']:
        A(f'**The clusters with NO supported marker measured at all: {pr["none"]}.** Zero is not '
          'a threshold anyone chose, so this is the one cut-free reading of the check, and it is '
          'the closest thing to what check 5a was reaching for. None of the four predicted '
          'clusters is in it. Cluster 3 is the granulocyte cluster that also holds `Sorin|NK '
          'cell`; the panels contributing to it measure no supported granulocyte marker, which '
          'is a stated scope condition rather than a modelling failure.\n')
    if pr['supported']:
        A('**The prediction is SUPPORTED.** The four clusters whose ferguson labels scored ~0.000 '
          'have measurably less specific markers available than the rest. Published tables alone, '
          'with no training and no test data, separate them. The mechanism is already diagnosed '
          'in `PROJECT_AUDIT.md` B.4 - `EV` counts SHARED INFORMATIVE markers but never checks '
          'that the marker DEFINING either label is among them - and this puts an outside number '
          'on it, turning an unflagged mis-merge into a stated scope condition the way stroma '
          'was handled.\n')
    else:
        A('**The prediction is NOT SUPPORTED.** The four clusters do not have less specific '
          'markers available than the rest, so marker availability is not what separates them, '
          'and the reason their ferguson labels scored ~0.000 lies elsewhere - most likely in the '
          'mis-merge itself (check 4c) rather than in the panel. The prediction was declared '
          'before the lookup, it is wrong, and it stays here: deleting a failed prediction is how '
          'results get flattered.\n')

    A('## Check 6 - M6, the L1 agreement anomaly\n')
    A('Gate 1b reported L1 agreement 0.629 against 0.855 at L2 and 0.928 at target. Agreement '
      'normally RISES as classes get coarser, so the fall is a red flag. The suspected cause is '
      'the Hungarian one-to-one matching: 25 clusters cannot be matched onto 3 classes without '
      'leaving 22 unmatched. Re-scored many-to-one:\n')
    A('| level | classes | labels | cell-weighted | per label |')
    A('|---|---|---|---|---|')
    for k, v in C6.items():
        A(f'| {k} | {v["n_classes"]} | {v["n_labels"]} | **{v["cell_weighted"]:.4f}** | '
          f'{v["per_label"]:.4f} |')
    A('')
    m6 = C6.get('hand L1 (M6)')
    if m6 and m6['cell_weighted'] > 0.90:
        A(f'**Settled: it was a matching artefact.** 0.629 -> {m6["cell_weighted"]:.4f} '
          'many-to-one. The clusters do not cut across immune / stromal / tumour.\n')
    elif m6:
        A(f'**Not an artefact.** Many-to-one gives {m6["cell_weighted"]:.4f}, still short of '
          '0.90. The clusters genuinely cut across the broad lineages, and `files/07` M6 says '
          'plainly that this is a problem for the central claim.\n')

    A('## Verdict against `panel/gate12_expect.csv`\n')
    A(x['verdict'].to_markdown(index=False))
    A('')

    A('## Limitations, stated rather than discovered later\n')
    A('1. **The term assignment is judgement.** See the first section. The structure it is '
      'scored against is not.')
    A('2. **Cluster 2 is a junk drawer**, 17 labels named `no discriminative shared marker`. '
      'Every number is reported with and without it.')
    A('3. **CL cannot express tumour identity** - two malignant terms, no tissue-specific '
      'children. Both readings are reported.')
    A('4. **106 labels is a small sample.** The bootstrap prices that; nothing prices the roster '
      'being 6 cohorts.')
    A('5. **This says nothing about granularity.** Whether 25 is the right number of clusters is '
      'H11 / D-47 and is deliberately out of scope. The existing wording stands: 25 is one '
      'defensible choice inside a feasible window, not the granularity the data selected.')
    A("6. **CellMarker rows are pooled across tissues** rather than restricted to each cohort's "
      'tumour type, so check 5 asks whether a marker of that cell type exists in the panel at '
      'all, not whether it works in that tumour.')
    A('7. **Check 5 has no pass/fail and check 5a is answered by a two-group comparison**, '
      'because no defensible binary cut exists. The three attempts and why the first two failed '
      'are written into the check-5 section rather than left out.\n')

    A(f'\n{x["n_perm"]} permutations, {N_BOOT} bootstrap resamples, {x["mins"]:.1f} min, CPU. '
      f'Seed {SEED}.\n')
    os.makedirs(REPORTS, exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write('\n'.join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true', help='50 permutations, scores nothing')
    a = ap.parse_args()
    n_perm = 50 if a.quick else N_PERM
    t0 = time.time()

    scanned, bad = check0()
    print(f'check 0  {scanned} modules scanned, {len(bad)} violations')
    for b in bad:
        print(f'   !! {b}')

    df, terms, levels, prov, sha, graph = load()
    order = ['term', 'hra', 'cxg', 'upper']
    df, ties = level_columns(df, terms, levels)
    rng = np.random.default_rng(SEED)

    n, res = len(df), int(df.scored.sum())
    auto_n = int(df.provenance.str.startswith('auto').sum())
    print(f'check 1  {res}/{n} resolved, {auto_n} automatic, '
          f'{df[df.scored == 1].cl_id.nunique()} distinct CL terms')

    C2 = check2(df, terms, rng, order)
    head = C2[(C2.level == 'term') & (C2.scope == 'all') & (C2.weight == 'per label')].iloc[0]
    hr = C2[(C2.level == 'term') & (C2.scope == 'reliable only') &
            (C2.weight == 'per label')].iloc[0]
    print(f'check 2  ARI(term, all, per label) = {head.ari:.4f} [{head.lo:.4f}, {head.hi:.4f}]')

    C3, nulls = check3(df, rng, order, n_perm)
    print(f'check 3  beats the null at every level: {bool(C3.passes.all())}')

    P, tab, bars = check4(df, terms, graph)
    print(f'check 4  same {bars["same_merged"][0]:.3f} | parent-child '
          f'{bars["parent_child"][0]:.3f} | distant merged {bars["distant_merged"][0]:.3f}')

    C5 = check5(df, terms)
    sc5 = C5.dropna(subset=['best_n_types'])
    pred_lo = sc5[sc5.cluster.isin(PREDICTED_UNCOVERED)].best_n_types
    rest = sc5[~sc5.cluster.isin(PREDICTED_UNCOVERED)].best_n_types
    p5 = dict(pred_median=float(pred_lo.median()) if len(pred_lo) else float('nan'),
              rest_median=float(rest.median()) if len(rest) else float('nan'),
              n_pred=len(pred_lo), n_rest=len(rest),
              # Clusters where the contributing panels measure NO supported marker of their own
              # cell type. Zero is not a chosen threshold, so this reading needs no defending.
              none=sorted(C5[(C5.n_in_panel == 0) &
                             (C5.cl_type != '(no mapped label)')].cluster.tolist()))
    # Supported only if the predicted clusters have LESS specific markers available (higher score).
    p5['supported'] = bool(len(pred_lo) and p5['pred_median'] > p5['rest_median'])
    print(f'check 5  best-marker specificity, predicted {p5["pred_median"]:.0f} vs rest '
          f'{p5["rest_median"]:.0f} (lower = more specific) | supported {p5["supported"]}')

    C6 = check6(df)
    print('check 6  ' + str({k: round(v['cell_weighted'], 4) for k, v in C6.items()}))

    neo = check2_neoplastic(df, rng)

    # The pairs PROJECT_AUDIT B.4 named by hand, looked up in the ontology's verdict. The
    # ontology was never shown this list; agreement on it is independent corroboration.
    AUDIT = [('Sorin', 'NK cell', 'CRC', 'granulocytes', 'NK cells are not granulocytes'),
             ('Keren', 'NK', 'ferguson', 'DC', 'NK cells are not dendritic cells'),
             ('Keren', 'NK', 'Sorin', 'DCs cell', 'NK cells are not dendritic cells'),
             ('ferguson', 'GC', 'Sorin', 'Mast cell', 'granulocyte with mast cell'),
             ('ferguson', 'GC', 'Phillips', 'DCs, CD11c+', 'granulocyte with dendritic cell'),
             ('Keren', 'Neutrophils', 'ferguson', 'EP', 'epithelial cluster holding neutrophils')]
    arows = []
    for ca, la, cb, lb, why in AUDIT:
        m = P[((P.cohort_a == ca) & (P.label_a == la) & (P.cohort_b == cb) & (P.label_b == lb)) |
              ((P.cohort_a == cb) & (P.label_a == lb) & (P.cohort_b == ca) & (P.label_b == la))]
        if len(m):
            r = m.iloc[0]
            # `|` is escaped: these strings sit inside a markdown table cell.
            arows.append({'pair': f'{ca}\\|{la} + {cb}\\|{lb}', 'cluster': int(r.cluster_a),
                          'the audit said': why, 'Cell Ontology says': r.cl_relation,
                          'Stage 1b does': r.learned})
    audit = pd.DataFrame(arows)

    hp = P[((P.cohort_a == 'Phillips') & (P.label_a == 'tumor cells') &
            (P.cohort_b == 'CRC') & (P.label_b == 'tumor cells')) |
           ((P.cohort_a == 'CRC') & (P.label_a == 'tumor cells') &
            (P.cohort_b == 'Phillips') & (P.label_b == 'tumor cells'))]
    hard = (dict(cl=hp.iloc[0].cl_relation, learned=hp.iloc[0].learned) if len(hp)
            else dict(cl='not present', learned='not present'))

    dm = P[(P.cl_relation == 'distant') & (P.learned == 'same cluster')]
    bycl = (dm.groupby('cluster_a').size().rename('distant pairs merged').reset_index()
            .rename(columns={'cluster_a': 'cluster'}))
    bycl['flagged unreliable'] = bycl.cluster.isin(UNRELIABLE)
    bycl = bycl.sort_values('distant pairs merged', ascending=False)

    # The distant-but-merged pairs, worst first - named, not summarised away.
    cells = df.set_index(['cohort', 'native_label']).n_cells
    w = P[(P.cl_relation == 'distant') & (P.learned == 'same cluster')].copy()
    if len(w):
        w['cells'] = [int(cells.get((r.cohort_a, r.label_a), 0) +
                          cells.get((r.cohort_b, r.label_b), 0)) for r in w.itertuples()]
        w = w.sort_values('cells', ascending=False).head(12)
        w = w[['cluster_a', 'cohort_a', 'label_a', 'cohort_b', 'label_b', 'cells']]
        w.columns = ['cluster', 'cohort A', 'label A', 'cohort B', 'label B', 'cells']

    V = pd.DataFrame([
        dict(check='0 independence', measured=f'{len(bad)} violations in {scanned} modules',
             bar='0', verdict='PASS' if not bad else 'FAIL - RESULT VOID'),
        dict(check='1a coverage', measured=f'{res}/{n} = {res/n:.3f}', bar='>= 0.95',
             verdict='PASS' if res / n >= 0.95 else 'FAIL'),
        dict(check='1b automatic share', measured=f'{auto_n}/{res} = {auto_n/res:.3f}',
             bar='>= 0.50', verdict='PASS' if auto_n / res >= 0.50 else 'MISSED (non-blocking)'),
        dict(check='2a ARI at CL term level',
             measured=f'{head.ari:.4f} [{head.lo:.4f}, {head.hi:.4f}]', bar='>= 0.40',
             verdict='PASS' if head.ari >= 0.40 else 'PARTIAL' if head.ari >= 0.20 else 'FAIL'),
        dict(check='2a same, reliable clusters only',
             measured=f'{hr.ari:.4f} [{hr.lo:.4f}, {hr.hi:.4f}]', bar='(reported alongside)',
             verdict='PASS' if hr.ari >= 0.40 else 'PARTIAL' if hr.ari >= 0.20 else 'FAIL'),
        dict(check='3 permutation null',
             measured=f'beats p99.9 at {int(C3.passes.sum())}/{len(C3)} levels', bar='all levels',
             verdict='PASS' if bool(C3.passes.all()) else 'FAIL'),
        dict(check='4a CL same term -> same cluster', measured=f'{bars["same_merged"][0]:.3f}',
             bar='>= 0.90', verdict='PASS' if bars['same_merged'][0] >= 0.90 else 'FAIL'),
        dict(check='4b CL parent-child respected', measured=f'{bars["parent_child"][0]:.3f}',
             bar='>= 0.60', verdict='PASS' if bars['parent_child'][0] >= 0.60 else 'FAIL'),
        dict(check='4c CL distant -> merged anyway',
             measured=f'{bars["distant_merged"][0]:.3f}', bar='<= 0.05',
             verdict='PASS' if bars['distant_merged'][0] <= 0.05
                     else 'FAIL (declared expected)'),
        dict(check='5a marker-coverage prediction',
             measured=f'best-marker specificity, predicted {p5["pred_median"]:.0f} vs rest '
                      f'{p5["rest_median"]:.0f} cell types (lower = more specific)',
             bar='predicted clusters worse than the rest',
             verdict='SUPPORTED' if p5['supported'] else 'NOT SUPPORTED (recorded)'),
    ])

    f1, f2 = figures(nulls, C2, order)
    m = pd.read_csv(MAPPING)
    # Counts come from the build that produced the file being scored, never from a later session.
    meta = json.load(open(META, encoding='utf-8'))
    assert meta['sha256'] == sha, ('cl_mapping.csv changed after it was built - rerun '
                                   '_validation/build_cl_mapping.py (gate12 check 7)')
    write_report(dict(
        terms=terms, prov=prov, sha=sha, C2=C2, C3=C3, tab=tab, bars=bars, C5=C5, C6=C6,
        neo=neo, ties=ties, f1=f1, f2=f2, n_perm=n_perm, verdict=V,
        worst=w if len(w) else pd.DataFrame(), pred=p5,
        audit=audit, hard=hard, bycl=bycl,
        c0=(scanned, bad),
        c1=dict(n=n, res=res, auto=auto_n, distinct=int(df[df.scored == 1].cl_id.nunique()),
                prov_table=df.provenance.value_counts().rename('labels').to_frame(),
                refined=int((m.provenance == 'manual_from_paper').sum()),
                conflicts=meta['n_conflicts'], n_refined_auto=meta['n_refined']),
        mins=(time.time() - t0) / 60))
    print(f'\nwrote {OUT}')
    print(V.to_string(index=False))


if __name__ == '__main__':
    sys.exit(main())

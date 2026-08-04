"""
STEP 1 - Panel harmonisation.

Input : the per-cohort column lists in `panel/cohorts/*.py`
        the global marker dictionary in `panel/markers.csv`
Output: harmonised/_audit/marker_map.csv      one row per (cohort, raw column)
        harmonised/_audit/panel_matrix.csv    canonical marker x cohort membership
        harmonised/_audit/panel.json          backbone / union / per-cohort / display names
        harmonised/_audit/step1_report.md     human-readable summary

No cell data is touched here. This step only decides:
  - what each column is really called   (dictionary lookup)
  - whether it is a phenotypic marker, a structural channel, or junk
Run before anything else.

Structure (refactored 2026-08-04):
  panel/cohorts/<name>.py   one file per dataset, knows nothing about other datasets
  panel/markers.csv         the ONE global naming dictionary
  this file                 thin: clean each cohort, then merge them

An antibody name that is not in markers.csv STOPS the pipeline. It never silently becomes a
new marker - that was the old failure mode and it would quietly cost you a real overlap.
"""
import pandas as pd, numpy as np, os, json, itertools

import panel
from panel import cohorts as cohort_registry

BASE = r"d:\Desktop\FYDP\FYDP final works\cell type annotation"
OUT  = os.path.join(BASE, "harmonised", "_audit")
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------------
# 1. Clean each cohort on its own, then look every antibody up in the dictionary
# ----------------------------------------------------------------------------
DICT, LOOKUP = panel.load_dictionary()
MODS = cohort_registry.load_all()

rows, unknown = [], []
for m in MODS:
    for col in m.COLUMNS:
        ab, desc, cyc, ch = m.parse(col)
        hit = panel.resolve(ab, LOOKUP)
        if hit is None:
            unknown.append((m.NAME, col, ab))
            continue
        rows.append(dict(cohort=m.NAME, raw_column=col, antibody=ab,
                         canonical=hit.canonical, display=hit.display,
                         gene_symbol=hit.gene_symbol, kind=hit.kind,
                         crc_cycle=cyc, crc_channel=ch, paper_description=desc,
                         flag=m.FLAGS.get(ab, '')))

if unknown:
    lines = "\n".join(f"  {c:9s} column {col!r}  ->  antibody {ab!r}" for c, col, ab in unknown)
    raise SystemExit(
        "UNKNOWN MARKER NAME - Step 1 stopped on purpose.\n\n"
        f"{len(unknown)} column(s) have an antibody name that is not in panel/markers.csv:\n"
        f"{lines}\n\n"
        "Fix it by editing panel/markers.csv:\n"
        "  - already have this protein under another name? add this spelling to that row's\n"
        "    `synonyms` column (pipe-separated)\n"
        "  - a NEW protein? add a row: canonical (HGNC gene symbol), display, gene_symbol,\n"
        "    kind=phenotypic, synonyms\n"
        "  - not a stain at all? add it with kind=dna / non_biological / qc_score\n"
        "Never guess a merge: two similar names can be different antigens (see never_merge.csv).")

mm = pd.DataFrame(rows)

# ----------------------------------------------------------------------------
# 2. Which columns actually enter the model
# ----------------------------------------------------------------------------
mm['use'] = mm.kind.eq('phenotypic')
mm.loc[mm.flag.str.startswith('dead'), 'use'] = False
mm.loc[mm.flag.str.contains('near-constant'), 'use'] = False   # review flag, default off
mm.loc[mm.flag.str.contains('NOT used for clustering'), 'use'] = False

# ----------------------------------------------------------------------------
# 3. Self-checks
# ----------------------------------------------------------------------------
# (a) two canonical names differing only by case/punctuation are almost certainly the same
#     antigen that the dictionary split by accident.
collisions = (mm[mm.use].assign(key=lambda d: d.canonical.map(panel.normalise))
                .groupby('key').canonical.unique())
collisions = {k: sorted(v) for k, v in collisions.items() if len(v) > 1}
if collisions:
    raise SystemExit(
        "DICTIONARY PROBLEM - these canonical names differ only by case/punctuation and are "
        "probably the same antigen:\n" + json.dumps(collisions, indent=2))

# (b) pairs that must never collapse into one marker (look-alike names, different antigens).
NEVER = panel.load_never_merge()
row_by_canon = DICT.set_index('canonical')
for a, b, why in NEVER:
    if a == b:
        raise SystemExit(f"never_merge.csv lists '{a}' against itself")
    if a not in row_by_canon.index or b not in row_by_canon.index:
        raise SystemExit(f"never_merge.csv names '{a}'/'{b}' but markers.csv has no such row")
    sa = {panel.normalise(s) for s in str(row_by_canon.loc[a, 'synonyms']).split('|') if s}
    sb = {panel.normalise(s) for s in str(row_by_canon.loc[b, 'synonyms']).split('|') if s}
    if sa & sb:
        raise SystemExit(f"NEVER-MERGE VIOLATION: '{a}' and '{b}' share the name(s) "
                         f"{sorted(sa & sb)}. {why}")

mm.to_csv(os.path.join(OUT, 'marker_map.csv'), index=False)

# ----------------------------------------------------------------------------
# 4. Merge - the only part that has to see every dataset at once
# ----------------------------------------------------------------------------
ORDER = [m.NAME for m in MODS]
ph = mm[mm.use]
sets = {c: set(g.canonical) for c, g in ph.groupby('cohort')}
allm = sorted(set().union(*sets.values()))
pm = pd.DataFrame({c: [k in sets[c] for k in allm] for c in ORDER}, index=allm).astype(int)
pm['n_cohorts'] = pm.sum(1)
pm = pm.sort_values(['n_cohorts'] + ORDER, ascending=False)

DISPLAY = dict(zip(DICT.canonical, DICT.display))
GENE    = dict(zip(DICT.canonical, DICT.gene_symbol))
pm.insert(0, 'display', [DISPLAY[i] for i in pm.index])
pm.to_csv(os.path.join(OUT, 'panel_matrix.csv'))

pair = pd.DataFrame(index=ORDER, columns=ORDER, dtype=int)
for a, b in itertools.product(ORDER, ORDER):
    pair.loc[a, b] = len(sets[a] & sets[b])

BACKBONE = sorted(pm.index[pm.n_cohorts >= 4])
UNION    = sorted(pm.index)

json.dump({'backbone': BACKBONE, 'union': UNION,
           'per_cohort': {c: sorted(s) for c, s in sets.items()},
           'display': {k: DISPLAY[k] for k in UNION},
           'gene_symbol': {k: GENE[k] for k in UNION},
           'naming': 'canonical = HGNC gene symbol; an underscore marks a documented pseudo-name'},
          open(os.path.join(OUT, 'panel.json'), 'w'), indent=2)


def lab(k):
    """'CD8A (CD8)' - canonical plus the familiar antibody name when they differ."""
    return f"{k} ({DISPLAY[k]})" if DISPLAY[k] != k else k


# ----------------------------------------------------------------------------
# 5. Report--- part need to be removed when the pipeline is run in a non-interactive environment
# ----------------------------------------------------------------------------
L = []
w = L.append
w("# STEP 1 - Panel harmonisation report\n")
w("Generated by `pipeline/step1_panel_harmonisation.py`. No cell data modified.\n")
w("**Naming: canonical name = HGNC gene symbol** (dictionary: `panel/markers.csv`). A name "
  "containing an underscore is a documented pseudo-name for an antibody that no single gene "
  "describes - `KRT_PAN`, `HLA_ABC`, `CEACAM5_6`, `PTPRC_RA`, `PTPRC_RO`, `H3_K9ac`, "
  "`H3_K27me3`, `RPS6_p`, `STAT3_p`. The familiar antibody name is kept as `display`.\n")

w("## 1. Columns in / out\n")
t = mm.groupby(['cohort', 'kind']).size().unstack(fill_value=0)
t['TOTAL'] = t.sum(1); t['USED'] = mm[mm.use].groupby('cohort').size()
t['DROPPED'] = t.TOTAL - t.USED
w(t.to_markdown() + "\n")

w("## 2. Every dropped column, with reason\n")
d = mm[~mm.use][['cohort', 'raw_column', 'antibody', 'kind', 'flag']].copy()
d['reason'] = np.where(d.flag != '', d.flag,
              np.where(d.kind == 'dna',            'DNA/nuclear channel - kept aside as segmentation QC, not a phenotype marker',
              np.where(d.kind == 'non_biological', 'elemental / instrument channel, not a protein stain',
              np.where(d.kind == 'qc_score',       'segmentation QC score, not a stain', '?'))))
w(d[['cohort', 'raw_column', 'antibody', 'reason']].to_markdown(index=False) + "\n")
w(f"\n**Total dropped: {len(d)} columns. Total kept: {int(mm.use.sum())} columns.**\n")

w("## 3. CRC naming convention - fixed\n")
w("`<antibody> - <paper description>:Cyc_<cycle>_ch_<channel>` is split into 3 fields inside "
  "`panel/cohorts/CRC.py`. The antibody goes to the dictionary; cycle/channel are kept as "
  "imaging provenance (markers from the same cycle share a bleaching/exposure batch).\n")
crc = mm[(mm.cohort == 'CRC') & mm.use][['raw_column', 'antibody', 'canonical', 'crc_cycle', 'crc_channel']]
w(crc.head(12).to_markdown(index=False) + "\n\n_(first 12 of "
  + str(len(crc)) + " - full list in `marker_map.csv`)_\n")

w("## 4. Name resolutions actually applied\n")
al = mm[mm.use][['cohort', 'antibody', 'canonical', 'display']].drop_duplicates()
al = al[al.antibody != al.canonical].sort_values(['canonical', 'cohort'])
grp = al.groupby(['canonical', 'display']).apply(
    lambda g: ', '.join(f"{r.cohort}:{r.antibody}" for r in g.itertuples()), include_groups=False)
w(pd.DataFrame({'canonical': [i[0] for i in grp.index],
                'display':   [i[1] for i in grp.index],
                'renamed from': grp.values}).to_markdown(index=False) + "\n")

w("\n> **Not a safe merge:** `Cytokeratin` (CRC), `Pan-Keratin` (Keren) and `PanCK` "
  "(UPMC, ferguson) are different antibody clones covering different keratin subsets. They are "
  "merged into `KRT_PAN`. Standard practice, but it is an assumption and must be stated in the "
  "write-up, not hidden.\n")
w("\n> **Deliberately NOT merged** (`panel/never_merge.csv`): "
  + "; ".join(f"`{a}` vs `{b}`" for a, b, _ in NEVER) + ".\n")

w("## 5. Panel overlap after harmonisation (usable phenotypic markers only)\n")
w("Per-cohort usable marker count:\n")
w(pd.DataFrame({'markers': {c: len(s) for c, s in sets.items()}}).to_markdown() + "\n")
w("\nPairwise shared:\n")
w(pair.to_markdown() + "\n")
w("\nMarkers by how many cohorts carry them:\n")
tier = pm.n_cohorts.value_counts().sort_index(ascending=False)
w(pd.DataFrame({'n_cohorts': tier.index, 'n_markers': tier.values,
                'cumulative': tier.values.cumsum()}).to_markdown(index=False) + "\n")
for n in range(len(ORDER), 0, -1):
    ms = sorted(pm.index[pm.n_cohorts == n])
    w(f"\n**in {n} cohorts ({len(ms)}):** "
      + (', '.join(lab(k) for k in ms) if n >= 3 else f"_{len(ms)} markers, see panel_matrix.csv_"))

w("\n\n## 6. Backbone definition used downstream\n")
w(f"- **BACKBONE ({len(BACKBONE)} markers, in >=4 cohorts)** - every model sees these:\n\n  "
  + ', '.join(lab(k) for k in BACKBONE) + "\n")
w(f"\n- **UNION ({len(UNION)} markers)** - the full input vector; a cohort that lacks a "
  "marker gets NaN + mask=0, never 0.\n")
w("\n> The backbone means \"in >= 4 of the loaded cohorts\". Adding a 6th dataset changes it, "
  "and results built on different backbones are not comparable. Freeze it before reporting "
  "numbers.\n")

open(os.path.join(OUT, 'step1_report.md'), 'w', encoding='utf-8').write('\n'.join(L))
print('\n'.join(L))
print("\n\nWROTE:", OUT)

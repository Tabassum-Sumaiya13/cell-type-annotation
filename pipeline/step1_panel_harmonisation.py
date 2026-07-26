"""
STEP 1 - Panel harmonisation.

Input : raw marker column names from all 5 cohorts
Output: harmonised/_audit/marker_map.csv      one row per (cohort, raw column)
        harmonised/_audit/panel_matrix.csv    canonical marker x cohort membership
        harmonised/_audit/step1_report.md     human-readable summary

No cell data is touched here. This step only decides:
  - what each column is really called   (alias resolution)
  - whether it is a phenotypic marker, a structural channel, or junk
Run before anything else.
"""
import pandas as pd, numpy as np, re, os, json, itertools

BASE = r"d:\Desktop\FYDP\FYDP final works\cell type annotation"
OUT  = os.path.join(BASE, "harmonised", "_audit")
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------------
# 1. Raw column names, exactly as they appear in each file
# ----------------------------------------------------------------------------
RAW = {
'Keren': ['C','Na','Si','P','Ca','Fe','dsDNA','Vimentin','SMA','Background','B7H3','FoxP3',
    'Lag3','CD4','CD16','CD56','OX40','PD1','CD31','PD-L1','EGFR','Ki67','CD209','CD11c',
    'CD138','CD163','CD68','CSF-1R','CD8','CD3','IDO','Keratin17','CD63','CD45RO','CD20',
    'p53','Beta catenin','HLA-DR','CD11b','CD45','H3K9ac','Pan-Keratin','H3K27me3',
    'phospho-S6','MPO','Keratin6','HLA_Class_1','Ta','Au'],
'ferguson': ['panCK','CD20','HH3','CD45RA','CD8a','podoplanin','CD16','CADM1','IDO','PDL1',
    'CD13','CD68','VISTA','CD31','CXCR3','pSTAT3','CCR7','CD14','FX111A','FoxP3','PD1',
    'CD45RO','OX40','NFKBp65','CD66a','Ki67','LAG3','CD3','granzB','PDL2','CD4','HLADR',
    'ICOS','TIM3','DNA1','DNA2'],
'UPMC': ['CD117','CD11b','CD11c','CD134','CD14','CD15','CD152','CD16','CD20','CD21','CD31',
    'CD34','CD38','CD3e','CD4','CD45','CD45RA','CD45RO','CD47','CD49f','CD56','CD57','CD68',
    'CD69','CD8','CollagenIV','FoxP3','GranzymeB','HLA-DR','ICOS','Ki67','PD1','PDL1','PanCK',
    'Podoplanin','TMEM16A','Vimentin','aSMA','p16'],
'HubMap': ['MUC2','SOX9','MUC1','CD31','Synapto','CD49f','CD15','CHGA','CDX2','ITLN1','CD4',
    'CD127','Vimentin','HLADR','CD8','CD11c','CD44','CD16','BCL2','CD3','CD123','CD38','CD90',
    'aSMA','CD21','NKG2D','CD66','CD57','CD206','CD68','CD34','aDef5','CD7','CD36','CD138',
    'CD45RO','Cytokeratin','CD117','CD19','Podoplanin','CD45','CD56','CD69','Ki67','CD49a',
    'CD163','CD161','OLFM4','FAP','CD25','CollIV','CK7','MUC6'],
'CRC': ['CD44 - stroma:Cyc_2_ch_2','FOXP3 - regulatory T cells:Cyc_2_ch_3',
    'CD8 - cytotoxic T cells:Cyc_3_ch_2','p53 - tumor suppressor:Cyc_3_ch_3',
    'GATA3 - Th2 helper T cells:Cyc_3_ch_4','CD45 - hematopoietic cells:Cyc_4_ch_2',
    'T-bet - Th1 cells:Cyc_4_ch_3','beta-catenin - Wnt signaling:Cyc_4_ch_4',
    'HLA-DR - MHC-II:Cyc_5_ch_2','PD-L1 - checkpoint:Cyc_5_ch_3','Ki67 - proliferation:Cyc_5_ch_4',
    'CD45RA - naive T cells:Cyc_6_ch_2','CD4 - T helper cells:Cyc_6_ch_3','CD21 - DCs:Cyc_6_ch_4',
    'MUC-1 - epithelia:Cyc_7_ch_2','CD30 - costimulator:Cyc_7_ch_3','CD2 - T cells:Cyc_7_ch_4',
    'Vimentin - cytoplasm:Cyc_8_ch_2','CD20 - B cells:Cyc_8_ch_3','LAG-3 - checkpoint:Cyc_8_ch_4',
    'Na-K-ATPase - membranes:Cyc_9_ch_2','CD5 - T cells:Cyc_9_ch_3','IDO-1 - metabolism:Cyc_9_ch_4',
    'Cytokeratin - epithelia:Cyc_10_ch_2','CD11b - macrophages:Cyc_10_ch_3',
    'CD56 - NK cells:Cyc_10_ch_4','aSMA - smooth muscle:Cyc_11_ch_2','BCL-2 - apoptosis:Cyc_11_ch_3',
    'CD25 - IL-2 Ra:Cyc_11_ch_4','CD11c - DCs:Cyc_12_ch_3','PD-1 - checkpoint:Cyc_12_ch_4',
    'Granzyme B - cytotoxicity:Cyc_13_ch_2','EGFR - signaling:Cyc_13_ch_3',
    'VISTA - costimulator:Cyc_13_ch_4','CD15 - granulocytes:Cyc_14_ch_2',
    'ICOS - costimulator:Cyc_14_ch_4','Synaptophysin - neuroendocrine:Cyc_15_ch_3',
    'GFAP - nerves:Cyc_16_ch_2','CD7 - T cells:Cyc_16_ch_3','CD3 - T cells:Cyc_16_ch_4',
    'Chromogranin A - neuroendocrine:Cyc_17_ch_2','CD163 - macrophages:Cyc_17_ch_3',
    'CD45RO - memory cells:Cyc_18_ch_3','CD68 - macrophages:Cyc_18_ch_4',
    'CD31 - vasculature:Cyc_19_ch_3','Podoplanin - lymphatics:Cyc_19_ch_4',
    'CD34 - vasculature:Cyc_20_ch_3','CD38 - multifunctional:Cyc_20_ch_4',
    'CD138 - plasma cells:Cyc_21_ch_3','HOECHST1:Cyc_1_ch_1',
    'CDX2 - intestinal epithelia:Cyc_2_ch_4','Collagen IV - bas. memb.:Cyc_12_ch_2',
    'CD194 - CCR4 chemokine R:Cyc_14_ch_3','MMP9 - matrix metalloproteinase:Cyc_15_ch_2',
    'CD71 - transferrin R:Cyc_15_ch_4','CD57 - NK cells:Cyc_17_ch_4',
    'MMP12 - matrix metalloproteinase:Cyc_21_ch_4','DRAQ5:Cyc_23_ch_4','Profile_Homogeneity:Fiter1'],
}

# ----------------------------------------------------------------------------
# 2. CRC naming convention fix
#    'CD8 - cytotoxic T cells:Cyc_3_ch_2'  ->  antibody 'CD8', cycle 3, channel 2
#    The cycle/channel is imaging provenance and is kept as metadata, not in the name.
# ----------------------------------------------------------------------------
def parse_crc(col):
    body, _, cyc = col.partition(':')
    ab = body.split(' - ')[0].strip()
    desc = body.split(' - ')[1].strip() if ' - ' in body else ''
    m = re.match(r'Cyc_(\d+)_ch_(\d+)', cyc)
    return ab, desc, (int(m.group(1)) if m else None), (int(m.group(2)) if m else None)

# ----------------------------------------------------------------------------
# 3. Alias table -> canonical antibody name
# ----------------------------------------------------------------------------
ALIAS = {
  # keratins  (NOTE: different clones, merged by convention - flagged below)
  'pan-keratin':'PanCK','panck':'PanCK','cytokeratin':'PanCK',
  # CD naming variants
  'cd8a':'CD8','cd3e':'CD3','sma':'aSMA','a-sma':'aSMA','asma':'aSMA',
  # NOT merged on purpose: ferguson 'CD66a' (=CEACAM1) vs HubMap 'CD66' (epithelial
  # CEACAM5/6, it defines their 'CD66+ Enterocyte' class). Different antigens.
  'foxp3':'FoxP3',   # CRC writes FOXP3, everyone else FoxP3
  # checkpoint / functional
  'pd-l1':'PDL1','pdl1':'PDL1','pd-1':'PD1','pd1':'PD1','lag-3':'LAG3','lag3':'LAG3',
  'ido-1':'IDO','ido':'IDO','granzyme b':'GranzymeB','granzb':'GranzymeB','granzymeb':'GranzymeB',
  # MHC
  'hla-dr':'HLA-DR','hladr':'HLA-DR','hla_class_1':'HLA-ABC',
  # structural / other
  'beta catenin':'bCatenin','beta-catenin':'bCatenin','bcl-2':'BCL2','bcl2':'BCL2',
  'collagen iv':'CollagenIV','collageniv':'CollagenIV','colliv':'CollagenIV',
  'na-k-atpase':'NaKATPase','podoplanin':'Podoplanin',
  'synapto':'Synaptophysin','synaptophysin':'Synaptophysin',
  'chga':'ChromograninA','chromogranin a':'ChromograninA',
  'muc-1':'MUC1','muc1':'MUC1','keratin17':'KRT17','keratin6':'KRT6','ck7':'KRT7',
  'csf-1r':'CSF1R','t-bet':'TBET','phospho-s6':'pS6','pstat3':'pSTAT3','nfkbp65':'NFKBp65',
  'cd194':'CCR4',
}
# channels that are DNA / nuclear, used for segmentation - not phenotype
DNA = {'dsdna','hh3','dna1','dna2','hoechst1','draq5'}
# channels that are not proteins at all
NONBIO = {'na','si','p','ca','fe','ta','au','background','c'}
# columns that are QC scores, not stains
QC = {'profile_homogeneity'}

def canonical(name):
    k = name.strip().lower()
    if k in ALIAS: return ALIAS[k], 'phenotypic'
    if k in DNA:   return name.strip(), 'dna'
    if k in NONBIO:return name.strip(), 'non_biological'
    if k in QC:    return name.strip(), 'qc_score'
    return name.strip(), 'phenotypic'

# per-cohort measured problems found in the data audit (Part 1)
FLAGS = {
 ('Keren','C'):            'dead channel - every value is exactly 0',
 ('Keren','CD56'):         'near-constant: median == p99, only a few positive cells',
 ('Keren','CD163'):        'near-constant: median == p99, only a few positive cells',
 ('Keren','OX40'):         'near-constant: median == p99, only a few positive cells',
 ('ferguson','CXCR3'):     'median 29.25 = 45x the next marker - possible channel bleed',
 ('HubMap','OLFM4'):       'captured but NOT used for clustering (README); mostly NaN',
 ('HubMap','FAP'):         'captured but NOT used for clustering (README); mostly NaN',
 ('HubMap','CD25'):        'captured but NOT used for clustering (README); mostly NaN',
 ('HubMap','CollIV'):      'captured but NOT used for clustering (README); mostly NaN',
 ('HubMap','CK7'):         'captured but NOT used for clustering (README); mostly NaN',
 ('HubMap','MUC6'):        'captured but NOT used for clustering (README); B009-B012 only',
}

# ----------------------------------------------------------------------------
# 4. Build the map
# ----------------------------------------------------------------------------
rows = []
for cohort, cols in RAW.items():
    for col in cols:
        if cohort == 'CRC':
            ab, desc, cyc, ch = parse_crc(col)
        else:
            ab, desc, cyc, ch = col, '', None, None
        canon, kind = canonical(ab)
        rows.append(dict(cohort=cohort, raw_column=col, antibody=ab, canonical=canon,
                         kind=kind, crc_cycle=cyc, crc_channel=ch, paper_description=desc,
                         flag=FLAGS.get((cohort, ab), '')))
mm = pd.DataFrame(rows)

# merge DNA channels into one canonical name so they can be compared across cohorts
mm.loc[mm.kind == 'dna', 'canonical'] = 'DNA'
# 'use' = will this column enter the model?
mm['use'] = mm.kind.eq('phenotypic')
mm.loc[mm.flag.str.startswith('dead'), 'use'] = False
mm.loc[mm.flag.str.contains('near-constant'), 'use'] = False   # review flag, default off
mm.loc[mm.flag.str.contains('NOT used for clustering'), 'use'] = False

# --- self-check: two canonical names that differ only by case/punctuation are almost
# certainly the same antigen that the alias table missed. This caught FOXP3 vs FoxP3.
def squash(s): return re.sub(r'[^a-z0-9]', '', s.lower())
collisions = (mm[mm.use].assign(key=lambda d: d.canonical.map(squash))
                .groupby('key').canonical.unique())
collisions = {k: list(v) for k, v in collisions.items() if len(v) > 1}
if collisions:
    raise SystemExit(
        "ALIAS TABLE INCOMPLETE - these canonical names differ only by case/punctuation "
        "and are probably the same antigen. Add them to ALIAS and re-run:\n"
        + json.dumps(collisions, indent=2))

mm.to_csv(os.path.join(OUT, 'marker_map.csv'), index=False)

# ----------------------------------------------------------------------------
# 5. Panel membership matrix over usable phenotypic markers
# ----------------------------------------------------------------------------
ph = mm[mm.use]
sets = {c: set(g.canonical) for c, g in ph.groupby('cohort')}
allm = sorted(set().union(*sets.values()))
pm = pd.DataFrame({c: [m in sets[c] for m in allm] for c in RAW}, index=allm).astype(int)
pm['n_cohorts'] = pm.sum(1)
pm = pm.sort_values(['n_cohorts'] + list(RAW), ascending=False)
pm.to_csv(os.path.join(OUT, 'panel_matrix.csv'))

pair = pd.DataFrame(index=list(RAW), columns=list(RAW), dtype=int)
for a, b in itertools.product(RAW, RAW):
    pair.loc[a, b] = len(sets[a] & sets[b])

# ----------------------------------------------------------------------------
# 6. Report
# ----------------------------------------------------------------------------
L = []
w = L.append
w("# STEP 1 - Panel harmonisation report\n")
w("Generated by `pipeline/step1_panel_harmonisation.py`. No cell data modified.\n")

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
w("`<antibody> - <paper description>:Cyc_<cycle>_ch_<channel>` is split into 3 fields. "
  "The antibody becomes the column name; cycle/channel are kept as imaging provenance "
  "(useful later: markers from the same cycle share a bleaching/exposure batch).\n")
crc = mm[(mm.cohort == 'CRC') & mm.use][['raw_column', 'antibody', 'canonical', 'crc_cycle', 'crc_channel']]
w(crc.head(12).to_markdown(index=False) + "\n\n_(first 12 of "
  + str(len(crc)) + " - full list in `marker_map.csv`)_\n")

w("## 4. Alias resolutions actually applied\n")
al = mm[mm.antibody.str.lower().isin(ALIAS)][['cohort', 'antibody', 'canonical']].drop_duplicates()
al = al.sort_values(['canonical', 'cohort'])
grp = al.groupby('canonical').apply(
    lambda g: ', '.join(f"{r.cohort}:{r.antibody}" for r in g.itertuples()), include_groups=False)
w(pd.DataFrame({'canonical': grp.index, 'merged from': grp.values}).to_markdown(index=False) + "\n")

w("\n> **Not a safe merge:** `Cytokeratin` (CRC), `Pan-Keratin` (Keren) and `PanCK` "
  "(UPMC, ferguson) are different antibody clones covering different keratin subsets. "
  "Merging them is standard practice but it is an assumption and must be stated in the "
  "write-up, not hidden.\n")

w("## 5. Panel overlap after harmonisation (usable phenotypic markers only)\n")
w("Per-cohort usable marker count:\n")
w(pd.DataFrame({'markers': {c: len(s) for c, s in sets.items()}}).to_markdown() + "\n")
w("\nPairwise shared:\n")
w(pair.to_markdown() + "\n")
w("\nMarkers by how many cohorts carry them:\n")
tier = pm.n_cohorts.value_counts().sort_index(ascending=False)
w(pd.DataFrame({'n_cohorts': tier.index, 'n_markers': tier.values,
                'cumulative': tier.values.cumsum()}).to_markdown(index=False) + "\n")
for n in range(5, 0, -1):
    ms = sorted(pm.index[pm.n_cohorts == n])
    w(f"\n**in {n} cohorts ({len(ms)}):** " + (', '.join(ms) if n >= 3 else f"_{len(ms)} markers, see panel_matrix.csv_"))
w("\n\n## 6. Backbone definition used downstream\n")
BACKBONE = sorted(pm.index[pm.n_cohorts >= 4])
UNION    = sorted(pm.index)
w(f"- **BACKBONE ({len(BACKBONE)} markers, in >=4 cohorts)** - every model sees these:\n\n  "
  + ', '.join(BACKBONE) + "\n")
w(f"\n- **UNION ({len(UNION)} markers)** - the full input vector; a cohort that lacks a "
  "marker gets NaN + mask=0, never 0.\n")
json.dump({'backbone': BACKBONE, 'union': UNION,
           'per_cohort': {c: sorted(s) for c, s in sets.items()}},
          open(os.path.join(OUT, 'panel.json'), 'w'), indent=2)

open(os.path.join(OUT, 'step1_report.md'), 'w', encoding='utf-8').write('\n'.join(L))
print('\n'.join(L))
print("\n\nWROTE:", OUT)

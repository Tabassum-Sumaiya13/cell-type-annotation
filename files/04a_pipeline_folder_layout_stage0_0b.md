4. Current Accepted Pipeline
Order is marker names (0b) → rank values (1) → label alignment (1b) → tokens (2) → encoder (3) → training (6) → evaluation (7). Note the reorder: label alignment needs harmonised marker values, so it moves after Stage 1.

4.1 Folder layout

pipeline2/
  config.py            cohort registry: paths, µm/px, column names, arrival state
  loaders.py           ONE generic loader, no cohort branching
  panel/
    complexes.csv          HLA-DR, pan-keratin, Collagen IV, DNA stains
    never_merge.csv        9 pairs — an ASSERTION on the resolver, not an override
    must_merge.csv         5 positive-direction assertions
    manual_overrides.csv   the ~20 the API could not settle
    gate1_expect.csv       Stage 1 declared assertions
    gate1b_expect.csv      Stage 1b declared hard cases
  acquire/             one download + extraction script per new cohort
  s0_audit.py          Stage 0   acquire + audit                    ✅
  s0b_markers.py       Stage 0b  marker NAME harmonisation          ✅
  s1_values.py         Stage 1   rank + continuous encoder          ✅
  s1b_labels.py        Stage 1b  automatic label alignment          ✅
  s2_tokens.py         Stage 2                                      ⚪ designed, not written
  s3_encoder.py        Stage 3                                      ⚪
  s4_spatial.py        Stage 4                                      ❌ DEFERRED
  s6_train.py          Stage 6                                      ⚪
  s7_eval.py           Stage 7                                      ⚪
  nn/
    marker_encoder.py  MarkerEncoder, FiLMScalar, FiLMMLP, MaskedMarkerProbe   ✅
    tokens.py          Stage 2 token module + set transformer       ⚪
work/
  raw/*.parquet            Stage 0 output
  marker_registry.csv      AUTO-GENERATED, API-cached (259 rows × 12 cols)
  api_cache.json           1.58 MB, makes runs offline + reproducible
  values/{c}.parquet       Stage 1 stratified 40k draw, 9 core markers
  values/{c}_rand.parquet  Stage 1 UNSTRATIFIED draw (distribution checks only)
  values/{c}_slidestats.parquet   per-slide med/iqr, standardised within cohort
  s1_folds.pt              7.4 MB
  s1b_signatures.npz       957 KB — QT, MEAN, nodes, co-expression
  label_map.csv            AUTO-GENERATED (cohort, native_label) -> cluster. Never hand-edited
  label_graph.json         nesting DAG
  prototypes.npy           cluster prototype vectors for Stage 6
reports/                   one markdown report per stage — the deliverable
  s0_audit.md  s0b_markers.md  s1_normalisation.md  s1b_labels.md
  figures/
_validation/
  extract_hand_mapping.py       reads T and NAT from git via ast.literal_eval
  hand_mapping_reference.csv    71 labels, 4 cohorts, 26 targets, 10 L2, 4 L1, 5 dropped
One thing comes out of git, and it is now a test rather than an input: git show HEAD:pipeline/panel/never_merge.csv — 9 look-alike pairs that must stay separate. With the triple key these stay apart automatically, so the file is an assertion that Stage 0b is working. The old markers.csv synonym list is not carried over.

4.2 Stage 0 — Acquire + audit ✅ PASS
Purpose. Download and load every cohort into one standard table so no downstream code branches on cohort.

Input. Datasets/ (8.2 GB on disk).
Output. work/raw/{cohort}.parquet, work/raw/{cohort}_meta.json, reports/s0_audit.md.

Standard table: cell_id, cohort, image_id, patient_id, x_px, y_px, area_px2, native_label, label_confidence, <raw markers…>.

Key design decision — declarative registry, generic loader. Everything cohort-specific lives in config.py as a dict. There is no if cohort == "X" anywhere else in the codebase. Adding a dataset means adding a dict, not editing code. Marker columns are declared by rule, never hand-listed:

{'kind': 'pattern', 'regex': ...} — columns whose name matches
{'kind': 'file', 'path': ...} — one marker name per line
{'kind': 'exclude', 'cols': [...]} — everything except these
Key design decision — Stage 0 keeps EVERY column and EVERY cell. It does not decide what is a real protein (DNA stains, elemental channels) or a real cell (dirt, undefined). Those calls are made later on evidence by Stage 0b's resolver and Stage 1b's coherence check. This decision was vindicated — Stage 1b's junk labels collected correctly in the negative-definition cluster rather than being silently dropped.

Gate 0 verdict: PASS. Zero missing coordinates, areas or patient ids in any cohort. All six tissue plots look like real tissue (rectangular acquisitions for CRC/Keren/UPMC, round TMA cores for Phillips/ferguson/Sorin) — no grids, lines or blobs. Pixel sizes confirmed by measured extent (§3.2).

Sorin required writing feature extraction. It ships no cell table at all: only MATLAB masks, per-cell types, and 18-frame marker TIFFs. pipeline2/acquire/sorin_extract.py computes per-cell centroid, area and per-channel mean from the labelled masks. All 536 images, 0 skipped, 278 s, 20 empty labels out of 2.14M (0.001%). Its labels are the most fine-grained in the roster (Tc/Th/Treg, Cl Mo/Int Mo/Non-Cl Mo, Cl MAC/Alt MAC) — good material for Stage 1b nesting.

Known weakness. UPMC's µm/px is assumed, not published.

4.3 Stage 0b — Marker identity resolution ✅ GATE 0b: PASS
Purpose. Resolve every marker column to a stable database identifier so that 'CD8 - cytotoxic T cells:Cyc_3_ch_2', 'CD8a' and 'CD8' land on the same thing without string matching.

Input. work/raw/*_meta.json marker column lists.
Output. work/marker_registry.csv (259 rows), work/api_cache.json, reports/s0b_markers.md.

The canonical key is a triple, not a name:


(gene_or_complex_id, epitope, modification)

CD45    → (HGNC:9666 PTPRC, pan, none)
CD45RA  → (HGNC:9666 PTPRC, RA,  none)
CD45RO  → (HGNC:9666 PTPRC, RO,  none)
RPS6_p  → (HGNC:10429 RPS6, pan, phospho)
HLA-DR  → (COMPLEX:HLA-DR → [HLA-DRA, HLA-DRB1…], pan, none)
PanCK   → (FAMILY:KRT_PAN → [KRT1…KRT20], pan, none)
Why a triple. Resolving to a gene alone would merge CD45 / CD45RA / CD45RO (all PTPRC) and merge phospho-RPS6 with total RPS6 — exactly the pairs in never_merge.csv. With the triple they stay apart by construction, demoting never_merge.csv from a hand-maintained blacklist to an assertion that the resolver works.

Resolution order (each step field-scoped, never free-text):

Normalise the raw column — strip cohort decoration, punctuation, case-fold.
Split off epitope (RA, RO, isoform tags) and modification (_p, phospho).
HGNC REST (rest.genenames.org, free, no key), in order: /fetch/symbol/X → /search/alias_symbol/X → /search/prev_symbol/X. Try with and without hyphens; require all spellings to agree.
UniProt REST (rest.uniprot.org, reviewed + human only) for protein-level names HGNC misses.
CD-number table for CD antigens.
Complex / family table for things that are genuinely not one gene.
Anything ambiguous or zero-hit → review queue. Never guessed, never dropped.
Registry schema (12 columns): cohort, raw_column, stripped, core, epitope, modification, resolved_id, gene, kind, source, note, triple.

Gate 0b — all five checks pass on 259 marker columns:

Check	Result
Auto-resolved coverage	100% (target ≥90%) — review queue empty
Beats verbatim matching	43 → 59 shared markers (+16)
never_merge all distinct	9/9 pass
must_merge all unified	5/5 pass
No non-protein resolved to a gene	0 leaks
Offline re-run	byte-identical (503 cache hits, 0 network calls)
Backbone: 26 markers in ≥4 cohorts, up from the old pipeline's 19. Nine markers are in all six cohorts and form a clean lineage core: CD4 CD8A COMPLEX:CD3 MS4A1(CD20) CD68 FOXP3 COMPLEX:HLA-DR FAMILY:KRT_PAN PECAM1(CD31).

Resolution sources: HGNC symbol 83 · HGNC alias 53 · complex table 47 · HGNC prev 39 · manual 20 · UniProt 17. Of 259 columns: 212 protein, 31 complex/family, 16 non-protein.

Panel geometry (measured, protein/complex only — 242 columns, 99 distinct triples):

per-cohort panel size		triples by #cohorts	
CRC	56	in 6 cohorts	9
Phillips	57	in 5	5
Keren	39	in 4	12
UPMC	39	in 3	12
ferguson	34	in 2	18
Sorin	17	in 1	43
Union panel = 99 triples. Shared by ≥2 cohorts = 56. Shared by ≥3 = 38. Zero duplicate (cohort, triple) pairs in the current roster.

Evidence the resolver was needed (real API calls, not assumed):

Query	Result	Lesson
search/CD152	CTLA4	API resolves what strings cannot
search/CD45	PTPRC	ditto
free-text search/PD-1	PSMA6, PSMB6, PDCD1 (3rd)	top-hit-wins is wrong
search/alias_symbol/PD-1	PDCD1 only	field-scoping fixes it
search/alias_symbol/PD1	3 hits, ambiguous	punctuation changes the answer → require agreement
search/alias_symbol/HLA-DR	0 hits	it is a complex, needs the family table
search/CD45RO	0 hits	it is an epitope, needs the triple key
aSMA	0 hits	informal name → normalise, then UniProt, else review
never_merge proved the triple key structurally:

pair	triple A	triple B
CD45 / CD45RA / CD45RO	HGNC:9666|pan|none	HGNC:9666|RA|none · HGNC:9666|RO|none
Pan-Keratin / Keratin17	FAMILY:KRT_PAN|pan|none	HGNC:6427|pan|none
H3K9ac / H3K27me3	FAMILY:H3|K9ac|none	FAMILY:H3|K27me3|none
phospho-S6 / pSTAT3	HGNC:10429|pan|phospho	HGNC:11364|pan|phospho
B7H3 / H3K9ac (deliberate trap)	HGNC:19137|pan|none (CD276)	FAMILY:H3|K9ac|none
must_merge proved the positive direction — hardest case: six spellings of pan-cytokeratin across six cohorts (Cytokeratin - epithelia:Cyc_10_ch_2 · Cytokeratin · Pan-Keratin · Pancytokeratin · PanCK · panCK) all collapse to one triple. Also three spellings of beta-catenin, which no HGNC query resolves — UniProt carried it.

Judgement calls, written into complexes.csv where they are visible:

CD3 ≡ CD3e. UPMC names it CD3e, five cohorts name it CD3, no cohort carries both. In multiplex imaging the pan-CD3 reagent is in practice anti-CD3ε. Keeping them apart would strand UPMC's only pan-T-cell marker.
CD16 → COMPLEX:CD16 (FCGR3A|FCGR3B). UniProt returns both and the antibody generally does not separate NK from neutrophil forms, so it is recorded as a complex rather than guessed.
Non-proteins are flagged, never forced: MIBI elemental channels (Au, Ta, Na, C, Si, P, Ca, Fe), DNA stains (HOECHST1, DRAQ5, DNA1, dsDNA, HH3, Nuc), instrument artefacts (Background, X140empty). They stay in the table with a non_protein flag so later stages exclude them on evidence rather than by a hidden list.

Honest scope statement. This does not remove human judgement — it shrinks it from "hand-map ~120 marker names across 8 cohorts" to "confirm the ~20 the resolver flags", and it produces a citable stable id (HGNC:2505, UniProt:P35222) instead of a project-local string.

Known weakness / open item. The plan states Stage 0b "also computes a per-(cohort, marker) dynamic-range score, used in Stage 2." It does not. There is no such column in marker_registry.csv. Stage 2 must compute it (see §4.6).


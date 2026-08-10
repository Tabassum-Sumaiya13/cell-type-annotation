# Stage 0b - Marker identity resolution (GATE 0b)

**259 marker columns** across 6 cohorts, **180 distinct raw names**.

Cache: 503 hits, 0 network calls.

## 1. Resolution coverage

| outcome                              |   n_columns |   share_% |
|:-------------------------------------|------------:|----------:|
| protein (gene id)                    |         211 |      81.5 |
| complex / family                     |          31 |      12   |
| non-protein (dye, element, artefact) |          17 |       6.6 |
| UNRESOLVED                           |           0 |       0   |

**Auto-resolved: 259/259 = 100.0%** (target >= 90%).


By source:

| source        |   columns |
|:--------------|----------:|
| hgnc_symbol   |        83 |
| hgnc_alias    |        53 |
| complex_table |        48 |
| hgnc_prev     |        38 |
| manual        |        20 |
| uniprot       |        17 |

## 2. Does resolution beat naive string matching?

| method            |   distinct markers |   shared by >=2 cohorts |
|:------------------|-------------------:|------------------------:|
| verbatim raw name |                180 |                      43 |
| resolved triple   |                111 |                      59 |

**Shared markers: 43 -> 59 (+16).**


## 3. `never_merge` - must resolve to DIFFERENT triples

| a           | b         | triple_a                | triple_b               | status   |
|:------------|:----------|:------------------------|:-----------------------|:---------|
| CD45        | CD45RA    | HGNC:9666|pan|none      | HGNC:9666|RA|none      | PASS     |
| CD45        | CD45RO    | HGNC:9666|pan|none      | HGNC:9666|RO|none      | PASS     |
| CD45RA      | CD45RO    | HGNC:9666|RA|none       | HGNC:9666|RO|none      | PASS     |
| Pan-Keratin | Keratin17 | FAMILY:KRT_PAN|pan|none | HGNC:6427|pan|none     | PASS     |
| Pan-Keratin | Keratin6  | FAMILY:KRT_PAN|pan|none | HGNC:6443|pan|none     | PASS     |
| H3K9ac      | H3K27me3  | FAMILY:H3|K9ac|none     | FAMILY:H3|K27me3|none  | PASS     |
| phospho-S6  | pSTAT3    | HGNC:10429|pan|phospho  | HGNC:11364|pan|phospho | PASS     |
| B7H3        | H3K9ac    | HGNC:19137|pan|none     | FAMILY:H3|K9ac|none    | PASS     |
| CD66a       | CD16      | HGNC:1814|pan|none      | COMPLEX:CD16|pan|none  | PASS     |

**9/9 pass, 0 fail.**


## 3b. `must_merge` - different spellings that must resolve to the SAME triple

| group   |   in_data |   of |   distinct_triples | status   | triples                 |
|:--------|----------:|-----:|-------------------:|:---------|:------------------------|
| KRT_PAN |         6 |    6 |                  1 | PASS     | FAMILY:KRT_PAN|pan|none |
| CTNNB1  |         3 |    3 |                  1 | PASS     | HGNC:2514|pan|none      |
| PTPRC   |         2 |    2 |                  1 | PASS     | HGNC:9666|pan|none      |
| CD8A    |         3 |    3 |                  1 | PASS     | HGNC:1706|pan|none      |
| HLA-DR  |         4 |    4 |                  1 | PASS     | COMPLEX:HLA-DR|pan|none |

## 3c. Non-protein channels must not resolve to genes

A regression guard. `Na` (sodium) once resolved to the gene **XK**, whose *previous* HGNC symbol is literally `NA` — reached because pandas had parsed the string "NA" in the table as a missing value. A silently wrong marker id is the worst failure this stage can produce, so it is now asserted rather than eyeballed.

_22 declared non-protein names checked; none resolved to a gene._

## 4. Marker x cohort availability

|   present in >= N cohorts |   markers |
|--------------------------:|----------:|
|                         6 |         9 |
|                         5 |        14 |
|                         4 |        26 |
|                         3 |        38 |
|                         2 |        56 |

The old 5-cohort pipeline's backbone was **19** markers in >=4 cohorts. Here: **26**.


Markers present in every cohort:

`CD4`, `CD68`, `CD8A`, `COMPLEX:CD3`, `COMPLEX:HLA-DR`, `FAMILY:KRT_PAN`, `FOXP3`, `MS4A1`, `PECAM1`

## 5. Review queue - unresolved, never guessed

_empty - everything resolved._

## 6. Non-proteins - flagged, not forced

These stay in the table with a `non_protein` kind so Stage 1b can exclude them on evidence rather than by a hidden hard-coded list.

| resolved_id         | raw columns              |
|:--------------------|:-------------------------|
| ARTEFACT:BACKGROUND | Background               |
| DYE:DNA             | DNA1, DNA2, dsDNA        |
| DYE:DRAQ5           | DRAQ5, DRAQ5:Cyc_23_ch_4 |
| DYE:HOECHST         | HOECHST1:Cyc_1_ch_1      |
| ELEMENT:AU          | Au                       |
| ELEMENT:C           | C                        |
| ELEMENT:CA          | Ca                       |
| ELEMENT:FE          | Fe                       |
| ELEMENT:NA          | Na                       |
| ELEMENT:P           | P                        |
| ELEMENT:SI          | Si                       |
| ELEMENT:TA          | Ta                       |

## Verdict

| check                                     | result   | value      |
|:------------------------------------------|:---------|:-----------|
| coverage >= 90%                           | PASS     | 100.0%     |
| resolution beats verbatim (43)            | PASS     | 43 -> 59   |
| never_merge: all pairs distinct           | PASS     | 0 failures |
| must_merge: all groups unified            | PASS     | 0 failures |
| no non-protein channel resolved to a gene | PASS     | 0 leaks    |

**GATE 0b: PASS**

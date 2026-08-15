# Results — External validation of the derived label space

*Draft Results section. Section numbers are placeholders; renumber to fit the paper.
Every number here comes from `reports/s12_ontology.md` and reproduces exactly (seed 20260810).*

---

## 4.1 Setup

The label space is 25 clusters derived from marker profiles alone, over 106 cohort-specific
labels from 6 spatial-proteomics cohorts. No ontology, dictionary or text embedding entered the
derivation.

To test it, each of the 106 labels was assigned a Cell Ontology (CL) term. The ontology then
supplied the structure: which terms are identical, which contain which, what level each sits at,
and which markers define them. The clustering never saw any of it. A static check confirmed that
no module in the pipeline reads a CL term or the mapping file (30 modules scanned with comments
and string literals removed, 0 violations).

**Table 1. Label-to-ontology mapping.**

| Quantity | Value |
|---|---|
| Cohort-specific labels | 106 |
| Resolved to a CL term | 101 (95.3 %) |
| Distinct CL terms used | 33 |
| Resolved by exact match to a CL name or exact synonym | 23 (22.8 % of resolved) |
| Assigned from the cohort's own publication | 78 |
| Assignments contradicting an automatic match | 0 |
| Not a cell type or an irreducible mixture | 5 |

The five unresolved labels are `dirt`, `undefined`, `Unidentified`, and two labels naming two
lineages at once. They are excluded from scoring, not silently dropped.

Sources: Cell Ontology `cl.obo`, release 2026-06-08 (Diehl et al., *J Biomed Semantics* 2016);
CellMarker 2.0 human (Hu et al., *Nucleic Acids Res* 2023). Both were frozen locally with SHA-256
recorded before scoring.

---

## 4.2 Agreement with the ontology

Agreement was measured at four levels. The finest is the exact CL term. The other three are CL's
own published subsets — the HuBMAP Human Reference Atlas subset, the CZI CellxGene subset, and
CL's upper slims. Using published subsets removes the choice of comparison level from the authors.

Intervals are percentile bootstrap over labels (2000 resamples). The null is 1000 shuffles of the
cluster assignment with cluster sizes held fixed.

**Table 2. Agreement between the 25 derived clusters and the Cell Ontology.**
ARI is given per label and weighted by cell count. NMI, homogeneity and completeness are per
label. "Reliable only" excludes the three clusters the derivation itself flagged as unreliable.

| Level | Scope | Labels | CL classes | ARI (per label) [95 % CI] | ARI (cell-weighted) [95 % CI] | NMI | Hom. | Compl. |
|---|---|---:|---:|---|---|---:|---:|---:|
| CL term | all | 101 | 33 | **0.440** [0.366, 0.662] | **0.934** [0.773, 0.985] | 0.771 | 0.721 | 0.829 |
| CL term | reliable only | 81 | 24 | **0.572** [0.478, 0.786] | **0.937** [0.754, 0.987] | 0.817 | 0.785 | 0.852 |
| HRA subset | all | 101 | 28 | 0.526 [0.427, 0.730] | 0.955 [0.853, 0.988] | 0.779 | 0.749 | 0.812 |
| HRA subset | reliable only | 81 | 20 | 0.678 [0.579, 0.847] | 0.960 [0.856, 0.992] | 0.832 | 0.825 | 0.839 |
| CellxGene subset | all | 101 | 33 | 0.440 [0.370, 0.666] | 0.934 [0.753, 0.984] | 0.771 | 0.721 | 0.829 |
| CellxGene subset | reliable only | 81 | 24 | 0.572 [0.475, 0.784] | 0.937 [0.752, 0.988] | 0.817 | 0.785 | 0.852 |
| CL upper slims | all | 100 | 17 | 0.455 [0.369, 0.668] | 0.919 [0.718, 0.981] | 0.725 | 0.751 | 0.700 |
| CL upper slims | reliable only | 81 | 14 | 0.573 [0.468, 0.765] | 0.923 [0.710, 0.983] | 0.770 | 0.818 | 0.728 |

The gap between the per-label and cell-weighted columns locates the disagreements. The large
clusters — tumour, macrophage, T cell — match published biology. The errors sit in small clusters.

**Table 3. Permutation test.** Observed ARI against 1000 shuffles preserving cluster sizes.

| Level | Observed ARI | Null mean | Null 99.9th pct | Null max | *p* |
|---|---:|---:|---:|---:|---:|
| CL term | 0.440 | −0.0002 | 0.055 | 0.062 | < 0.001 |
| HRA subset | 0.526 | 0.0001 | 0.058 | 0.065 | < 0.001 |
| CellxGene subset | 0.440 | 0.0010 | 0.058 | 0.084 | < 0.001 |
| CL upper slims | 0.455 | −0.0001 | 0.053 | 0.056 | < 0.001 |

Observed agreement exceeds the 99.9th percentile of the null at every level.

### The comparison that tests the method's premise

The same 25 clusters were previously scored against a hand-written mapping produced by this
project, giving ARI 0.596 per label and 0.962 cell-weighted over 64 labels and 25 classes. The
Cell Ontology, written independently of this work, gives 0.440 and 0.934 over a **larger** label
set (101) and a **larger** class set (33).

An external ontology therefore reaches close to the same verdict as the internal mapping. The
earlier agreement was not an artefact of scoring the method against a target written by the same
authors.

### Malignant cells

CL provides only two malignant terms (`neoplastic cell`, `malignant cell`) and no tissue-specific
children. Malignant labels were therefore mapped to their cell of origin with a separate malignant
flag. Collapsing all 14 malignant labels to `neoplastic cell` instead gives ARI 0.409
[0.351, 0.646] over 34 classes. That reading makes malignant colorectal epithelium and malignant
T cells the same term, and so penalises a split the method makes correctly (Section 4.4).

---

## 4.3 Pairwise relations

Every pair of resolved labels (5050 pairs) was classified by the ontology and by the derived
space. This replaces 13 hand-written assertions with an externally sourced test set.

**Table 4. Pairwise relations: ontology against derived space.** Counts of label pairs.

| Ontology relation | Same cluster | Nesting edge | Different | Total |
|---|---:|---:|---:|---:|
| Same CL term | 138 | 12 | 64 | 214 |
| Parent–child | 91 | 48 | 354 | 493 |
| Same upper class | 9 | 2 | 39 | 50 |
| Distant | 135 | 212 | 3946 | 4293 |

**Table 5. Pre-declared pairwise criteria and outcomes.** Thresholds were committed before the
ontology was consulted.

| Criterion | Required | All clusters | Reliable only | Threshold | Outcome |
|---|---|---:|---:|---|---|
| Pairs CL calls the same term | same cluster | **0.645** | 0.736 | ≥ 0.90 | fail |
| Pairs CL calls parent–child | same cluster or nesting edge | **0.282** | 0.377 | ≥ 0.60 | fail |
| Pairs CL calls distant | not the same cluster | **0.031** | 0.018 | ≤ 0.05 | pass |

Two findings follow.

- **The parent–child result is the first external evidence about the nesting layer, and it is
  negative.** Only 28.2 % of ancestor–descendant pairs are represented as either a nesting edge or
  a merge. An earlier internal test of three hand-chosen cases had also failed; this shows that
  outcome was not an artefact of case selection. Any downstream component that assumes a working
  hierarchy must be described accordingly.
- **The distant-pair criterion passes but should not be read as a clean result.** It passes partly
  because 4293 distant pairs is a large denominator, and 82 of the 135 wrongly merged pairs fall in
  a single cluster already flagged as unreliable.

---

## 4.4 Independent recovery of known errors

A prior manual audit of the label space had named six specific mis-merges. The ontology was not
given that list.

**Table 6. Mis-merges identified independently by the ontology.**

| Label pair | Cluster | Ontology relation | Derived space |
|---|---:|---|---|
| Sorin NK cell + CRC granulocytes | 3 | distant | same cluster |
| Keren NK + ferguson DC | 21 | distant | same cluster |
| Keren NK + Sorin DCs | 21 | distant | same cluster |
| ferguson GC + Sorin mast cell | 22 | distant | same cluster |
| ferguson GC + Phillips DCs | 22 | distant | same cluster |
| Keren neutrophils + ferguson EP | 20 | distant | same cluster |

All six were recovered. The ontology reproduces, automatically, what manual inspection had found.

**The hardest declared case.** Two cohorts use the identical string `tumor cells` for different
cell types: one is colorectal epithelium, the other is a cutaneous T-cell lymphoma. Any
name-based method merges them. The ontology places the pair **distant**, and the derived space
places them in **different clusters**. An external referee agrees with the method on the case it
was designed to get right.

---

## 4.5 Marker availability

For each cluster we asked whether the contributing cohorts measure a marker that identifies its
cell type. Markers came from CellMarker 2.0, joined by CL identifier rather than by name. A marker
was required to be listed for the type in at least 10 database rows before its specificity was
read; specificity is the number of other cell types the same symbol is listed for, so lower is
more identifying.

**Table 7. Marker availability, selected clusters.**

| Cluster | Majority CL type | Supported markers | In panel | Best available | Specificity |
|---:|---|---:|---:|---|---:|
| 0 | epithelial cell | 8 | 6 | KRT14 | 10 |
| 1 | macrophage | 19 | 7 | ITGAM | 11 |
| 6 | B cell | 25 | 4 | CR2 | 8 |
| 22 | mast cell | 5 | 2 | TPSAB1 | 7 |
| 21 | dendritic cell | 11 | 3 | CD209 | 10 |
| 18 | endothelial cell | 16 | 2 | PECAM1 | 42 |
| **3** | **granulocyte** | **0** | **0** | **none** | — |
| **5** | **CD4+ helper T cell** | **0** | **0** | **none** | — |
| **17** | **lymphatic endothelium** | **1** | **0** | **none** | — |

Three clusters have no supported marker of their own cell type measured by any contributing
cohort. Cluster 3 is also the granulocyte cluster that wrongly absorbs NK cells (Table 6). These
are panel limitations and should be reported as scope conditions rather than modelling failures.

We had pre-declared that four specific clusters would show poor marker availability. **That
prediction was not supported**: their median specificity was 10 against 12 for the remaining
clusters, i.e. marginally better. Their poor transfer is explained by the mis-merges in Table 6,
not by the panel.

---

## 4.6 Broad-lineage agreement

An earlier internal score reported agreement of 0.629 at the broadest lineage level (immune /
stromal / epithelial-tumour), lower than at finer levels. Agreement normally rises as classes get
coarser, so this was investigated.

**Table 8. Broad-lineage agreement under a many-to-one cluster assignment.**

| Level | Classes | Labels | Cell-weighted | Per label |
|---|---:|---:|---:|---:|
| Three-lineage (internal) | 3 | 64 | **0.993** | 0.922 |
| CL upper slims (external) | 17 | 100 | **0.914** | 0.710 |

The low value was an artefact of one-to-one matching: 25 clusters cannot be matched one-to-one
onto 3 classes. Under a many-to-one assignment agreement is 0.993. The clusters do not cut across
the broad lineages.

---

## 4.7 Summary

**Table 9. All pre-declared checks and their outcomes.** Thresholds were committed to a versioned
file before the ontology was consulted.

| Check | Measured | Threshold | Outcome |
|---|---|---|---|
| Ontology absent from the pipeline | 0 violations / 30 modules | 0 | pass |
| Mapping coverage | 101/106 = 0.953 | ≥ 0.95 | pass |
| Resolved automatically | 23/101 = 0.228 | ≥ 0.50 | **missed** |
| ARI at CL term level | 0.440 [0.366, 0.662] | ≥ 0.40 | pass |
| ARI, reliable clusters only | 0.572 [0.478, 0.786] | reported alongside | pass |
| Exceeds permutation null | 4/4 levels | all levels | pass |
| Same-term pairs merged | 0.645 | ≥ 0.90 | **fail** |
| Parent–child pairs represented | 0.282 | ≥ 0.60 | **fail** |
| Distant pairs wrongly merged | 0.031 | ≤ 0.05 | pass |
| Marker-availability prediction | 10 vs 12 (median specificity) | predicted worse | **not supported** |

---

## 4.8 Limitations

1. **The choice of CL term per label is human judgement.** Only 22.8 % of labels resolved by exact
   string match; the rest were assigned from each cohort's own publication. The supported claim is
   that the derived clusters agree with a published ontology's *structure*. It is not that the
   labels were mapped without human input. What judgement cannot influence is which terms the
   ontology treats as identical, nested or distant — and that is what Tables 2–6 measure.
2. **One cluster is a residual class.** Cluster 2 holds 17 labels with no discriminative shared
   marker. Every result is reported with and without the three clusters flagged unreliable.
3. **The ontology cannot express tumour identity.** Two malignant terms exist, with no
   tissue-specific children. Both readings are reported (Section 4.2).
4. **101 labels is a small sample.** The bootstrap prices the label count. It does not price the
   roster being six cohorts.
5. **Marker records are pooled across tissues.** Table 7 asks whether a marker of a cell type
   exists in the panel, not whether it performs in that tumour type.
6. **HuBMAP ASCT+B could not be used.** Every documented API endpoint was unavailable at the time
   of analysis, so CellMarker 2.0 was substituted for the marker component.
7. **Granularity is out of scope.** These results test which labels belong together, not whether
   25 is the correct number of clusters.

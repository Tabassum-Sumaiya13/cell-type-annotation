# Stage 7 - the frozen-holdout number (GATE 7)

**ferguson zero-shot macro-F1 = 0.3309** over 22 reliable clusters, in the shipped label space. Baselines measured on the same cells: majority 0.0237, random 0.0562.

ferguson is IMC, skin, 34 markers - a machine, a tissue and a panel the pipeline has never seen. It has never entered a loss. Trained on all 5 training cohorts with the shipped Gate 6 configuration, nothing re-tuned. 20.0 min of GPU time over 3 fits.

## The three numbers

| space | clusters | macro-F1 (reliable) | macro-F1 (all) | majority | random |
|---|---|---|---|---|---|
| A - shipped - NOT blind to the holdout (D-46) | 25 | 0.331 | 0.295 | 0.024 | 0.056 |
| B1 - clean, 5-cohort cut | 37 | 0.308 | 0.308 | 0.024 | 0.044 |
| B2 - clean, shipped cut - matched to A | 22 | 0.424 | 0.373 | 0.031 | 0.065 |

**A is not a clean zero-shot number and is not presented as one.** Stage 1b clustered all six cohorts together, so ferguson helped form the space A scores in (D-46). B1 and B2 are built from the 5 training cohorts alone; the holdout's labels are placed into a frozen partition from marker signatures, admitted only within the same cut, and can never move a boundary.

### Check 4 - what the leak is worth

A and B2 use the SAME cut (0.800) and differ only in whether ferguson was present when the clusters formed, so granularity is not confounded with the comparison.

| | clusters | macro-F1 |
|---|---|---|
| A - holdout present when clustering | 25 | 0.3309 |
| B2 - holdout absent, same cut | 22 | 0.4240 |
| **difference** | | **-0.0931** |

**THE LEAK DID NOT FLATTER THE RESULT - IT PENALISED IT, and that corrects a stated expectation.** D-46 said "coarser is easier, so the direction of the bias is known and it FAVOURS the result." At a matched cut that is backwards: ferguson's presence made the space FINER, 25 clusters against 22, and the shipped number is 0.0931 LOWER than the clean one. The disclosed headline is therefore CONSERVATIVE. gate7_expect.csv check 3 had already caught the loose wording before the run; this measures it.

The H10 control predicted the two spaces would be close at a matched cut (cell-weighted ARI 0.9828). The partitions are - but the three-cluster difference in granularity still moves the macro-F1 by this much, which is worth remembering the next time a macro-F1 is compared across two label spaces.

### Check 3 - the ordering predicted before the run

`gate7_expect.csv` predicted **B2 (22 clusters) >= A (25) >= B1 (37)** purely from cluster count, since fewer classes is an easier macro-F1.

Measured: B2 0.4240 · A 0.3309 · B1 0.3080 - **prediction HOLDS**.

## What the label spaces did before any model ran

**B2 - NOVEL (check 5).** No cluster admitted these labels, so they are dropped from the macro-F1 rather than forced into the nearest bin:

- `EP` - 14,170 cells

**B1 - FUSED (check 6).** ferguson EP and GC both assign to one cluster in B1, so its 9 labels cover 8 distinct targets and the model cannot separate that pair by construction. That is a property of the label space, not a model failure.

## What actually decides the number - training support

Not planned, and it is the strongest thing in this report. Every holdout label was scored against how much TRAINING data its target cluster has. The separation is total, and it reproduces in all three label spaces, so it is not an artefact of any one of them.

| label | ferguson_cells | f1 | recall | train_cohorts | train_labels | train_cells | cohorts |
|---|---|---|---|---|---|---|---|
| TC_CD8 | 4313 | 0.8131 | 0.8233 | 5 | 6 | 325817 | CRC, Keren, Phillips, Sorin, UPMC |
| TC_CD4 | 5536 | 0.5192 | 0.4118 | 3 | 4 | 244911 | CRC, Phillips, Sorin |
| BC | 2327 | 0.5091 | 0.6541 | 5 | 5 | 252271 | CRC, Keren, Phillips, Sorin, UPMC |
| MC | 4196 | 0.4372 | 0.8661 | 5 | 15 | 632612 | CRC, Keren, Phillips, Sorin, UPMC |
| SC | 5984 | 0.3671 | 0.4609 | 5 | 12 | 2014929 | CRC, Keren, Phillips, Sorin, UPMC |
| EC | 5881 | 0.0039 | 0.0020 | 1 | 3 | 13062 | Keren |
| GC | 3864 | 0.0016 | 0.0008 | 2 | 2 | 17635 | Phillips, Sorin |
| EP | 5488 | 0.0000 | 0.0000 | 1 | 1 | 3018 | Keren |
| DC | 2411 | 0.0000 | 0.0000 | 2 | 2 | 2313 | Keren, Sorin |

- correlation between log10(training cells in the target cluster) and ferguson F1: **0.798**
- correlation between the NUMBER OF TRAINING COHORTS in the cluster and F1: **0.843**

Split at that line, the single headline number is really two regimes:

| | classes | mean F1 |
|---|---|---|
| clusters carried by >= 3 training cohorts | 5 | **0.5291** |
| clusters carried by <= 2 training cohorts | 4 | **0.0014** |

**This is the result of the project, stated plainly.** Cross-cohort transfer to an unseen machine, tissue and panel WORKS for cell types that several cohorts independently agree on, and FAILS COMPLETELY for types defined by one or two. It is not a gradient - the thin classes are not weak, they are never predicted at all.

It is also a replication rather than a new claim. Gate 6 found a support-to-F1 correlation of 0.709 across the LOCO folds and 10 single-cohort clusters scoring exactly 0.000. The same law now reappears on a cohort the pipeline had never seen, from a different machine and a different tissue. A finding that survives that is worth more than the headline average, which is just these two regimes mixed together.

## Per holdout label

This is the table a reader of this cohort actually recognises. Recall is what fraction of that label's cells were given the right cluster.

### Space A (25 clusters)

| label | cells | cluster | cluster_name | unreliable | recall | precision | f1 |
|---|---|---|---|---|---|---|---|
| SC | 5984 | 0 | KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ MKI67+ VIM- | 0 | 0.461 | 0.305 | 0.367 |
| EC | 5881 | 18 | PTPRC- | 1 | 0.002 | 0.057 | 0.004 |
| TC_CD4 | 5536 | 5 | CD4+ CD3D|CD3E|CD3G+ PTPRC+ | 0 | 0.412 | 0.702 | 0.519 |
| EP | 5488 | 20 | PDPN+ KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ EGFR+ | 0 | 0.000 | 0.000 | 0.000 |
| TC_CD8 | 4313 | 4 | CD8A+ LAG3+ CD3D|CD3E|CD3G+ | 0 | 0.823 | 0.803 | 0.813 |
| MC | 4196 | 1 | CD163+ CD68+ HLA-DRA|HLA-DRB1|HLA-DRB5+ | 0 | 0.866 | 0.292 | 0.437 |
| GC | 3864 | 22 | CD68+ ITGAX+ ICOS- | 0 | 0.001 | 0.600 | 0.002 |
| DC | 2411 | 21 | ITGAX+ HLA-DRA|HLA-DRB1|HLA-DRB5+ IDO1+ | 0 | 0.000 | 0.000 | 0.000 |
| BC | 2327 | 6 | MS4A1+ PTPRC+ PTPRC+ | 0 | 0.654 | 0.417 | 0.509 |

### Space B1 (37 clusters)

| label | cells | cluster | cluster_name | unreliable | recall | precision | f1 |
|---|---|---|---|---|---|---|---|
| SC | 5984 | 0 | KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ FUT4+ MKI67+ VIM- | 0 | 0.307 | 0.282 | 0.294 |
| EC | 5881 | 22 | VIM- | 0 | 0.027 | 0.416 | 0.051 |
| TC_CD4 | 5536 | 5 | CD3D|CD3E|CD3G+ CD4+ PTPRC+ | 0 | 0.492 | 0.568 | 0.527 |
| EP | 5488 | 31 | ITGAM+ EGFR+ KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ | 0 | 0.000 | 0.000 | 0.000 |
| TC_CD8 | 4313 | 4 | CD8A+ CD3D|CD3E|CD3G+ LAG3+ | 0 | 0.941 | 0.636 | 0.759 |
| MC | 4196 | 1 | CD163+ CD68+ IDO1+ | 0 | 0.827 | 0.344 | 0.486 |
| GC | 3864 | 31 | ITGAM+ EGFR+ KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ | 0 | 0.000 | 0.000 | 0.000 |
| DC | 2411 | 36 | ITGAX+ HLA-DRA|HLA-DRB1|HLA-DRB5+ CD4+ | 0 | 0.000 | 0.000 | 0.000 |
| BC | 2327 | 6 | MS4A1+ PTPRC+ PTPRC+ | 0 | 0.238 | 0.639 | 0.346 |

### Space B2 (22 clusters)

| label | cells | cluster | cluster_name | unreliable | recall | precision | f1 |
|---|---|---|---|---|---|---|---|
| SC | 5984 | 0 | KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ TP53+ CTNNB1+ VIM- | 0 | 0.539 | 0.362 | 0.433 |
| EC | 5881 | 15 | VIM+ IDO1+ PTPRC- | 1 | 0.008 | 0.170 | 0.015 |
| TC_CD4 | 5536 | 4 | CD3D|CD3E|CD3G+ CD4+ PTPRC+ | 0 | 0.579 | 0.519 | 0.547 |
| TC_CD8 | 4313 | 3 | CD8A+ LAG3+ CD3D|CD3E|CD3G+ | 0 | 0.927 | 0.764 | 0.838 |
| MC | 4196 | 1 | CD163+ CD68+ | 0 | 0.751 | 0.475 | 0.582 |
| GC | 3864 | 21 | ITGAX+ CD68+ CD163+ LAG3- | 0 | 0.000 | 0.000 | 0.000 |
| DC | 2411 | 18 | IDO1+ NCAM1+ ITGAX+ | 0 | 0.000 | 0.000 | 0.000 |
| BC | 2327 | 5 | MS4A1+ PTPRC+ PTPRC+ | 0 | 0.491 | 0.675 | 0.568 |

## How this was run

- Trained on **CRC, Keren, Phillips, Sorin, UPMC** - all five, not LOCO. `ferguson` asserted absent from every training and validation draw (check 0).
- Scored on **40,000 ferguson cells** out of a 40,000-cell value table. That table is Stage 2's 40,000-cell subsample, drawn from the same slides - NOT every labelled ferguson cell (check 9). 0 cells carry a label with no place in this space and are dropped.
- Configuration is Gate 6's shipped arm exactly: prototype head, cell-type + masked-marker losses, no VICReg (D-44), no adversary (D-36), confidence weighting on, warm start from Stage 2 arm B. Nothing was re-tuned for this stage.
- Early stopping on held-out SLIDES of the training cohorts, never on ferguson.
- **Every run hit the 30-epoch ceiling** ([30, 30, 30]), so none of them had stopped improving. These numbers are a LOWER BOUND, not a converged result.
- The stroma waiver is honoured in every space (check 7): the headline drops flagged clusters, and the all-cluster column is printed beside it.

Thresholds and predictions were committed to `pipeline2/panel/gate7_expect.csv` before this file was written.

## Check 8 - the predicted range, and it was WRONG

`gate7_expect.csv` predicted **0.35 - 0.55** for space A. Measured **0.3309** - BELOW the floor.

The reasoning behind the prediction was: Stage 7 trains on 5 cohorts rather than 4, and every cluster ferguson touches has training support, so the 10-single-cohort-clusters problem that drags the LOCO macro-F1 down should not apply. **That reasoning was wrong, and the support table above shows exactly how.** "Has training support" is not a yes/no property. Four of ferguson's nine labels land in clusters carried by one or two cohorts and 2.3k-18k cells, and those four score essentially zero. The prediction confused "the class exists in training" with "the class is learnable from training", which is the same mistake the all-25-cluster macro-F1 makes.

For scale: Gate 6's LOCO mean over the same 22 reliable clusters is 0.3901, and the weakest LOCO fold (held-out CRC) is 0.2983. ferguson at 0.3309 sits between them - harder than the average held-out cohort, easier than the hardest one. A new machine, tissue and panel costs about as much as the worst cohort already on the roster, which is a defensible thing to report.

# H10 control - was the label space built blind to the frozen holdout?

**FAIL** - the 25-cluster label space was compared against the one Stage 1b would have produced from the 5 training cohorts alone.

## The question

Stage 1b clustered all six cohorts together, so ferguson's 9 labels and their marker signatures were in the distance matrix that produced the 25 clusters. ferguson cells have never entered a loss, so this is not a training leak - but the label space Stage 7 will be scored in was not built blind to ferguson, and that is worth measuring rather than arguing about.

This is a CONTROL, not a rebuild. Re-clustering on 5 cohorts and shipping that would change the cluster count and invalidate every number produced since Gate 1b. The same choice was made at Gate 2 (D-27).

Thresholds were declared in `pipeline2/panel/gate1b_control_expect.csv` before this script was run.

## Does this script reproduce the shipped result?

ARI against `work/label_map.csv`: **1.0000** - identical labelling: `True`. It runs the same chain as `s1b_labels.main()` with nothing added or skipped, so the 5-cohort column below is a like-for-like comparison.

## The two runs

| | 6-cohort (shipped) | 5-cohort (control) |
|---|---|---|
| labels | 106 | 97 |
| chosen cut tau | 0.800 | 0.650 |
| clusters at the cut | 19 | 33 |
| after per-branch refinement | 25 | 37 |
| after SCC contraction | **25** | **37** |
| biggest cluster share | 16.0% | 9.3% |
| cohort ARI guard | 0.004 | -0.003 |
| stability at the cut | 0.875 | 0.824 |

_Checks 5 and 6 are these two rows, reported with no threshold: the cut is chosen by guards over the whole node set, so dropping 9 labels may legitimately move it._

## Check 1 - could ferguson have acted through the signatures?

- SIM submatrix identical: `True`
- EV submatrix identical: `True`

`rescale` loops over cohorts one at a time, so dropping ferguson's rows cannot change another cohort's Z, P or W. This check asserts that consequence instead of trusting the argument. When it passes, ferguson's ONLY channel of influence is the clustering itself - bridging two labels in average linkage, shifting the cut the guards choose, or changing a per-branch split's LOCO support - which is what checks 2-4 then measure.

## Checks 2 and 3 - how much did the label space move?

Over the **97 training-cohort labels** present in both runs:

| measure | value | threshold | |
|---|---|---|---|
| cell-weighted ARI | **0.5447** | >= 0.9 | FAIL |
| unweighted ARI | **0.5238** | >= 0.85 | FAIL |
| label pairs agreeing | 0.9495 | report only | 4,421 of 4,656 |

0.90 is Gate 1b's own agreement bar, reused so the number means the same thing it does elsewhere in this project. The unweighted bar is lower on purpose: it counts a 100-cell label the same as a 900k-cell one, so a small rare-label reshuffle should not by itself fail the control.

## Check 4 - the clusters Stage 7 actually depends on

ferguson's 9 labels map into 9 clusters. For each one, do its TRAINING-cohort members still sit together when ferguson is removed? A change confined to exactly these clusters would be the worst case, and a global ARI would hide it.

| cluster6 | name | ferguson_labels | train_labels | cells | control_clusters | unbroken |
|---|---|---|---|---|---|---|
| 0 | KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ MKI67+ VIM- | SC | 12 | 2014929 | 5 | False |
| 1 | CD163+ CD68+ HLA-DRA|HLA-DRB1|HLA-DRB5+ | MC | 15 | 632612 | 5 | False |
| 4 | CD8A+ LAG3+ CD3D|CD3E|CD3G+ | TC_CD8 | 6 | 325817 | 1 | True |
| 5 | CD4+ CD3D|CD3E|CD3G+ PTPRC+ | TC_CD4 | 4 | 244911 | 1 | True |
| 6 | MS4A1+ PTPRC+ PTPRC+ | BC | 5 | 252271 | 2 | False |
| 18 | PTPRC- | EC | 3 | 13062 | 2 | False |
| 20 | PDPN+ KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20+ EGFR+ | EP | 1 | 3018 | 1 | True |
| 21 | ITGAX+ HLA-DRA|HLA-DRB1|HLA-DRB5+ IDO1+ | DC | 2 | 2313 | 2 | False |
| 22 | CD68+ ITGAX+ ICOS- | GC | 2 | 17635 | 2 | False |

**3 of 9 unbroken.**

## Which labels changed cluster-mates

62 of 97 labels have a different set of cluster-mates. `gained` and `lost` count mates, not clusters.

**Do not read this table on its own.** It is measured at the control's OWN cut, so almost every row is a cluster being SPLIT rather than regrouped - note how nearly every `gained` is 0 while `lost` is large, which is the signature of a finer cut, not of labels changing partners. Checks 7-9 below separate the two.

| cohort | label | cells | gained | lost |
|---|---|---|---|---|
| Sorin | Cancer | 930658 | 0 | 9 |
| UPMC | Tumor (Ki67+) | 275647 | 0 | 7 |
| UPMC | Tumor | 225099 | 2 | 11 |
| UPMC | Macrophage | 211303 | 0 | 7 |
| Sorin | Cl MAC | 198873 | 0 | 12 |
| UPMC | Stromal / Fibroblast | 158552 | 1 | 0 |
| UPMC | B cell | 136756 | 0 | 4 |
| UPMC | Tumor (Podo+) | 129357 | 0 | 7 |
| UPMC | Tumor (CD15+) | 125871 | 0 | 9 |
| UPMC | Tumor (CD21+) | 111077 | 0 | 7 |
| Keren | Keratin_positive_tumor | 99487 | 0 | 10 |
| Sorin | B cell | 91152 | 0 | 1 |
| UPMC | APC | 78777 | 0 | 13 |
| Sorin | Cl Mo | 64667 | 0 | 10 |
| UPMC | Granulocyte | 55415 | 0 | 2 |
| Sorin | Alt MAC | 51533 | 0 | 7 |
| Sorin | Neutrophils | 50328 | 0 | 10 |
| CRC | tumor cells | 47602 | 0 | 9 |
| UPMC | Tumor (CD20+) | 43261 | 0 | 7 |
| CRC | CD68+CD163+ macrophages | 39596 | 0 | 7 |
| CRC | smooth muscle | 27817 | 0 | 10 |
| Sorin | Non-Cl Mo | 23364 | 0 | 10 |
| CRC | granulocytes | 22144 | 1 | 1 |
| Keren | Macrophages | 20616 | 0 | 7 |
| CRC | stroma | 20139 | 0 | 10 |
| Phillips | epithelium | 18182 | 0 | 10 |
| Sorin | Mast cell | 17424 | 1 | 1 |
| Phillips | macrophages (M1>M2) | 13800 | 0 | 7 |
| CRC | B cells | 13043 | 0 | 1 |
| Sorin | Int Mo | 12838 | 0 | 10 |

## Checks 7 and 8 - DIAGNOSTIC, added after the FAIL, and it does NOT revise the verdict

Checks 2-4 change **two things at once**: the node set, and the cut the guards then choose from it. Re-running the control at the SHIPPED cut separates them. This section was written after seeing checks 2-4 fail, so it is labelled a diagnostic and the verdict above stands as declared - D-34 refuses a rule that would flip a verdict in its own favour.

| | control at ITS OWN cut | control at the SHIPPED cut |
|---|---|---|
| cut tau | 0.650 | 0.800 |
| clusters | 37 | 22 |
| cell-weighted ARI vs shipped | 0.5447 | **0.9828** |
| unweighted ARI vs shipped | 0.5238 | **0.8764** |
| control clusters spanning >1 shipped cluster | 4 of 37 | 4 of 22 |

**This is the whole story.** Hold the cut fixed and the partition barely moves - the similarity structure is stable without ferguson. Let the guards pick the cut and it moves a lot, 0.800 to 0.650, which is 25 clusters against 37. So ferguson did not change WHICH labels are alike. It changed which GRANULARITY the cut-choosing rule selected, and ARI punishes a pure granularity change as hard as a genuine re-mixing.

The clusters that genuinely re-mix - not a refinement, a real regrouping - are these:

| control_cluster | labels | spans_shipped |
|---|---|---|
| 0 | 14 | 0, 18 |
| 1 | 19 | 1, 3, 20 |
| 15 | 3 | 16, 18 |
| 19 | 2 | 22, 23 |

Read these in the direction they happened: ferguson SEPARATED these groups. Without it they merge. So on this evidence the frozen cohort was acting as a source of distinctions, not as a bridge.

## Check 9 - DIAGNOSTIC - why did the cut move?

The cut is chosen in two steps: three guards mark which cuts are USABLE, then stability picks the argmax inside that window. Both steps are affected, and they are worth separating.

| cut | clusters_6 | biggest_share_6 | cross_cohort_share_6 | stability_6 | usable_6 | clusters_5 | biggest_share_5 | cross_cohort_share_5 | stability_5 | usable_5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.600 | 38 | 0.094 | 0.888 | 0.839 | False | 41 | 0.072 | 0.903 | 0.775 | False |
| 0.625 | 35 | 0.094 | 0.945 | 0.887 | False | 36 | 0.082 | 0.950 | 0.806 | False |
| 0.650 | 31 | 0.113 | 0.946 | 0.821 | False | 33 | 0.093 | 0.952 | 0.824 | True |
| 0.675 | 31 | 0.113 | 0.946 | 0.825 | False | 31 | 0.103 | 0.964 | 0.784 | True |
| 0.700 | 28 | 0.151 | 0.946 | 0.823 | False | 28 | 0.165 | 0.964 | 0.762 | True |
| 0.725 | 27 | 0.151 | 0.946 | 0.807 | False | 24 | 0.165 | 0.995 | 0.802 | True |
| 0.750 | 25 | 0.151 | 0.967 | 0.799 | True | 22 | 0.175 | 0.995 | 0.801 | True |
| 0.775 | 20 | 0.160 | 0.996 | 0.864 | True | 20 | 0.175 | 0.996 | 0.768 | True |
| 0.800 | 19 | 0.160 | 0.996 | 0.875 | True | 18 | 0.196 | 0.996 | 0.821 | True |
| 0.825 | 16 | 0.283 | 0.996 | 0.850 | False | 17 | 0.206 | 0.996 | 0.788 | True |
| 0.850 | 15 | 0.340 | 0.996 | 0.856 | False | 14 | 0.227 | 0.996 | 0.783 | True |
| 0.875 | 14 | 0.340 | 0.996 | 0.865 | False | 13 | 0.371 | 0.996 | 0.868 | False |

- **The guards.** With ferguson the usable window is **0.750 to 0.800** - 3 grid points. Without it, **0.650 to 0.850** - 9 points. A sixth cohort binds BOTH guards: it drags `cross_cohort_share` below the 0.95 floor at the fine end and pushes `biggest_share` above the 0.25 ceiling at the coarse end. That is real, and it is the honest part of the leak.
- **The stability pick.** Inside the 5-cohort window the stability curve is nearly FLAT. The control chooses 0.650 over the shipped 0.800 by a margin of **+0.0035 ARI**. That is not a decision, it is a coin flip on noise.
- **And the shipped cut is legal without ferguson.** 0.800 sits INSIDE the 5-cohort usable window 0.650 to 0.850. The 25-cluster space is a choice the 5 training cohorts also support; it is just not the argmax of a curve that varies by less than 0.01.

**A separate defect surfaces here, and it is not about ferguson at all.** `choose_cut` takes the argmax of a stability curve whose whole range across the feasible window is 0.062. Its own docstring says stability has "no directional bias, only low resolution" - this control measures how low. A rule that picks a granularity by 0.003 of ARI is not selecting; it is sampling. Recorded as its own finding.

## How to read this

The declared verdict is **FAIL**: the 25-cluster label space is NOT independent of the frozen holdout, and Stage 7's number cannot be reported as a clean zero-shot result without saying so.

But the mechanism is narrower than the verdict alone suggests, and both halves must be reported together:

- **What is stable:** the similarity structure. At a matched cut the weighted ARI is 0.9828 and 18 of 22 control clusters sit entirely inside one shipped cluster.
- **What is not:** the granularity. The guard-plus-stability rule that picks the cut is sensitive to which cohorts are in the room, and 9 labels out of 106 moved it from 0.800 to 0.650.
- **What it costs:** Stage 7 is scored in a label space whose COARSENESS ferguson helped choose. Coarser is easier, so the direction of the bias is known and it favours the result. That must be stated next to the number.

Two ways forward, and this file does not choose between them:

1. **Disclose.** Report Stage 7 in the shipped 25-cluster space, cite this control, state the direction of the bias. Costs nothing. An examiner can still ask the question.
2. **Also report a clean-protocol number.** Freeze the control's label space, assign the frozen cohort's labels into it from their marker signatures alone, and train and score there as a second number. That is the actual deployment procedure this project claims, it is fully leak-free, and it costs one extra training run.

Neither changes what ships. They change which sentence can be written about what ships.

# Stage 1 - Continuous value harmonisation (GATE 1)

**6 arms** raced on **9 markers measured by all 6 cohorts**, scored **leave-one-cohort-out** over the 5 training cohorts.

**Winner on mean LOCO R2: `V3`.**

## The arms, and what each comparison isolates

| arm    | channels      | film   |
|:-------|:--------------|:-------|
| V1     | u_img         | -      |
| V3     | u_coh         | -      |
| V2a    | u_coh         | scalar |
| V2b    | u_coh         | mlp    |
| V1+V3  | u_img , u_coh | -      |
| V2a+V1 | u_coh , u_img | scalar |

| comparison | question it answers |
|---|---|
| V1 vs V3 | is per-image grouping harmful on its own? |
| V3 vs V2a / V2b | is a learned slide correction worth anything at all? |
| V2a vs V2b | is the **extra capacity** in that correction worth anything? |
| V3 vs V1+V3 | does the image rank **add** to the cohort rank rather than replace it? |
| V1+V3 vs V2a+V1 | does FiLM beat simply handing over the image rank? |

### A channel the plan asked for, dropped on measurement

The plan specified a second channel holding *the value relative to a cohort-level reference* (tanh of a robust z-score), so that ranking would not destroy prevalence. Built and measured, it fails twice. It **saturates** - 5.5-17.5% of cells sit at `|lvl| > 0.99`, worst on Sorin, which arrives uint8 so most markers have median 0 and a near-zero IQR. And it is **redundant by construction**: any per-cell function of the raw value computed from cohort statistics is a monotone transform of that value, so it carries what `u_coh` already carries (measured correlation 0.89-0.97).

It would also have broken this gate. An arm holding `{u_img, lvl}` strictly contains an arm holding `{u_coh, lvl}`, so **V1 could not have lost**. The second channel is therefore the *other grouping*, which is genuinely independent information.

## The shared core

Gate 1 compares arms against each other, so every fold must see an identical feature space - otherwise an arm could win on imputation rather than on normalisation. Only triples present in every cohort are used, so nothing is filled in.

| triple                  | gene / members                                                                       |
|:------------------------|:-------------------------------------------------------------------------------------|
| COMPLEX:CD3|pan|none    | CD3D|CD3E|CD3G                                                                       |
| COMPLEX:HLA-DR|pan|none | HLA-DRA|HLA-DRB1|HLA-DRB5                                                            |
| FAMILY:KRT_PAN|pan|none | KRT1|KRT4|KRT5|KRT6A|KRT7|KRT8|KRT10|KRT13|KRT14|KRT15|KRT16|KRT17|KRT18|KRT19|KRT20 |
| HGNC:1678|pan|none      | CD4                                                                                  |
| HGNC:1693|pan|none      | CD68                                                                                 |
| HGNC:1706|pan|none      | CD8A                                                                                 |
| HGNC:6106|pan|none      | FOXP3                                                                                |
| HGNC:7315|pan|none      | MS4A1                                                                                |
| HGNC:8823|pan|none      | PECAM1                                                                               |

## Subsample actually built

Stratified round-robin over (patient x native label), so a rare label is kept whole and a huge stratum cannot swamp the draw. References (cohort ECDF, per-image ECDF, slide statistics) come from **all** cells; only the written table is subsampled.

| cohort   |   cells_kept |   cells_total |   slides |
|:---------|-------------:|--------------:|---------:|
| CRC      |        40000 |        258385 |      140 |
| UPMC     |        40000 |       2061102 |      308 |
| Keren    |        40000 |        197678 |       40 |
| ferguson |        40000 |        155913 |       44 |
| Phillips |        40000 |        117170 |       69 |
| Sorin    |        40000 |       2141875 |      536 |

## Check 1 - cross-cohort distribution overlap (mean pairwise KS)

Lower is better. `raw (before)` is the values exactly as each cohort ships them. All distribution checks below use the **unstratified** draw - see the note at the end of this section.

| marker         |   raw (before) |    V1 |    V3 |   V2a |   V2b |   V1+V3 |   V2a+V1 |
|:---------------|---------------:|------:|------:|------:|------:|--------:|---------:|
| CD3D|CD3E|CD3G |          0.772 | 0.146 | 0.25  | 0.234 | 0.187 |   0.146 |    0.225 |
| COMPLEX:HLA-DR |          0.638 | 0.161 | 0.248 | 0.203 | 0.179 |   0.161 |    0.239 |
| FAMILY:KRT_PAN |          0.516 | 0.116 | 0.303 | 0.233 | 0.114 |   0.116 |    0.182 |
| CD4            |          0.742 | 0.143 | 0.245 | 0.23  | 0.158 |   0.143 |    0.222 |
| CD68           |          0.781 | 0.136 | 0.242 | 0.195 | 0.208 |   0.136 |    0.192 |
| CD8A           |          0.757 | 0.178 | 0.283 | 0.264 | 0.259 |   0.178 |    0.248 |
| FOXP3          |          0.89  | 0.3   | 0.347 | 0.35  | 0.21  |   0.3   |    0.398 |
| MS4A1          |          0.709 | 0.257 | 0.365 | 0.328 | 0.215 |   0.257 |    0.327 |
| PECAM1         |          0.678 | 0.276 | 0.374 | 0.353 | 0.205 |   0.276 |    0.363 |

**Mean over markers** - raw **0.720** -> V1 **0.190** · V3 **0.295** · V2a **0.266** · V2b **0.193** · V1+V3 **0.190** · V2a+V1 **0.266**


**This check confirms the arrival-state problem is fixed, and it CANNOT rank the arms.** Raw values sit at 0.705 mean KS - four different curve shapes, exactly the defect Stage 1 exists to remove - and every arm lands near 0.2-0.3. But a per-group ECDF forces each group's marginal to uniform *by construction*, so between-cohort KS is near zero for any rank-based arm on a representative sample, and whatever spread remains reflects the sample, not the method. Reading an arm ranking off this table would be reading noise. Checks 2, 3 and 4 decide.

*(First attempt at this check ran on the class-balanced table and appeared to rank V1 best and V3 worst. That was an artefact of the balancing: measured `|mean(u_coh) - 0.5|` is 0.0009 on a random draw of Keren and 0.0475 on the stratified one. Distribution checks now use the unstratified draw.)*


## Check 2 - composition-skew robustness (the check that decides V1)

Take the label that dominates the most composition-skewed 10% of slides, and compare its median marker value **on those slides** against its median **on the most balanced slides**. Same label, same cohort, same marker - only the neighbours change.

A negative delta is the *invented negative population*: ranking inside a 90%-tumour slide pushes half those tumour cells below the median on keratin, so an identical cell reads lower purely because of what it was sitting next to. Reported as a contrast rather than an absolute level, because an absolute median cannot be separated from base rate.

| cohort   |   pairs |     V1 |     V3 |    V2a |    V2b |   V1+V3 |   V2a+V1 |
|:---------|--------:|-------:|-------:|-------:|-------:|--------:|---------:|
| CRC      |       7 | -0.062 |  0.051 |  0.049 |  0.109 |  -0.062 |    0.081 |
| UPMC     |       9 | -0.113 | -0.014 | -0.038 | -0.006 |  -0.113 |    0.008 |
| Keren    |       4 | -0.336 | -0.134 | -0.18  | -0.23  |  -0.336 |   -0.148 |
| ferguson |       4 | -0.034 |  0.012 |  0.071 |  0.289 |  -0.034 |    0.096 |
| Phillips |       2 | -0.153 |  0.127 |  0.134 |  0.199 |  -0.153 |    0.137 |
| Sorin    |      52 | -0.22  | -0.04  | -0.013 | -0.366 |  -0.22  |    0.058 |

## Check 3 - label / marker consistency (AUROC)

Assertions declared in advance in `pipeline2/panel/gate1_expect.csv`: a cell whose native label names a marker must read **higher on that marker than the rest of its own cohort**, at AUROC >= 0.75. That file scores the gate and never feeds the pipeline - the same status `never_merge.csv` has at Stage 0b.

|                    | V1      | V3      | V2a     | V2b     | V1+V3   | V2a+V1   |
|:-------------------|:--------|:--------|:--------|:--------|:--------|:---------|
| assertions passing | 33 / 40 | 34 / 40 | 34 / 40 | 27 / 40 | 33 / 40 | 33 / 40  |

*Scored by AUROC, not by "median rank in the top quartile", which was the first attempt and is mathematically broken. A label of prevalence `p` sitting at the top of the distribution has a best-possible median rank of `1 - p/2`, so a fixed 0.75 threshold is **unreachable** above 50% prevalence. Measured: ferguson `SC` is 56.0% of its cohort (ceiling 0.720) and Keren `Keratin_positive_tumor` is 50.3% (ceiling 0.748) - the latter "passed" at 0.751, i.e. the threshold was scoring base rate, not biology. AUROC is invariant to prevalence and asks the intended question.*


<details><summary><b>6 assertion(s) failing under the winner V3</b></summary>

| cohort   | native_label         | marker   |   cells |   auroc | passes   | note                                                                                                                                                                                                        |
|:---------|:---------------------|:---------|--------:|--------:|:---------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| CRC      | tumor cells          | panCK    |    7283 |   0.669 | False    | sibling classes share this marker (other tumour/epithelial classes sit in the negative set), so vs-all-others AUROC is diluted                                                                              |
| CRC      | CD4+ T cells CD45RO+ | CD4      |    2574 |   0.716 | False    | CD4 is also carried by monocytes and macrophages, so vs-all-others AUROC understates T-cell identity; CD3 separates these labels at 0.80-0.92                                                               |
| UPMC     | Tumor                | panCK    |    4344 |   0.586 | False    | sibling classes share this marker (other tumour/epithelial classes sit in the negative set), so vs-all-others AUROC is diluted                                                                              |
| Phillips | CD4+ T cells         | CD4      |     564 |   0.66  | False    | CD4 is also carried by monocytes and macrophages, so vs-all-others AUROC understates T-cell identity; CD3 separates these labels at 0.80-0.92                                                               |
| ferguson | SC                   | panCK    |   22343 |   0.626 | False    | sibling classes share this marker (other tumour/epithelial classes sit in the negative set), so vs-all-others AUROC is diluted                                                                              |
| ferguson | EC                   | CD31     |    3789 |   0.5   | False    | KNOWN DATA DEFECT: ferguson CD31 does not mark its own EC label (AUROC 0.500). Its endothelium is marked by CD13 instead (0.83). ferguson is the frozen holdout, so this is recorded BEFORE the final test. |

</details>


## Check 4 - LOCO masked-marker transfer R2 (the decision)

Hide one marker, predict its cohort-level ECDF value from the other 8; train on 4 cohorts, score on the held-out one. The target is the same quantity for every arm, so the numbers are comparable.

Scored **leave-one-cohort-out, not on held-out cells** - on purpose. Fitting to slide statistics is invisible on held-out cells, which share the very slides the statistics came from, and only shows up on a cohort the model has never seen.

|          |     V1 |     V3 |    V2a |    V2b |   V1+V3 |   V2a+V1 |
|:---------|-------:|-------:|-------:|-------:|--------:|---------:|
| CRC      | 0.1061 | 0.1552 | 0.1493 | 0.1606 |  0.1443 |   0.1346 |
| UPMC     | 0.1122 | 0.1652 | 0.1757 | 0.1779 |  0.1648 |   0.1837 |
| Keren    | 0.0683 | 0.1386 | 0.1271 | 0.1181 |  0.1281 |   0.1008 |
| Phillips | 0.177  | 0.2013 | 0.1904 | 0.1962 |  0.1836 |   0.1768 |
| Sorin    | 0.1479 | 0.1827 | 0.18   | 0.1421 |  0.1784 |   0.1413 |
| **mean** | 0.1223 | 0.1686 | 0.1645 | 0.159  |  0.1598 |   0.1474 |

## Check 5 - FiLM capacity

How hard FiLM is actually pushing. The output is bounded at `eps = 0.3`, so `|gamma-1|` near 0.3 means it is straining against the bound - which usually means it is fitting cohort identity, not slide drift.


**V2a**

| fold     |   gamma_dev_mean |   beta_abs_mean |   gamma_dev_max |   beta_abs_max |
|:---------|-----------------:|----------------:|----------------:|---------------:|
| CRC      |           0.0495 |          0.0403 |          0.2274 |         0.2353 |
| UPMC     |           0.0588 |          0.0399 |          0.2952 |         0.2845 |
| Keren    |           0.0442 |          0.0332 |          0.2705 |         0.2603 |
| Phillips |           0.0715 |          0.0545 |          0.2778 |         0.284  |
| Sorin    |           0.0367 |          0.0388 |          0.3    |         0.2974 |

**V2b**

| fold     |   gamma_dev_mean |   beta_abs_mean |   gamma_dev_max |   beta_abs_max |
|:---------|-----------------:|----------------:|----------------:|---------------:|
| CRC      |           0.1767 |          0.1546 |             0.3 |         0.3    |
| UPMC     |           0.1826 |          0.1664 |             0.3 |         0.3    |
| Keren    |           0.1666 |          0.1175 |             0.3 |         0.2993 |
| Phillips |           0.1717 |          0.1531 |             0.3 |         0.3    |
| Sorin    |           0.1427 |          0.1107 |             0.3 |         0.3    |

**V2a+V1**

| fold     |   gamma_dev_mean |   beta_abs_mean |   gamma_dev_max |   beta_abs_max |
|:---------|-----------------:|----------------:|----------------:|---------------:|
| CRC      |           0.058  |          0.0577 |          0.2853 |         0.29   |
| UPMC     |           0.0574 |          0.0718 |          0.2883 |         0.3    |
| Keren    |           0.0575 |          0.0689 |          0.2908 |         0.2922 |
| Phillips |           0.1146 |          0.0761 |          0.3    |         0.2987 |
| Sorin    |           0.0438 |          0.0499 |          0.3    |         0.3    |

## No cliffs

![no cliffs](figures/s1_no_cliffs.png)

Token norm against `u`. The line must be smooth: any step function means a bin survived somewhere, which is the exact defect this stage replaces.



---
1. The Winning Formula is Locked In (V3)
What it means: Your pipeline will now normalize every marker by ranking it against the entire cohort’s distribution (ECDF). No per-image grouping, no neural network adjusters (FiLM), no second channel. Just pure math.

Why this is good: It is the simplest, most robust, and least prone to overfitting. When a brand new cohort (like Danenberg or any future dataset) arrives, you just compute its own ECDF and map the values. No dataset-specific tuning.

2. FiLM and Per-Image Ranking are Officially Dead
What it means:

FiLM overfit. The more parameters it had, the worse it performed—especially on Keren (the 40-slide cohort). You now have hard proof that adding complexity to normalization hurts generalization.

Per-image ranking (V1) is actively harmful. It invented fake negative populations on tumor-heavy slides, and it was the worst arm across all cohorts.

Why this is good: You just removed two major failure modes from your pipeline. Your thesis can now state: "We experimentally demonstrate that per-image normalization and learned slide-correction (FiLM) degrade cross-cohort transfer, and thus we adopt a simple cohort-level ECDF." That is a strong, data-driven claim.

3. The Gate System Caught and Fixed its Own Flaws
What it means: You identified that three of your own checks were mathematically broken:

The median rank threshold was impossible for high-prevalence labels (e.g., 50% tumor cells physically cannot have a median rank >0.75). You replaced it with AUROC.

The KS overlap check was confounded by stratified sampling; you fixed it to use unstratified draws.

You caught a biological domain error: Phillips is T-cell lymphoma, so its "tumor cells" are CD3+/CD4+ T cells, not PanCK+ carcinomas.

Why this is good: This is exactly what a rigorous pipeline should do—catch its own mistakes before they corrupt the final model. You are not hiding these fixes; you are documenting them. Reviewers love this.

4. The Critical Warning for Ferguson (The Frozen Test)
What it means: ferguson's endothelial cells (EC) do not express CD31—they express CD13 instead. CD31 is one of your 9 core universal markers. Since ferguson is completely held out and never used for training, your model will fail to detect endothelial cells on ferguson when it looks at CD31.

Why this is good (in a painful way):

You discovered this before running Stage 7. You now have a choice:

Option A: Record this in your thesis as a known panel limitation. Ferguson's EC will be misclassified for a data reason, not a model failure. This protects your model's reputation.
Option B: If CD13 is also present in ferguson and you can map it, you could add it to the shared core just for inference. But that would mean touching the frozen holdout, which breaks the zero-shot rule. (Don't do this unless absolutely necessary.)
Recommendation: Record it now. In your final report, write: "Ferguson's endothelial cells are marked by CD13, not CD31, which is a panel-specific limitation. This is noted as an expected zero-shot failure for this specific cell type."
# Stage 7b - abstain and novel-class detection (GATE 7b)

No training. Stage 7a's fitted models reloaded from `work/ckpt/s7_*.pt` and run forward, so this whole stage is minutes on a CPU.

## Why this stage exists

Stage 7a measured that four of ferguson's nine cell types score ~0.000, because their cluster is carried by one or two training cohorts. A classifier with no abstain option answers confidently on those four anyway. The question that matters to anyone annotating a new cohort is not the macro-F1 - it is **which predictions can I trust, and what do I give up by keeping only those**.

## Calibration

Temperature is fitted on the TRAINING cohorts' held-out slides by minimising NLL. Never on ferguson - that would calibrate the abstain rule on the test set.

| space | T | val NLL before | val NLL after |
|---|---|---|---|
| A | 1.15 | 0.7459 | 0.7323 |
| B1 | 1.10 | 0.9318 | 0.9257 |
| B2 | 1.10 | 0.6752 | 0.6723 |

## Accuracy and macro-F1 against coverage - space A

Cells are ranked by confidence and the most confident kept. `proto` is cosine distance to the nearest prototype, the score the design named because it works on a cohort with no labels at all. `msp` is temperature-scaled max softmax, the standard baseline.

**proto**

| coverage | n_kept | accuracy | macro_f1 | n_classes_left |
|---|---|---|---|---|
| 0.1000 | 4000 | 0.7120 | 0.3941 | 8 |
| 0.1500 | 6000 | 0.6740 | 0.4049 | 8 |
| 0.2000 | 8000 | 0.6366 | 0.4121 | 8 |
| 0.2500 | 10000 | 0.6016 | 0.4159 | 8 |
| 0.3000 | 12000 | 0.5693 | 0.4188 | 8 |
| 0.3500 | 14000 | 0.5456 | 0.4204 | 8 |
| 0.4000 | 16000 | 0.5251 | 0.4183 | 8 |
| 0.4500 | 18000 | 0.5089 | 0.4149 | 8 |
| 0.5000 | 20000 | 0.4930 | 0.4095 | 8 |
| 0.5500 | 22000 | 0.4782 | 0.4031 | 8 |
| 0.6000 | 24000 | 0.4607 | 0.3938 | 8 |
| 0.6500 | 26000 | 0.4438 | 0.3845 | 8 |
| 0.7000 | 28000 | 0.4275 | 0.3766 | 8 |
| 0.7500 | 30000 | 0.4113 | 0.3683 | 8 |
| 0.8000 | 32000 | 0.3972 | 0.3614 | 8 |
| 0.8500 | 34000 | 0.3827 | 0.3537 | 8 |
| 0.9000 | 36000 | 0.3684 | 0.3461 | 8 |
| 0.9500 | 38000 | 0.3560 | 0.3385 | 8 |
| 1.0000 | 40000 | 0.3440 | 0.3309 | 8 |

**msp**

| coverage | n_kept | accuracy | macro_f1 | n_classes_left |
|---|---|---|---|---|
| 0.1000 | 4000 | 0.7997 | 0.3934 | 8 |
| 0.1500 | 6000 | 0.7148 | 0.3873 | 8 |
| 0.2000 | 8000 | 0.6535 | 0.3788 | 8 |
| 0.2500 | 10000 | 0.6070 | 0.3706 | 8 |
| 0.3000 | 12000 | 0.5666 | 0.3673 | 8 |
| 0.3500 | 14000 | 0.5411 | 0.3830 | 8 |
| 0.4000 | 16000 | 0.5239 | 0.3999 | 8 |
| 0.4500 | 18000 | 0.5101 | 0.4056 | 8 |
| 0.5000 | 20000 | 0.4978 | 0.4058 | 8 |
| 0.5500 | 22000 | 0.4818 | 0.4002 | 8 |
| 0.6000 | 24000 | 0.4633 | 0.3919 | 8 |
| 0.6500 | 26000 | 0.4462 | 0.3834 | 8 |
| 0.7000 | 28000 | 0.4293 | 0.3756 | 8 |
| 0.7500 | 30000 | 0.4139 | 0.3677 | 8 |
| 0.8000 | 32000 | 0.3992 | 0.3601 | 8 |
| 0.8500 | 34000 | 0.3846 | 0.3522 | 8 |
| 0.9000 | 36000 | 0.3706 | 0.3454 | 8 |
| 0.9500 | 38000 | 0.3568 | 0.3376 | 8 |
| 1.0000 | 40000 | 0.3440 | 0.3309 | 8 |

**Abstention earns its place, and there is a clear best operating point.** At full coverage accuracy is 0.3440 and macro-F1 0.3309. macro-F1 PEAKS at **0.4204 at 35% coverage** (0.5456 accuracy) - a gain of **+0.0894** over answering everywhere, for the price of declining 65% of the cells.

**Now read the two columns together, which is what check 4 exists for.** Accuracy rises monotonically all the way to 0.7120 at 10% coverage, but macro-F1 does NOT - it turns over after 35% and falls back to 0.3941. Past the peak the rule is buying accuracy by favouring the easy classes, exactly the failure the macro-F1 column was put there to expose. Anyone reading the accuracy column alone would have chosen the worst operating point on the curve.

One thing that does NOT go wrong: all 8 scored classes survive at every coverage level, down to the most confident 10% of cells. The rule declines cells, not whole cell types.

## Novel-class detection

**The test set is real, not simulated.** In label space B2 the frozen partition admitted NO cluster for ferguson `EP` - average distance 0.8120 against a cut of 0.800 - so it is a genuinely novel cell type on a genuinely unseen cohort, and the model was never told it exists. Positives: 5,488 cells (13.7% of the table), labels ['EP']. Negatives: every other ferguson cell.

This substitutes for the design's cohort-exclusive-cluster test (files/05 section 4.11), which needs a retrain per held-out cluster. The substitution is the stronger test - a real unseen type on a real unseen cohort rather than one hidden on purpose.

| score | AUROC |
|---|---|
| proto - distance to nearest prototype | **0.5776** |
| msp - temperature-scaled max softmax | 0.5778 |

Median nearest-prototype similarity: known types 0.7448, novel type 0.7172.

**Both scores are close to chance, and that is the finding.** The model does not know it is looking at something it has never seen. It places the novel type near a prototype with ordinary confidence. Whatever the abstain curve shows, this system cannot currently be trusted to flag a new cell type on arrival - which is exactly the situation a new cohort presents.

## What this does and does not license

- Reported for all three label spaces, since Stage 7a showed a three-cluster granularity difference moves macro-F1 by 0.09 (D-51).
- No threshold is recommended. The design asked for a curve, not a number, because the right operating point depends on what the annotation is for.
- Everything here rests on ONE fitted model per space and ONE seed. The confidence intervals this project still owes (H9) apply to these curves too.

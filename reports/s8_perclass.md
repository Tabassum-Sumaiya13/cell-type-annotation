# Step 4 - per-class reporting and the learnable/unlearnable split

No compute. Existing checkpoints re-reported. No gate verdict changes.

## The headline, three ways

| | macro-F1 |
|---|---|
| Gate 6 LOCO, as reported (all clusters present in the truth) | **0.3901** |
| Gate 6 LOCO, learnable clusters only | **0.4606** |
| Gate 7 ferguson, mean over all 9 holdout LABELS | **0.2946** |
| Gate 7 ferguson, labels whose cluster has 3+ training cohorts | **0.5291** |

_The Gate 7 rows are per-LABEL means over all nine ferguson labels, so they do not equal the 0.3309 headline, which is a per-CLUSTER macro over the eight reliable clusters. Same model, same predictions, different denominator - stated here because two numbers that close together invite exactly that confusion._

**Quote both, always, and say which is which.** The all-cluster number answers "how well does this annotate a new cohort end to end" - in deployment nobody removes the classes you cannot do. The learnable-only number answers "how well does the model do the part of the job it was given data for". Different questions; the thesis needs both.

## Gate 6 per fold

| held | reported | learnable_only | n_all | n_learnable | n_unlearnable | unlearnable_f1 | unlearnable_cells | cells_share |
|---|---|---|---|---|---|---|---|---|
| CRC | 0.2983 | 0.4640 | 14 | 9 | 5 | 0.0000 | 623 | 0.1252 |
| UPMC | 0.3763 | 0.4233 | 9 | 8 | 1 | 0.0000 | 478 | 0.0635 |
| Keren | 0.4058 | 0.4508 | 10 | 9 | 1 | 0.0000 | 524 | 0.0830 |
| Phillips | 0.4270 | 0.5219 | 11 | 9 | 2 | 0.0000 | 153 | 0.0323 |
| Sorin | 0.4432 | 0.4432 | 11 | 11 | 0 |  | 0 | 0.0000 |

Across the five folds, **9 of 55 class-folds are unlearnable by construction** - the cluster's only contributing cohort is the one being held out, so it has zero training examples and scores 0.000 whatever the model does. They are 6.08% of the cells and 16.4% of the macro-average.

Note how unevenly it lands: the gap between the two columns is not a constant offset, so a fold-to-fold comparison made on the reported number is partly a comparison of label-space coverage rather than of transfer.

### This CONFIRMS H7 - it does not discover it

files/07 already recorded this as "LIKELY EXPLAINED, NOT YET CONFIRMED" and named the exact test: *"CONFIRM by re-scoring the saved checkpoints (~2 h, no retraining) before closing."* That is what this file does. The hypothesis was written down first and is confirmed here, which is the order that makes a confirmation worth anything.

H7 asked: **why is CRC the worst fold despite being the largest cohort with the second-richest panel?** Answer: **it is not the worst fold.** It carries the most unlearnable classes - 5 of 14, more than any other fold - and each contributes a forced 0.000 to its macro-average.

| held | reported | learnable_only | n_unlearnable |
|---|---|---|---|
| Phillips | 0.4270 | 0.5219 | 2 |
| CRC | 0.2983 | 0.4640 | 5 |
| Keren | 0.4058 | 0.4508 | 1 |
| Sorin | 0.4432 | 0.4432 | 0 |
| UPMC | 0.3763 | 0.4233 | 1 |

On learnable classes only, CRC ranks **2 of 5** at 0.4640, against a fold mean of 0.4606. The question was built on a measurement artefact. Stage 6's prototype loss and class balancing were aimed at H7 (files/10) and barely moved it, which now makes sense - they were aimed at a problem that was not there.

## The support law, measured on the LOCO folds

Gate 7 found that ferguson labels whose cluster is carried by 3+ training cohorts average F1 0.5291 while those carried by 1-2 average 0.0014. Here is the same cut applied to every class-fold of Gate 6, which is a much larger sample and was collected before ferguson was ever scored.

| band | class_folds | mean_f1 | zero_share | median_support |
|---|---|---|---|---|
| 0 (unlearnable) | 9 | 0.0000 | 1.0000 | 97.0000 |
| 1 cohort | 8 | 0.0921 | 0.5000 | 465.0000 |
| 2 cohorts | 9 | 0.2231 | 0.2222 | 474.0000 |
| 3+ cohorts | 29 | 0.6361 | 0.0000 | 551.0000 |

Correlation between the number of contributing training cohorts and F1, over learnable class-folds only: **0.781**.

**This is the project's most reproducible result.** It holds inside the training roster (here), on a held-out cohort of a familiar kind (Gate 6), and on an unseen machine, tissue and panel (Gate 7). It is not an artefact of one label space - Gate 7 measured it in three.

## Gate 7 per label

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

r = 0.843 against contributing cohorts, 0.798 against log10 training cells.

## What this changes, and what it does not

- **No verdict moves.** Gate 6 still passes on its declared rule and Gate 7 still reports 0.3309. This is a reporting fix, not a re-scoring.
- **It changes the claim that can be written.** "The model fails on 40% of clusters" is wrong; "the metric includes clusters no model could learn on that fold, and separately the model fails on thin classes" is right, and the second half is the real limitation.
- **It does not rescue the thin classes.** Clusters carried by 1-2 cohorts have training data and still score near zero. That is a genuine failure and the learnable-only number still contains it.

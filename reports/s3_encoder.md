# Stage 3 - cell encoder + domain-adversarial training (GATE 3)

**PASS** - shipped lambda = **0** - 39.8 min on cuda.

Arm **absent** from Gate 2. Label space: 25 Stage 1b clusters, 3 flagged
unreliable and held out of every headline number (stroma waiver, D-23/D-32).

## The gate

| check                              | result     | detail                                                                                                                                                                                           |
|:-----------------------------------|:-----------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1  beats majority-class by >= 0.05 | PASS       | shipped F1 0.3642 vs majority 0.0078 - margin +0.3564                                                                                                                                            |
| 1  beats random-uniform            | PASS       | shipped F1 0.3642 vs random 0.0466 - margin +0.3176                                                                                                                                              |
| 2  lambda selection                | decided    | ship lambda = 0 - the FALLBACK: no lambda beat the plain encoder                                                                                                                                 |
| 3  retained bits fall with lambda  | yes        | diagnostic only - 3.50 > 3.45 > 3.38 > 3.12 > 2.65                                                                                                                                               |
| 4  cohort guard (INVERTED)         | OK         | cohort accuracy 0.775 vs chance 0.250, guard 0.375                                                                                                                                               |
| 5  hiding vs removing              | diagnostic | co-trained 2.20 bits vs fresh 3.50 bits, gap -1.30 - lambda=0, so there is NO adversary and this gap is only the linear co-trained head being weaker than the 3-layer probe. Not a hiding signal |

Thresholds were declared in `pipeline2/panel/gate3_expect.csv` before this run. Two rows in that
file are marked REPLACED and kept alongside their replacements: the decision metric (D-31) and the
fresh-probe split (D-35).

## Per lambda

|   lam |   f1_core |   f1_maj |   f1_rnd |   fresh |    cotr |    coh |
|------:|----------:|---------:|---------:|--------:|--------:|-------:|
|  0    |    0.3642 |   0.0078 |   0.0466 |  3.5043 |  2.2042 | 0.7755 |
|  0.01 |    0.346  |   0.0078 |   0.0466 |  3.4503 |  1.4186 | 0.5515 |
|  0.03 |    0.3588 |   0.0078 |   0.0466 |  3.3772 | -0.8458 | 0.3819 |
|  0.1  |    0.3425 |   0.0078 |   0.0466 |  3.1205 | -3.2855 | 0.2307 |
|  0.3  |    0.2949 |   0.0078 |   0.0466 |  2.6539 | -2.0203 | 0.2636 |

`f1_core` is macro-F1 over the reliable clusters, averaged over the 5 LOCO folds. `f1_maj` and
`f1_rnd` are a majority-class and a random-uniform predictor scored on the same folds under the
same waiver - check 1 compares against them rather than a guessed threshold. `fresh` and `cotr`
are retained slide bits: `log2(N_slides) - CE_bits`, zero at chance.

## Every fold

|   lam | held     |   f1_core |   f1_all |   f1_waived |   f1_majority |   f1_random |    f1_l2 |   n_l2_cells |   fresh_bits |   fresh_acc |   cotrained_bits |   cohort_acc |   n_cohort |   n_slide |   seconds |
|------:|:---------|----------:|---------:|------------:|--------------:|------------:|---------:|-------------:|-------------:|------------:|-----------------:|-------------:|-----------:|----------:|----------:|
|  0    | CRC      |    0.277  |   0.2634 |      0.0723 |        0.0101 |      0.0421 |   0.3769 |         4978 |       3.5453 |      0.1474 |           2.4568 |       0.8211 |          4 |       648 |     110.6 |
|  0    | UPMC     |    0.3848 |   0.3464 |      0      |        0      |      0.0522 |   0.4243 |         7530 |       3.6263 |      0.1708 |           2.5723 |       0.8052 |          4 |       534 |     163.5 |
|  0    | Keren    |    0.3978 |   0.349  |      0.105  |        0      |      0.0465 |   0.4002 |         6315 |       3.3098 |      0.1212 |           2.3962 |       0.9597 |          4 |       716 |     153.1 |
|  0    | Phillips |    0.4287 |   0.3855 |      0.1475 |        0.0158 |      0.0478 | nan      |            0 |       3.5613 |      0.1556 |           1.9981 |       0.7001 |          4 |       696 |     110.6 |
|  0    | Sorin    |    0.3324 |   0.3367 |      0.3838 |        0.0131 |      0.0443 | nan      |            0 |       3.4786 |      0.1668 |           1.5977 |       0.5912 |          4 |       378 |      84.2 |
|  0.01 | CRC      |    0.2585 |   0.2605 |      0.2875 |        0.0101 |      0.0421 |   0.3698 |         4978 |       3.5573 |      0.1539 |           1.8443 |       0.6174 |          4 |       648 |     127   |
|  0.01 | UPMC     |    0.4018 |   0.3616 |      0      |        0      |      0.0522 |   0.4409 |         7530 |       3.5361 |      0.1703 |           0.681  |       0.3434 |          4 |       534 |     164.1 |
|  0.01 | Keren    |    0.3089 |   0.2683 |      0.0654 |        0      |      0.0465 |   0.329  |         6315 |       3.173  |      0.1174 |           1.0961 |       0.5158 |          4 |       716 |     158.8 |
|  0.01 | Phillips |    0.4299 |   0.3913 |      0.1791 |        0.0158 |      0.0478 | nan      |            0 |       3.5166 |      0.1509 |           1.8976 |       0.7168 |          4 |       696 |     111.1 |
|  0.01 | Sorin    |    0.3307 |   0.3346 |      0.3773 |        0.0131 |      0.0443 | nan      |            0 |       3.4683 |      0.1666 |           1.5742 |       0.5641 |          4 |       378 |      84.1 |
|  0.03 | CRC      |    0.2716 |   0.2739 |      0.3063 |        0.0101 |      0.0421 |   0.3754 |         4978 |       3.4306 |      0.1368 |          -0.2163 |       0.2721 |          4 |       648 |      94.7 |
|  0.03 | UPMC     |    0.3646 |   0.3281 |      0      |        0      |      0.0522 |   0.4197 |         7530 |       3.327  |      0.1542 |          -2.7024 |       0.2971 |          4 |       534 |     105.3 |
|  0.03 | Keren    |    0.3237 |   0.2726 |      0.0175 |        0      |      0.0465 |   0.3694 |         6315 |       3.1237 |      0.1111 |          -0.9109 |       0.4807 |          4 |       716 |     115.8 |
|  0.03 | Phillips |    0.4507 |   0.4137 |      0.2105 |        0.0158 |      0.0478 | nan      |            0 |       3.5006 |      0.1489 |           0.0736 |       0.4838 |          4 |       696 |     116.1 |
|  0.03 | Sorin    |    0.3835 |   0.3689 |      0.2081 |        0.0131 |      0.0443 | nan      |            0 |       3.5039 |      0.1824 |          -0.4729 |       0.3761 |          4 |       378 |     137.5 |
|  0.1  | CRC      |    0.2236 |   0.2087 |      0      |        0.0101 |      0.0421 |   0.3414 |         4978 |       3.3608 |      0.1284 |          -2.0077 |       0.2451 |          4 |       648 |      57.8 |
|  0.1  | UPMC     |    0.3005 |   0.2705 |      0      |        0      |      0.0522 |   0.3506 |         7530 |       3.0814 |      0.1253 |          -1.1868 |       0.2528 |          4 |       534 |      57.8 |
|  0.1  | Keren    |    0.3746 |   0.3269 |      0.0883 |        0      |      0.0465 |   0.384  |         6315 |       2.8047 |      0.0898 |          -1.3027 |       0.2116 |          4 |       716 |      63.3 |
|  0.1  | Phillips |    0.4063 |   0.3461 |      0.0148 |        0.0158 |      0.0478 | nan      |            0 |       3.2518 |      0.1332 |          -0.558  |       0.1937 |          4 |       696 |      68.5 |
|  0.1  | Sorin    |    0.4076 |   0.4099 |      0.4347 |        0.0131 |      0.0443 | nan      |            0 |       3.1039 |      0.1468 |         -11.3722 |       0.2503 |          4 |       378 |      84.3 |
|  0.3  | CRC      |    0.243  |   0.2531 |      0.3942 |        0.0101 |      0.0421 |   0.2872 |         4978 |       2.8366 |      0.0999 |          -2.3178 |       0.2119 |          4 |       648 |      41.6 |
|  0.3  | UPMC     |    0.3028 |   0.2797 |      0.0717 |        0      |      0.0522 |   0.3398 |         7530 |       2.7513 |      0.1089 |          -2.5412 |       0.2777 |          4 |       534 |      41.7 |
|  0.3  | Keren    |    0.2717 |   0.2411 |      0.0882 |        0      |      0.0465 |   0.3058 |         6315 |       2.3698 |      0.0611 |          -5.4172 |       0.2235 |          4 |       716 |      47   |
|  0.3  | Phillips |    0.3453 |   0.2961 |      0.0254 |        0.0158 |      0.0478 | nan      |            0 |       2.8617 |      0.1029 |           0.4731 |       0.3528 |          4 |       696 |      41.5 |
|  0.3  | Sorin    |    0.3115 |   0.3324 |      0.5628 |        0.0131 |      0.0443 | nan      |            0 |       2.4503 |      0.1202 |          -0.2982 |       0.2523 |          4 |       378 |      46.8 |

## How the slide probe is scored (D-35)

The declared design said "train a new discriminator from scratch, score on slides it never saw".
That is structurally impossible. The probe is an N-way SLIDE classifier, so holding out slide IDs
asks it to name classes it never saw one example of - it can never be right. The first smoke run
measured exactly that: `fresh_acc` 0.000000 on 4 of 4 folds and retained bits of -28.5 against a
ceiling of log2(751) = 9.55, a value the quantity cannot take. The co-trained column had the same
defect more gently, because `slide_split` makes the train and val slides disjoint.

What the measurement is for is unchanged. A co-trained discriminator can be beaten without the
information being gone - the encoder only has to find a direction that one discriminator is not
looking in. The protection against that is that the probe is **freshly initialised and never
adversarially trained**, not that it meets unfamiliar slides. So the split moved to CELLS: the
probe trains on the training draw and is scored on `sprobe`, 594 slides' worth
of cells held out of training and drawn from the same slides. The co-trained head is now scored on
the same cells, so the gap between the two columns compares like with like.

## Secondary - L2, 3 of 5 folds

The plan's original metric, kept so the switch to clusters is auditable rather than a quiet
substitution. L2 exists for CRC, Keren and UPMC only; Phillips and Sorin have no L2 truth, and
ferguson is frozen. A predicted cluster is read as an L2 class by majority vote inside the
held-out cohort's own hand mapping - the hand mapping as a TEST SET, which is what D-4 permits.
Never decides anything.

|   lam | held     |   f1_core |    f1_l2 |   n_l2_cells |
|------:|:---------|----------:|---------:|-------------:|
|  0    | CRC      |    0.277  |   0.3769 |         4978 |
|  0    | UPMC     |    0.3848 |   0.4243 |         7530 |
|  0    | Keren    |    0.3978 |   0.4002 |         6315 |
|  0    | Phillips |    0.4287 | nan      |            0 |
|  0    | Sorin    |    0.3324 | nan      |            0 |
|  0.01 | CRC      |    0.2585 |   0.3698 |         4978 |
|  0.01 | UPMC     |    0.4018 |   0.4409 |         7530 |
|  0.01 | Keren    |    0.3089 |   0.329  |         6315 |
|  0.01 | Phillips |    0.4299 | nan      |            0 |
|  0.01 | Sorin    |    0.3307 | nan      |            0 |
|  0.03 | CRC      |    0.2716 |   0.3754 |         4978 |
|  0.03 | UPMC     |    0.3646 |   0.4197 |         7530 |
|  0.03 | Keren    |    0.3237 |   0.3694 |         6315 |
|  0.03 | Phillips |    0.4507 | nan      |            0 |
|  0.03 | Sorin    |    0.3835 | nan      |            0 |
|  0.1  | CRC      |    0.2236 |   0.3414 |         4978 |
|  0.1  | UPMC     |    0.3005 |   0.3506 |         7530 |
|  0.1  | Keren    |    0.3746 |   0.384  |         6315 |
|  0.1  | Phillips |    0.4063 | nan      |            0 |
|  0.1  | Sorin    |    0.4076 | nan      |            0 |
|  0.3  | CRC      |    0.243  |   0.2872 |         4978 |
|  0.3  | UPMC     |    0.3028 |   0.3398 |         7530 |
|  0.3  | Keren    |    0.2717 |   0.3058 |         6315 |
|  0.3  | Phillips |    0.3453 | nan      |            0 |
|  0.3  | Sorin    |    0.3115 | nan      |            0 |

## The cohort guard reads backwards

Check 4 is the one number in this project where FAILING LOW is the bad outcome. Cohort is
confounded with tissue on this roster - colorectal, head and neck, breast, lung, skin twice - so
an embedding that cannot tell the cohorts apart cannot tell colon from lung either, and colon and
lung tumour cells genuinely differ. Driving cohort accuracy to chance would be destruction of
biology reported as success. That is why the cohort head carries only 0.1 of lambda and
why the domain being erased is SLIDE, not cohort (D-16).

Measured at the shipped lambda: **0.775** against chance 0.250.

# Stage 10 - the external baseline (closes H13a)

MAPS (Shaban et al., *Nat Commun* 2023) reimplemented from its published Methods and run on the **identical LOCO folds, identical 25-cluster Stage 1b label space, identical slide splits and identical drawn cells** as Gate 6. Loader asserted bit-identical to `s6.load_cohort` (check 0). Nothing was tuned for either side.

## macro-F1 (reliable clusters), per held-out cohort

| arm                       |    CRC |   Keren |   Phillips |   Sorin |   UPMC |   mean |
|:--------------------------|-------:|--------:|-----------:|--------:|-------:|-------:|
| STAGE 6 (proto2, shipped) | 0.2983 |  0.4058 |     0.427  |  0.4432 | 0.3763 | 0.3901 |
| maps_core9                | 0.2253 |  0.4287 |     0.3463 |  0.4214 | 0.302  | 0.3447 |
| gbm_core9                 | 0.2377 |  0.4115 |     0.3326 |  0.373  | 0.2676 | 0.3245 |
| gbm_full99                | 0.2406 |  0.4885 |     0.4359 |  0.2347 | 0.2167 | 0.3233 |
| maps_full99_area          | 0.2638 |  0.1432 |     0.3853 |  0.1771 | 0.1836 | 0.2306 |
| maps_full99               | 0.2173 |  0.154  |     0.3982 |  0.1644 | 0.124  | 0.2116 |

## Paired comparison against Gate 6

Per-fold differences with a bootstrap 95% interval. n=5, so this is an interval, not a significance claim (H9).

| baseline | Stage 6 - baseline | 95% CI | folds Stage 6 wins |
|---|---|---|---|
| maps_core9 | **+0.0454** | [+0.0054, +0.0766] | 4/5 |
| maps_full99 | **+0.1785** | [+0.0839, +0.2628] | 5/5 |
| maps_full99_area | **+0.1595** | [+0.0690, +0.2500] | 5/5 |
| gbm_core9 | **+0.0656** | [+0.0276, +0.0962] | 4/5 |
| gbm_full99 | **+0.0668** | [-0.0251, +0.1587] | 3/5 |

An interval that spans zero means the shipped model is **not** demonstrably better than that baseline on this roster.

## What each arm means

- `*_core9` - the 9 markers every training cohort measures. The only fixed panel a single-panel method could actually be given here.
- `*_full99` - all 99 vocabulary slots with unmeasured markers set to **0**. This is the failure mode Stage 2 exists to fix; the gap between core9 and full99 is its cost, measured against an outside architecture rather than asserted.
- `*_area` - adds cell area, which MAPS's published input includes and the token model does not, so the baseline cannot be said to have been starved.


25 fits, 40.9 min, CPU.

"""
STEP 9 - Diagnostics for the evaluation report.

For each LOCO fold (train 4 cohorts, test held-out):
  1. per-class F1 at L1 for expr vs expr+spatial  -> WHERE does spatial help / what fails
  2. L1 confusion matrix (expr+spatial)            -> WHICH classes get confused (root cause)
  3. grouped spatial-feature permutation importance -> WHICH spatial feature matters how much
     (permute one spatial sub-block in the test set, measure the L1 macro-F1 drop)

Outputs: harmonised/model/step9_{blocks,perclass,confusion}.csv + _audit/step9_report.md
Reuses step8_model.features / feature columns.
"""
import numpy as np, pandas as pd, os, json
from sklearn.metrics import f1_score, confusion_matrix
import step8_model as s8
from step8_model import features, EXPR_COLS, SPA_COLS, L2_L1, PER_COHORT_TRAIN, fit_eval
from common import COHORTS, OUT, AUDIT

BACKBONE = s8.BACKBONE
MODEL = os.path.join(OUT, "model")
RNG = np.random.default_rng(0)
ALL = EXPR_COLS + SPA_COLS

SPATIAL_BLOCKS = {
    'nb_mean':   [f'nb_mean_{m}'  for m in BACKBONE],
    'nb_std':    [f'nb_std_{m}'   for m in BACKBONE],
    'img_mean':  [f'img_mean_{m}' for m in BACKBONE],
    'img_pos':   [f'img_pos_{m}'  for m in BACKBONE],
    'density':   ['density_30um'],
    'micro_env': [f'me_{k}' for k in range(15)],
}
L1S = ['Immune', 'Stromal', 'Epithelial/Tumour']

def macroF1(y, p): return f1_score(y, p, average='macro', labels=sorted(pd.unique(y)), zero_division=0)

def main():
    print("caching training subsamples ...", flush=True)
    TRAIN = {}
    for c in COHORTS:
        F = features(c); g = F[F.L2 != '']
        TRAIN[c] = (g.sample(min(len(g), PER_COHORT_TRAIN), random_state=0) if len(g) > PER_COHORT_TRAIN else g).copy()
        del F

    blocks_rows, perclass_rows, conf_rows = [], [], []
    for held in COHORTS:
        tr = pd.concat([TRAIN[c] for c in COHORTS if c != held], ignore_index=True)
        te = features(held)
        ytr = tr.L2.values; wtr = tr.conf.values
        yL1 = te.L1.values

        # train both models
        clf_e, _ = fit_eval(tr, ytr, wtr, te.head(1), EXPR_COLS)
        clf_s, _ = fit_eval(tr, ytr, wtr, te.head(1), ALL)
        Xe = te[EXPR_COLS].to_numpy('float32'); Xs = te[ALL].to_numpy('float32')
        pe_L1 = pd.Series(clf_e.predict(Xe)).map(L2_L1).values
        ps_L1 = pd.Series(clf_s.predict(Xs)).map(L2_L1).values
        base_s = macroF1(yL1, ps_L1)

        # 1. per-class F1 (L1), expr vs +spatial
        fe = f1_score(yL1, pe_L1, average=None, labels=L1S, zero_division=0)
        fs = f1_score(yL1, ps_L1, average=None, labels=L1S, zero_division=0)
        for i, cls in enumerate(L1S):
            perclass_rows.append(dict(held_out=held, L1_class=cls,
                                      support=int((yL1 == cls).sum()),
                                      expr_F1=round(fe[i], 3), spatial_F1=round(fs[i], 3),
                                      dF1=round(fs[i]-fe[i], 3)))

        # 2. confusion (row-normalised, +spatial)
        cm = confusion_matrix(yL1, ps_L1, labels=L1S)
        cmn = cm / cm.sum(1, keepdims=True).clip(min=1)
        for i, cls in enumerate(L1S):
            conf_rows.append(dict(held_out=held, true=cls,
                                  **{f'pred_{L1S[j]}': round(cmn[i, j], 3) for j in range(len(L1S))}))

        # 3. grouped spatial permutation importance (drop in +spatial L1 macro-F1)
        Xs_df = te[ALL].copy()
        row = dict(held_out=held, base_spatial_F1=round(base_s, 4))
        for bname, bcols in SPATIAL_BLOCKS.items():
            cols = [c for c in bcols if c in Xs_df.columns]
            Xp = Xs_df.copy()
            perm = RNG.permutation(len(Xp))
            for c in cols:
                Xp[c] = Xp[c].values[perm]
            pp = pd.Series(clf_s.predict(Xp[ALL].to_numpy('float32'))).map(L2_L1).values
            row[f'drop_{bname}'] = round(base_s - macroF1(yL1, pp), 4)
        blocks_rows.append(row)
        print(f"[{held:8s}] base+spatial L1={base_s:.4f}  "
              + "  ".join(f"{b}={row['drop_'+b]:+.4f}" for b in SPATIAL_BLOCKS), flush=True)
        del te, Xs_df

    pd.DataFrame(blocks_rows).to_csv(os.path.join(MODEL, "step9_blocks.csv"), index=False)
    pd.DataFrame(perclass_rows).to_csv(os.path.join(MODEL, "step9_perclass.csv"), index=False)
    pd.DataFrame(conf_rows).to_csv(os.path.join(MODEL, "step9_confusion.csv"), index=False)

    B = pd.DataFrame(blocks_rows); PC = pd.DataFrame(perclass_rows); CF = pd.DataFrame(conf_rows)
    rep = ["# STEP 9 - Diagnostics\n",
           "## Spatial-feature importance (L1 macro-F1 drop when that block is permuted in test)\n",
           B.to_markdown(index=False),
           f"\nmean drop per block:\n" + pd.DataFrame({'mean_drop':
                B[[f'drop_{b}' for b in SPATIAL_BLOCKS]].mean().round(4)}).to_markdown(),
           "\n\n## Per-class F1 at L1 (expr vs +spatial)\n", PC.to_markdown(index=False),
           "\n\n## L1 confusion (row-normalised, +spatial)\n", CF.to_markdown(index=False)]
    open(os.path.join(AUDIT, "step9_report.md"), "w", encoding="utf-8").write("\n".join(rep))
    print("\nwrote step9_{blocks,perclass,confusion}.csv + step9_report.md", flush=True)

if __name__ == "__main__":
    main()

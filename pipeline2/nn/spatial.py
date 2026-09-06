"""
STAGE 4 - adaptive spatial context. Produces `z_neigh` beside Stage 3's `z_cell`.

WHAT THIS IS. A cell's identity is partly its neighbourhood: a T cell inside a tumour nest and a
T cell in a lymphoid aggregate are the same cell type but different biology, and some types are
only separable in context. Stage 4 gives each cell a second vector describing what surrounds it.

THE DESIGN CONSTRAINT THAT SHAPED THIS FILE. Encoding all k neighbours through the set
transformer would cost (k+1)x a Stage 6 fit - about 18 h on a T4 for the gate, which does not
fit the budget. Instead the neighbours are pooled IN VALUE SPACE with learned distance weights,
and the pooled profile is encoded ONCE by the same CellEncoder. That is 2x, not 16x.

This is not a shortcut around the design; it is what the design asked for. files/05 4.8 sets the
expectation in advance: "any gain must come from the learned distance weighting, not from
switching to kNN". A distance-weighted mean with weights learned from the edge features IS one
round of message passing with a learned edge function, computed with plain tensor ops - and
files/05 also required "plain scatter ops so it needs no torch_geometric", which is not
installed and is not on Kaggle by default.

WHY THE POOLED PROFILE STAYS A VALID INPUT. `u_coh` is an ECDF rank in [0, 1]. The pooling
weights are a softmax, so the pooled vector is a convex combination and stays in [0, 1] - the
same range the shared value MLP was trained on. Feeding it through the same encoder is therefore
meaningful rather than out-of-distribution, and the encoder's [ABSENT] logic still applies
unchanged because a neighbour has the same panel as the cell it neighbours.

EDGE FEATURES AND THE UPMC PROBLEM (M4). UPMC's px_um is marked
'ASSUMED - not published anywhere', and Stage 4 is the only stage that ever uses physical
distance, so that assumption stops being harmless here. The edge vector therefore carries BOTH
an absolute and a scale-free measure of distance:

    d_rel = d / (median nearest-neighbour distance in that image)

A wrong global um/px for UPMC cancels in d_rel, because numerator and denominator scale
together. The absolute term is kept as well so the model can use real distance where the scale
IS trustworthy, and Gate 4 reports a sensitivity arm that rescales UPMC's px_um to check the
verdict does not depend on it.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class NeighbourPool(nn.Module):
    """kNN marker profiles -> one pooled profile per cell, with learned distance weights.

    forward(nbr_u, edge, valid)
      nbr_u  (B, k, V) float  each neighbour's u_coh over the vocabulary
      edge   (B, k, E) float  per-edge features (distance terms)
      valid  (B, k)    bool   False where the cell has fewer than k neighbours
      returns pooled (B, V) in [0, 1], and has_nbr (B,) bool

    An invalid edge gets a -inf logit, so it is excluded from the softmax rather than
    contributing a small weight. A cell with NO valid neighbour (an isolated cell in a sparse
    image) returns zeros and has_nbr=False; the caller substitutes a learned vector, because
    falling back to the cell's own profile would make z_neigh a copy of z_cell and Gate 4's
    first check would measure nothing.
    """

    def __init__(self, e_dim=4, hidden=32):
        super().__init__()
        self.mlp = nn.Sequential(nn.Linear(e_dim, hidden), nn.GELU(), nn.Linear(hidden, 1))

    def forward(self, nbr_u, edge, valid):
        logit = self.mlp(edge).squeeze(-1)                       # (B, k)
        logit = logit.masked_fill(~valid, float('-inf'))
        has = valid.any(dim=1)
        # a row with no valid neighbour is all -inf and softmax would return NaN, so give it a
        # single dummy slot first and mask the result afterwards
        safe = torch.where(has.unsqueeze(1), logit, torch.zeros_like(logit))
        w = F.softmax(safe, dim=1).unsqueeze(-1)                 # (B, k, 1)
        pooled = (w * nbr_u).sum(dim=1)                          # (B, V)
        return pooled * has.unsqueeze(-1).float(), has


class SpatialContext(nn.Module):
    """Wraps a CellEncoder so one call returns both z_cell and z_neigh.

    The encoder is SHARED, not duplicated. Two reasons. The neighbourhood profile lives in the
    same space as a cell profile, so a second encoder would have to relearn the same value
    pathway from scratch on the same data. And sharing keeps the parameter count close to
    Stage 6's, so Gate 4 check 1 compares spatial information against no spatial information
    rather than a big model against a small one.
    """

    def __init__(self, enc, d_z, e_dim=4):
        super().__init__()
        self.enc = enc
        self.pool = NeighbourPool(e_dim=e_dim)
        self.no_neigh = nn.Parameter(torch.zeros(d_z))

    def forward(self, u, idx, present, nbr_u, edge, valid, hide=None, return_tokens=False):
        out = self.enc(u, idx, present, hide=hide, return_tokens=return_tokens)
        z, tok = out if return_tokens else (out, None)
        pooled, has = self.pool(nbr_u, edge, valid)
        zn = self.enc(pooled, idx, present)
        zn = torch.where(has.unsqueeze(-1), zn, self.no_neigh.expand_as(zn))
        return (z, zn, tok) if return_tokens else (z, zn)


def context_loss(pred, pooled, present):
    """The neighbourhood-context auxiliary loss - Stage 6's missing fourth loss (D-40).

    Predict the pooled neighbourhood marker profile from z_cell ALONE. It is label-free, so it
    trains on every cell of every cohort, and it forces the cell embedding to carry something
    about its surroundings rather than leaving all context in z_neigh.

    This loss could not be written before Stage 4 existed - it has no input without a pooled
    neighbourhood - which is why gate6_expect.csv records the declared "2 vs 4 losses" ablation
    as having been run as a 2 vs 3. With this it is a real 2 vs 4 for the first time.

    Scored only on slots the cohort MEASURES. An absent slot carries no value to predict, and
    including it would reward the model for predicting the [ABSENT] placeholder.
    """
    m = present.view(1, -1).expand_as(pred)
    if not bool(m.any()):
        return pred.sum() * 0.0
    return F.mse_loss(pred[m], pooled[m])

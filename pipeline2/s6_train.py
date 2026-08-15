"""
STAGE 6 - losses and training.  Produces GATE 6.

    python s6_train.py --ablate-losses          # GATE 6
    python s6_train.py --ablate-losses --quick  # smoke test: proves the code path, scores nothing
    python s6_train.py --ablate-losses --refit  # ignore the checkpoint cache
    python s6_train.py --ablate-losses --cpu    # force CPU even where a GPU exists

WHAT THIS STAGE IS. Stage 3 produced z_cell with a deliberately plain linear head, so that Gate 3
could ask one question without a second moving part. Stage 6 is where the real training objective
goes: a prototype loss over Stage 1b's clusters, the guards that make learnable prototypes safe,
and the auxiliary losses that keep the representation general.

THREE THINGS THE DESIGN ASKED FOR ARE NOT HERE, each for a stated reason. All three are declared
in pipeline2/panel/gate6_expect.csv, which was committed before this file was written.

  Descendant-tolerant cross-entropy. It needs Stage 1b's nesting graph, which missed ALL THREE
  cases declared for it (section 7 gap 2 / H2). The design says outright: do not rely on it until
  nesting is re-tested. A loss over an untrusted parent/child graph rewards wrong predictions
  silently, and the failure reads as a modelling result rather than a graph defect. Deferred, not
  rejected - re-test nesting and it drops in without touching anything else.

  The neighbourhood-context auxiliary loss. It predicts a cell's spatial surroundings from
  z_neigh, which Stage 4 produces, and Stage 4 is deferred (D-18). It has no input and cannot be
  written. SO THE DECLARED "2 vs 4 LOSSES" ABLATION IS A 2 vs 3 - cell-type, masked-marker,
  VICReg. Reported as such rather than quietly renumbered.

  The adversary. Gate 3 swept 5 lambdas x 5 folds and none beat lambda=0 (D-36), so carrying it
  would be the same encoder with extra moving parts.

WHAT GATE 6 DECIDES. Check 3 chooses which losses ship. Check 4 asks whether the stage earned its
existence at all, by re-measuring Stage 3's plain linear head INSIDE THIS RUN on the same encoder
and the same vocabulary - Gate 3's own 0.3642 is not comparable, because it was produced on an
88-triple vocabulary before D-39 fixed that.
"""
import os, sys, json, time, zlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.nn.functional as F

import config
from config import SPECS, WORK, REPORTS, FIGURES, SEED
from nn.encoder import CellEncoder
from nn.losses import (Prototypes, CollapseGuard, KendallSigma, vicreg,
                       masked_marker_loss, confidence_weighted_ce)
import s2_tokens as s2
import s3_encoder as s3

CKPT = os.path.join(WORK, 'ckpt')
CONF = os.path.join(WORK, 'label_conf')
os.makedirs(CKPT, exist_ok=True)

DEV = torch.device('cuda' if (torch.cuda.is_available() and '--cpu' not in sys.argv) else 'cpu')

# --------------------------------------------------------------- declared constants
D_TOK, D_Z    = 64, 128
BLOCKS, HEADS = 2, 4
N_TRAIN       = 15_000
SCORE_CELLS   = 8_000
BATCH, LR     = 512, 1e-3
EPOCHS, PATIENCE = 30, 4
MASK_FRAC     = 0.15          # same fraction Stage 2 used
PROTO_TEMP    = 0.1
SPREAD_MIN    = 0.20          # D-28's exclusion floor, inherited (D-33 warned it recurs here)
COLLAPSE_FRAC = 0.5           # check 2: min prototype distance may not halve
SIGMA_CAP     = 3.0           # check 1: how far an auxiliary log-sigma may travel
LINEAR_MARGIN = 0.02          # check 4: Stage 6 must beat the plain linear head by this


def _rng(*p):
    return np.random.default_rng(SEED ^ (zlib.crc32('|'.join(map(str, p)).encode()) & 0xffffffff))


# ----------------------------------------------------------------------------- data
def excluded_pairs():
    """Stage 2's (cohort, marker) exclusion set, inherited by the masked-marker loss.

    D-33 flagged this explicitly: "recurs in Stage 6, whose masked-marker auxiliary loss inherits
    the same exclusion set". A pair below the rank_spread floor has a collapsed R2 denominator -
    predicting it teaches nothing and the gradient is noise.
    """
    p = os.path.join(WORK, 's2_dynrange.csv')
    if not os.path.exists(p):
        return set()
    d = pd.read_csv(p)
    return {(r.cohort, r.triple) for r in d.itertuples() if r.rank_spread < SPREAD_MIN}


def load_conf(c, cell_ids):
    """Per-cell label confidence, or all-ones where a cohort has none.

    1-of-5 coverage and the report says so: only UPMC ships kNN.prob (0.14-1.0). The absence of a
    file MEANS a constant confidence, so this is not a silent default - see s6_confidence.py.
    """
    p = os.path.join(CONF, f'{c}.parquet')
    if not os.path.exists(p):
        return np.ones(len(cell_ids), 'float32'), False
    m = pd.read_parquet(p).set_index('cell_id').conf
    return m.reindex(cell_ids).fillna(1.0).to_numpy('float32'), True


def load_cohort(c, triples_c, tri2idx, n_vocab, L, excl, draw_seed=None):
    """One cohort as tensors. Mirrors Stage 3's loader and adds confidence and the mask-eligible
    slot list, so Stage 6 is scored on exactly the cells Stage 3 was.

    `draw_seed` varies WHICH CELLS are drawn. Default None reproduces every gate result to the
    bit - Gates 3, 6 and 7 all ran without it. Step 3's repeated-seed runs pass it so their
    intervals cover the cell draw as well as the model initialisation; an interval over model
    seeds alone would be narrower than the truth and would look like more precision than there is.
    """
    tl = list(triples_c)
    v = pd.read_parquet(s2.full_table(c),
                        columns=['cell_id', 'image_id', 'native_label'] +
                                [f'u_coh::{t}' for t in tl])
    y = np.array([L['key'].get((c, str(lab)), -1) for lab in v.native_label])
    ok = y >= 0
    if not ok.any():
        return None
    v, y = v[ok].reset_index(drop=True), y[ok]
    U = v[[f'u_coh::{t}' for t in tl]].to_numpy('float32')
    img = np.array([f'{c}|{s}' for s in v.image_id])
    conf, has_conf = load_conf(c, v.cell_id.to_numpy())

    tr_s, va_s, te_s = s2.slide_split(c, np.unique(img))

    def draw(slides, cap, why):
        w = np.flatnonzero(np.isin(img, list(slides)))
        if len(w) > cap:
            key = ('draw', c, why) if draw_seed is None else ('draw', c, why, draw_seed)
            w = np.sort(_rng(*key).choice(w, cap, replace=False))
        return w

    parts = dict(train=draw(tr_s, N_TRAIN, 'train'), val=draw(va_s, N_TRAIN // 4, 'val'),
                 test=draw(te_s, SCORE_CELLS, 'test'))

    slots = np.array([tri2idx[t] for t in tl])
    full = np.zeros((len(U), n_vocab), 'float32')
    full[:, slots] = U
    present = np.zeros(n_vocab, bool)
    present[slots] = True
    # mask-eligible = measured here AND not on Stage 2's exclusion list (D-28/D-33)
    elig = np.zeros(n_vocab, bool)
    for t, s_ in zip(tl, slots):
        elig[s_] = (c, t) not in excl

    return dict(cohort=c, has_conf=has_conf,
                idx=torch.arange(n_vocab).long().to(DEV),
                present=torch.from_numpy(present).to(DEV),
                elig=torch.from_numpy(elig).to(DEV),
                U={k: torch.from_numpy(full[w]).to(DEV) for k, w in parts.items()},
                y={k: torch.from_numpy(y[w]).long().to(DEV) for k, w in parts.items()},
                conf={k: torch.from_numpy(conf[w]).to(DEV) for k, w in parts.items()},
                img={k: img[w] for k, w in parts.items()},
                n={k: len(w) for k, w in parts.items()})


def make_hide(B, elig, gen):
    """Hide MASK_FRAC of the eligible slots per cell, at least one."""
    e = torch.nonzero(elig).flatten()
    if len(e) == 0:
        return torch.zeros(B, len(elig), dtype=torch.bool, device=elig.device)
    k = max(1, int(round(MASK_FRAC * len(e))))
    hide = torch.zeros(B, len(elig), dtype=torch.bool, device=elig.device)
    for i in range(B):
        pick = e[torch.randperm(len(e), generator=gen, device='cpu')[:k].to(e.device)]
        hide[i, pick] = True
    return hide


# ----------------------------------------------------------------------------- prototypes
def init_prototypes(enc, n_class, V, path=None):
    """Start each prototype where Stage 1b says its cluster lives.

    `path` overrides work/prototypes.npy. Stage 7 uses it to load the centroids of a label space
    built WITHOUT the frozen holdout - same file format, different cluster set (D-48).

    work/prototypes.npy is [n_class, 99] - each cluster's mean marker signature over the canonical
    vocabulary. Each signature is fed through the encoder as a synthetic cell and the output
    becomes that cluster's starting vector. Random initialisation would throw away the one thing
    Stage 1b actually knows, and would make the drift diagnostic meaningless: drift is only
    interpretable if the starting point means something.

    THE NaNs ARE INFORMATION, NOT CORRUPTION. 751 of the 2475 entries are NaN - a cluster has no
    signature for a marker that none of its contributing cohorts measures, and clusters built from
    panel-poor cohorts have many (cluster 17 has 60). Feeding them in raw makes every prototype
    NaN, which then makes every logit, loss and sigma NaN while training still appears to run.
    They are exactly what the [ABSENT] token exists for, so each cluster is encoded with its OWN
    `present` mask and the missing values never reach the value MLP.
    """
    p = path or os.path.join(WORK, 'prototypes.npy')
    if not os.path.exists(p):
        return None
    sig = np.load(p).astype('float32')
    if sig.shape != (n_class, V):
        print(f"    prototypes.npy is {sig.shape}, expected {(n_class, V)} - random init instead")
        return None
    ok = ~np.isnan(sig)
    idx = torch.arange(V).long().to(DEV)
    out = []
    with torch.no_grad():
        for k in range(n_class):
            u = torch.from_numpy(np.nan_to_num(sig[k], nan=0.0)).to(DEV).unsqueeze(0)
            present = torch.from_numpy(ok[k]).to(DEV)
            out.append(enc(u, idx, present))
    z = torch.cat(out)
    if not bool(torch.isfinite(z).all()):
        print("    prototype init produced non-finite values - random init instead")
        return None
    return z.detach()


def warm_state():
    """Stage 2's pretrained token layer, the same warm start Stage 3 used.

    Without it Stage 6 begins from a cold encoder and its numbers are not comparable with Gate 3's
    - which would defeat check 4, whose whole job is to compare the prototype head against the
    linear head on equal terms.
    """
    arm = json.load(open(os.path.join(WORK, 'panel.json'))).get('stage2_arm', 'absent')
    p = os.path.join(CKPT, 's2_armA.pt' if arm == 'set' else 's2_armB.pt')
    if '--no-warm' in sys.argv or not os.path.exists(p):
        return None, None
    return torch.load(p, weights_only=False)['state'], os.path.basename(p)


# ----------------------------------------------------------------------------- model
class Stage6(nn.Module):
    """Encoder + the head under test. `head='proto'` is the stage; `head='linear'` is Gate 6
    check 4's control - Stage 3's plain linear head, on the same encoder, in the same run."""

    def __init__(self, n_vocab, n_class, head='proto', proto_init=None):
        super().__init__()
        self.enc = CellEncoder(n_vocab, d_tok=D_TOK, d_z=D_Z, blocks=BLOCKS, heads=HEADS)
        self.head_kind = head
        self.proto = Prototypes(n_class, D_Z, init=proto_init, temp=PROTO_TEMP) \
            if head == 'proto' else None
        self.linear = nn.Linear(D_Z, n_class) if head == 'linear' else None
        self.mask_head = nn.Linear(D_TOK, 1)

    def forward(self, u, idx, present, hide=None):
        z, tok = self.enc(u, idx, present, hide=hide, return_tokens=True)
        logits = self.proto.logits(z) if self.proto is not None else self.linear(z)
        return z, logits, self.mask_head(tok).squeeze(-1)


# ----------------------------------------------------------------------------- fit
def fit(data, train_cohorts, L, V, head='proto', use_vicreg=True, use_conf=True,
        epochs=EPOCHS, patience=PATIENCE, seed=SEED, log='', proto_path=None):
    """Train on `train_cohorts`. Early stopping on held-out SLIDES by macro-F1 - the quantity the
    gate decides on, not the loss, which is not comparable across loss sets."""
    # Build the encoder first and warm-start it, THEN read the prototypes out of that same
    # encoder. Initialising them from a different (random) encoder would place them in a space
    # the model does not use, and the drift diagnostic would measure the mismatch rather than
    # any disagreement with Stage 1b.
    torch.manual_seed(seed)
    m = Stage6(V, L['n'], head=head, proto_init=None).to(DEV)
    warm, wname = warm_state()
    if warm is not None:
        m.enc.load_stage2(warm)
    if head == 'proto':
        pi = init_prototypes(m.enc, L['n'], V, path=proto_path)
        if pi is not None:
            with torch.no_grad():
                m.proto.p.copy_(pi)
                m.proto.p0.copy_(pi)
    aux = ['mask'] + (['vicreg'] if use_vicreg else [])
    sig = KendallSigma(aux).to(DEV)
    guard = CollapseGuard(m.proto, COLLAPSE_FRAC) if m.proto is not None else None
    opt = torch.optim.Adam(list(m.parameters()) + list(sig.parameters()), lr=LR)
    gen = torch.Generator().manual_seed(seed)

    pools = {c: {int(k): np.flatnonzero(data[c]['y']['train'].cpu().numpy() == k)
                 for k in np.unique(data[c]['y']['train'].cpu().numpy())}
             for c in train_cohorts}

    best, best_state, bad, used = -np.inf, None, 0, epochs
    sig_hist, guard_hist = [], []
    for ep in range(epochs):
        m.train()
        for c in [train_cohorts[i] for i in torch.randperm(len(train_cohorts),
                                                           generator=gen).tolist()]:
            d, pool = data[c], pools[c]
            ks = list(pool)
            per = max(1, d['n']['train'] // max(1, len(ks)))
            take = np.concatenate([_rng('bal', c, ep).choice(pool[k], per,
                                                             replace=len(pool[k]) < per)
                                   for k in ks])
            take = take[_rng('shuf', c, ep).permutation(len(take))]
            for i in range(0, len(take), BATCH):
                b = torch.from_numpy(take[i:i + BATCH]).long().to(DEV)
                u = d['U']['train'][b]
                hide = make_hide(len(b), d['elig'], gen)
                z, logits, pred = m(u, d['idx'], d['present'], hide=hide)

                w = d['conf']['train'][b] if (use_conf and d['has_conf']) else None
                l_cls = confidence_weighted_ce(logits, d['y']['train'][b], w)
                losses = {'mask': masked_marker_loss(pred, u, hide)}
                if use_vicreg:
                    losses['vicreg'] = vicreg(z)
                l_aux, _ = sig(losses)
                # the cell-type weight is PINNED at 1.0 and never enters the sigma weighting -
                # Kendall is free to switch off a task whose labels look noisy, and cross-cohort
                # labels look very noisy. That is the one task that must not be switched off.
                loss = l_cls + l_aux
                opt.zero_grad(); loss.backward(); opt.step()

        sig_hist.append(sig.snapshot())
        if guard is not None:
            guard_hist.append(guard.step(ep))

        m.eval()
        yt, yp = [], []
        with torch.no_grad():
            for c in train_cohorts:
                d = data[c]
                U = d['U']['val']
                for i in range(0, len(U), 1024):
                    _, lg, _ = m(U[i:i + 1024], d['idx'], d['present'])
                    yp.append(lg.argmax(1))
                yt.append(d['y']['val'])
        f1, _ = s3.macro_f1(torch.cat(yt).cpu().numpy(), torch.cat(yp).cpu().numpy(), L['n'])
        if f1 > best + 1e-5:
            best, bad = f1, 0
            best_state = {k: v.detach().clone() for k, v in m.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                used = ep + 1
                break
    if best_state is not None:
        m.load_state_dict(best_state)
    m.eval()
    info = dict(epochs_used=used, val_f1=round(best, 4),
                sigma=sig_hist, sigma_names=aux,
                guard=guard_hist,
                guard_events=(guard.events if guard else []),
                guard_floor=(round(guard.floor, 4) if guard else None),
                guard_d0=(round(guard.d0, 4) if guard else None),
                guard_passed=(guard.passed() if guard else None),
                drift=(m.proto.drift().round(4).tolist() if m.proto is not None else None))
    return m, info


def predict(m, d):
    out = []
    with torch.no_grad():
        U = d['U']['test']
        for i in range(0, len(U), 1024):
            _, lg, _ = m(U[i:i + 1024], d['idx'], d['present'])
            out.append(lg.argmax(1))
    return torch.cat(out).cpu().numpy() if out else np.array([])


def loco_run(tag, held, train, per, tri2idx, triples, L, excl, head, use_vicreg, use_conf,
             refit, epochs):
    p = os.path.join(CKPT, f's6_{tag}.pt')
    if os.path.exists(p) and not refit:
        print(f"    [cache] {tag}")
        return torch.load(p, weights_only=False)

    t0 = time.time()
    V = len(triples)
    rest = [c for c in train if c != held]
    data = {c: load_cohort(c, per[c], tri2idx, V, L, excl) for c in train}
    data = {c: d for c, d in data.items() if d is not None}
    rest = [c for c in rest if c in data]
    if not rest:
        raise ValueError(f"fold '{held}': no training cohorts left")

    m, info = fit(data, rest, L, V, head=head, use_vicreg=use_vicreg, use_conf=use_conf,
                  epochs=epochs)
    yp = predict(m, data[held])
    yt = data[held]['y']['test'].cpu().numpy()
    f1_all, per_cls = s3.macro_f1(yt, yp, L['n'])
    f1_core, _ = s3.macro_f1(yt, yp, L['n'], drop=L['unreliable'])
    f1_maj, f1_rnd, _ = s3.baselines(data, rest, held, L['n'], L['unreliable'])

    r = dict(tag=tag, held=held, head=head, vicreg=use_vicreg, conf=use_conf,
             f1_core=f1_core, f1_all=f1_all, f1_majority=f1_maj, f1_random=f1_rnd,
             per_cls=per_cls, info=info, n_cohort=len(rest),
             seconds=round(time.time() - t0, 1),
             state={k: v.detach().cpu() for k, v in m.state_dict().items()})
    torch.save(r, p)
    g = info.get('guard_passed')
    print(f"    [done ] {tag}  F1core={f1_core:.4f} (maj {f1_maj:.4f})  "
          f"guard={'ok' if g else ('COLLAPSE' if g is False else '-')}  "
          f"{r['seconds']:.0f}s  epochs={info['epochs_used']}")
    return r


# ----------------------------------------------------------------------------- figures
def figures(ship, L):
    """The two plots the design asks for by name: sigma trajectory and prototype drift."""
    os.makedirs(FIGURES, exist_ok=True)
    out = {}
    info = ship['info']

    if info['sigma']:
        fig, ax = plt.subplots(figsize=(7, 4))
        for n in info['sigma_names']:
            ax.plot([s[n] for s in info['sigma']], label=n, lw=2)
        ax.axhline(info['sigma'][0][info['sigma_names'][0]] + SIGMA_CAP, ls='--', c='crimson',
                   lw=1, label=f'cap (+{SIGMA_CAP})')
        ax.set_xlabel('epoch'); ax.set_ylabel('log sigma')
        ax.set_title('Auxiliary log-sigma. Rising = the loss is being switched off.\n'
                     'The cell-type weight is pinned and does not appear here.', fontsize=9)
        ax.legend(fontsize=8); fig.tight_layout()
        p = os.path.join(FIGURES, 's6_sigma.png'); fig.savefig(p, dpi=130); plt.close(fig)
        out['sigma'] = p

    if info['guard']:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(info['guard'], lw=2, label='min pairwise prototype distance')
        ax.axhline(info['guard_floor'], ls='--', c='crimson', lw=1,
                   label=f"floor ({COLLAPSE_FRAC}x init)")
        for e in info['guard_events']:
            ax.axvline(e['epoch'], c='orange', lw=1, alpha=.7)
        ax.set_xlabel('epoch'); ax.set_ylabel('cosine distance')
        ax.set_title('Collapse guard. Below the floor, two clusters are merging.', fontsize=9)
        ax.legend(fontsize=8); fig.tight_layout()
        p = os.path.join(FIGURES, 's6_collapse.png'); fig.savefig(p, dpi=130); plt.close(fig)
        out['collapse'] = p

    if info.get('drift'):
        dr = np.array(info['drift'])
        o = np.argsort(-dr)
        fig, ax = plt.subplots(figsize=(7, max(3, 0.25 * len(dr))))
        ax.barh([L['names'][i] or f'cluster {i}' for i in o][::-1], dr[o][::-1], color='steelblue')
        ax.set_xlabel('cosine distance moved from the Stage 1b signature')
        ax.set_title('Prototype drift. A long bar is the model DISAGREEING with Stage 1b.',
                     fontsize=9)
        fig.tight_layout()
        p = os.path.join(FIGURES, 's6_drift.png'); fig.savefig(p, dpi=130); plt.close(fig)
        out['drift'] = p
    return out


# ----------------------------------------------------------------------------- gate
def assemble(res, L):
    d = pd.DataFrame([{k: r[k] for k in ('tag', 'held', 'head', 'vicreg', 'conf',
                                         'f1_core', 'f1_all', 'f1_majority', 'seconds')}
                      for r in res])

    # BRACKETS, NOT ATTRIBUTES. `d.head` is DataFrame.head - the method - so `d.head == 'proto'`
    # is a silent False and every arm comes back empty with a nan mean. Nothing raises.
    def arm(h, v, c=True):
        return d[(d['head'] == h) & (d['vicreg'] == v) & (d['conf'] == c)]

    three, two, lin = arm('proto', True), arm('proto', False), arm('linear', True)
    m3 = float(three.f1_core.mean()) if len(three) else float('nan')
    m2 = float(two.f1_core.mean()) if len(two) else float('nan')
    ml = float(lin.f1_core.mean()) if len(lin) else float('nan')

    use_vic = m3 > m2
    ship_f1 = m3 if use_vic else m2
    ship_name = '3 losses (+VICReg)' if use_vic else '2 losses'
    ship = next((r for r in res if r['head'] == 'proto' and r['vicreg'] == use_vic
                 and r['conf'] and r['info']['sigma']), None) or res[0]

    inf = ship['info']
    sig_move = max((abs(inf['sigma'][-1][n] - inf['sigma'][0][n]) for n in inf['sigma_names']),
                   default=0.0)
    guard_ok = inf.get('guard_passed')
    ev = inf.get('guard_events') or []

    checks = [
        dict(check='1  auxiliary sigma does not run away',
             result='PASS' if sig_move <= SIGMA_CAP else 'FAIL',
             detail=f"largest log-sigma move {sig_move:.3f} against a cap of {SIGMA_CAP}"),
        dict(check='2  prototypes do not collapse',
             result='PASS' if guard_ok else 'FAIL',
             detail=(f"floor {inf.get('guard_floor')} (init {inf.get('guard_d0')}); "
                     + (f"{len(ev)} pair(s) frozen" if ev else "no pair frozen"))),
        dict(check='3  do the extra losses earn their place',
             result=('ship 3' if use_vic else 'ship 2'),
             detail=f"3 losses {m3:.4f} vs 2 losses {m2:.4f} - delta {m3 - m2:+.4f}"),
        dict(check=f'4  beats the plain linear head by >= {LINEAR_MARGIN:.2f}',
             result='PASS' if (ship_f1 - ml) >= LINEAR_MARGIN else 'FAIL',
             detail=(f"{ship_name} {ship_f1:.4f} vs linear head {ml:.4f} "
                     f"- margin {ship_f1 - ml:+.4f}")),
    ]
    hard = [c for c in checks if c['check'][0] in '124']
    verdict = 'PASS' if all(c['result'] == 'PASS' for c in hard) else 'FAIL'
    return d, checks, verdict, ship, ship_name, ship_f1, ml, m2, m3


def write_report(path, d, checks, verdict, ship, ship_name, ship_f1, ml, m2, m3, L, figs, mins):
    def md(x):
        return x.to_markdown(index=False)

    def img(k, alt):
        return (f"\n![{alt}](figures/{os.path.basename(figs[k])})\n" if k in figs else '')

    inf = ship['info']
    drift = ''
    if inf.get('drift'):
        dd = pd.DataFrame(dict(cluster=[c or f'cluster {i}' for i, c in enumerate(L['names'])],
                               moved=np.round(inf['drift'], 4)))
        drift = md(dd.sort_values('moved', ascending=False).head(10))
    ev = inf.get('guard_events') or []
    frozen = (md(pd.DataFrame([dict(epoch=e['epoch'],
                                    a=L['names'][e['a']] or e['a'],
                                    b=L['names'][e['b']] or e['b'],
                                    distance=e['distance']) for e in ev]))
              if ev else '_No pair ever breached the floor._')
    vic_line = ('VICReg earns its place and ships.' if m3 > m2 else
                'VICReg does NOT improve macro-F1, so it is dropped. The design said to keep the '
                'extra losses only if they earn it.')

    txt = f"""# Stage 6 - losses and training (GATE 6)

**{verdict}** - ships **{ship_name}** at LOCO macro-F1 **{ship_f1:.4f}** - {mins:.1f} min on {DEV}.

Label space: {L['n']} Stage 1b clusters, {len(L['unreliable'])} flagged unreliable and held out of
every headline number (stroma waiver, D-23/D-32).

## The gate

{md(pd.DataFrame(checks))}

Thresholds were declared in `pipeline2/panel/gate6_expect.csv` before any of this code was
written. Three rows there record things the design asked for that are NOT built, each with its
reason - read them before concluding anything is missing.

## What is deliberately not in this stage

**Descendant-tolerant cross-entropy.** It needs Stage 1b's nesting graph, which missed all three
cases declared for it (section 7 gap 2). A loss over an untrusted parent/child graph rewards wrong
predictions silently, and the failure would read as a modelling result rather than a graph defect.
Deferred, not rejected.

**The neighbourhood-context loss.** It needs `z_neigh` from Stage 4, which is deferred (D-18), so
it has no input at all. **The declared "2 vs 4 losses" ablation is therefore a 2 vs 3** - cell
type, masked marker, VICReg. Check 3 below is that comparison, not the one originally written.

**The adversary.** Gate 3 swept 5 lambdas x 5 folds and none beat lambda=0 (D-36).

## Check 3 - the loss ablation

| losses | LOCO macro-F1 |
|---|---|
| 2 - cell type + masked marker | {m2:.4f} |
| 3 - plus VICReg | {m3:.4f} |

{vic_line}

## Check 4 - did this stage earn its existence

| head | LOCO macro-F1 |
|---|---|
| Stage 3's plain linear head, same encoder, same run | {ml:.4f} |
| Stage 6 prototype loss ({ship_name}) | {ship_f1:.4f} |
| **margin** | **{ship_f1 - ml:+.4f}** against a required {LINEAR_MARGIN:+.2f} |

The linear control is re-measured INSIDE this run rather than read from Gate 3's report. Gate 3
ran on an 88-triple vocabulary before D-39 fixed that, so its 0.3642 is not comparable with
anything produced afterwards. Same discipline as Gate 2's core-9 control (D-27): measure the
baseline in the same run, or the comparison changes two things at once.

## Every run

{md(d.round(4))}

## Check 1 - the sigma trajectory
{img('sigma', 'auxiliary log-sigma over epochs')}
Kendall uncertainty weighting can switch a loss off by driving its sigma up - the weight is
1/(2 sigma^2), so a runaway sigma silently deletes the term while training still looks healthy.
**The cell-type sigma is pinned at 1.0 and is not learned**, because cross-cohort labels come from
six annotation schemes and look extremely noisy, which is exactly the condition under which
Kendall weighting would switch off the one task that matters.

## Check 2 - the collapse guard
{img('collapse', 'minimum pairwise prototype distance over epochs')}
Learnable prototypes can silently merge two classes, and macro-F1 over classes present in the
truth does not necessarily expose it. A breach freezes the pair and logs it rather than aborting -
a merge may be a true statement about the label space.

{frozen}

## Prototype drift - a diagnostic, not a failure
{img('drift', 'how far each prototype moved from its Stage 1b signature')}
Prototypes start at their Stage 1b marker signature and are learnable on purpose, so the protein
data may correct the clustering. A large move is the model DISAGREEING with Stage 1b about where
that cluster lives. That disagreement is a finding worth reading, not a bug.

{drift}
"""
    open(path, 'w', encoding='utf-8').write(txt)
    return path


def main():
    cohorts = s3.available()
    triples, tri2idx, per, genes, ncoh = s2.read_panel(cohorts)   # D-39: canonical, always 99
    V = len(triples)
    train = [c for c in cohorts if SPECS[c]['role'] == 'train']
    L = s3.label_space()
    excl = excluded_pairs()

    print(f"label space: {L['n']} Stage 1b clusters, {len(L['unreliable'])} unreliable (D-23)")
    print(f"vocabulary : {V} triples (canonical, from panel.json) x {len(train)} cohorts")
    print(f"device     : {DEV}" +
          (f" ({torch.cuda.get_device_name(0)})" if DEV.type == 'cuda' else ''))
    print(f"masked-marker loss excludes {len(excl)} (cohort, marker) pairs inherited from D-28")

    if '--ablate-losses' not in sys.argv:
        print("\nnothing to do. run with --ablate-losses for GATE 6.")
        return

    quick = '--quick' in sys.argv
    epochs = 2 if quick else EPOCHS
    q = 'quick_' if quick else ''
    refit = '--refit' in sys.argv
    if quick:
        global N_TRAIN, SCORE_CELLS
        N_TRAIN, SCORE_CELLS = 1_500, 800
        print("\n*** --quick: 2 epochs on a tiny draw. Proves the code path; scores nothing. ***")
    folds = train
    if '--folds' in sys.argv:
        pick = set(sys.argv[sys.argv.index('--folds') + 1].split(','))
        folds = [c for c in train if c in pick]
        print(f"  --folds: holding out only {folds}")

    ARMS = [('proto3', 'proto', True, True), ('proto2', 'proto', False, True),
            ('linear', 'linear', True, True)]
    t0, res = time.time(), []
    for name, head, vic, conf in ARMS:
        print(f"\n  arm {name}: head={head} vicreg={vic}")
        for h in folds:
            res.append(loco_run(f'{q}{name}_{h}', h, train, per, tri2idx, triples, L, excl,
                                head, vic, conf, refit, epochs))
    # check 6 - confidence weighting, UPMC only, because it is the only cohort that has one
    if 'UPMC' in folds:
        print("\n  check 6: confidence weighting OFF, UPMC fold (1-of-5 coverage)")
        res.append(loco_run(f'{q}noconf_UPMC', 'UPMC', train, per, tri2idx, triples, L, excl,
                            'proto', True, False, refit, epochs))

    torch.save([{k: v for k, v in r.items() if k != 'state'} for r in res],
               os.path.join(CKPT, f's6_{q}sweep.pt'))
    d, checks, verdict, ship, ship_name, ship_f1, ml, m2, m3 = assemble(res, L)
    print(f"\n--- GATE 6 ---\n{pd.DataFrame(checks).to_string(index=False)}")
    if quick:
        print("\n--quick: these numbers score nothing. No report written.")
        return
    figs = figures(ship, L)
    p = write_report(os.path.join(REPORTS, 's6_train.md'), d, checks, verdict, ship, ship_name,
                     ship_f1, ml, m2, m3, L, figs, (time.time() - t0) / 60)
    print(f"\n{verdict} - ships {ship_name} - wrote {p}")


if __name__ == "__main__":
    main()

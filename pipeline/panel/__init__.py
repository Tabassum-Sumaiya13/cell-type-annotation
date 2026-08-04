"""
Global marker dictionary.

One place decides what a protein is called, for every dataset that will ever be added.
The knowledge lives in `markers.csv` (data a biologist can read), not in Python.

Naming scheme (decided 2026-08-04): the canonical name is the **HGNC gene symbol**.
Where a gene symbol cannot describe the antibody, a documented pseudo-name is used instead
and `gene_symbol` is left empty:

  KRT_PAN     pan-cytokeratin - a mixture of keratins, not one gene
  HLA_ABC     MHC class I - covers HLA-A, HLA-B and HLA-C
  CEACAM5_6   HubMap 'CD66' - the antibody does not separate CEACAM5 from CEACAM6
  H3_K9ac     a histone modification, not a gene product
  H3_K27me3   a histone modification, not a gene product
  PTPRC_RA    PTPRC gene, but the RA isoform antibody (naive)
  PTPRC_RO    PTPRC gene, but the RO isoform antibody (memory)
  RPS6_p      phosphorylated RPS6 - a signalling state
  STAT3_p     phosphorylated STAT3 - a signalling state

Rule: a real HGNC symbol is written exactly as HGNC writes it (HLA-DRA keeps its hyphen).
A pseudo-name always uses an underscore. So you can tell them apart by eye.
"""
import os, re
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MARKERS_CSV    = os.path.join(HERE, "markers.csv")
NEVER_MERGE_CSV = os.path.join(HERE, "never_merge.csv")


def normalise(name):
    """'PD-L1' -> 'pdl1', 'Beta catenin' -> 'betacatenin'.

    Strips case, spaces and punctuation only. This is the *safe* part of name matching:
    it never guesses that two different words mean the same protein - that is what the
    synonym column in markers.csv is for.
    """
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def load_dictionary():
    """Return (table, lookup) where lookup maps a normalised name -> that row.

    The canonical name, the display name and every listed synonym are all valid keys.
    """
    t = pd.read_csv(MARKERS_CSV, keep_default_na=False)
    lookup = {}
    for r in t.itertuples(index=False):
        keys = [r.canonical, r.display] + [s for s in str(r.synonyms).split('|') if s]
        for k in keys:
            nk = normalise(k)
            prev = lookup.get(nk)
            if prev is not None and prev.canonical != r.canonical:
                raise SystemExit(
                    f"markers.csv is broken: the name '{k}' is claimed by both "
                    f"'{prev.canonical}' and '{r.canonical}'. One antibody name cannot mean "
                    f"two different markers - fix the synonyms column.")
            lookup[nk] = r
    return t, lookup


def load_never_merge():
    """Pairs that must stay separate. Returns a list of (a, b, reason)."""
    t = pd.read_csv(NEVER_MERGE_CSV, keep_default_na=False)
    return [(r.a, r.b, r.reason) for r in t.itertuples(index=False)]


def resolve(antibody, lookup):
    """Antibody name as written in a raw file -> its dictionary row, or None if unknown."""
    return lookup.get(normalise(antibody))

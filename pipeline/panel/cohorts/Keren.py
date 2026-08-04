"""Keren - MIBI-TOF, triple negative breast cancer. Nothing here knows about other cohorts."""

NAME = 'Keren'

# Column names exactly as they appear in Datasets/Keren/cell_expression.csv
COLUMNS = [
    'C', 'Na', 'Si', 'P', 'Ca', 'Fe', 'dsDNA', 'Vimentin', 'SMA', 'Background', 'B7H3', 'FoxP3',
    'Lag3', 'CD4', 'CD16', 'CD56', 'OX40', 'PD1', 'CD31', 'PD-L1', 'EGFR', 'Ki67', 'CD209',
    'CD11c', 'CD138', 'CD163', 'CD68', 'CSF-1R', 'CD8', 'CD3', 'IDO', 'Keratin17', 'CD63',
    'CD45RO', 'CD20', 'p53', 'Beta catenin', 'HLA-DR', 'CD11b', 'CD45', 'H3K9ac', 'Pan-Keratin',
    'H3K27me3', 'phospho-S6', 'MPO', 'Keratin6', 'HLA_Class_1', 'Ta', 'Au',
]

# Channels measured in THIS cohort that cannot be trusted. Found in the Step 2 value audit.
# Keyed by the antibody name as written above.
FLAGS = {
    'C':     'dead channel - every value is exactly 0',
    'CD56':  'near-constant: median == p99, only a few positive cells',
    'CD163': 'near-constant: median == p99, only a few positive cells',
    'OX40':  'near-constant: median == p99, only a few positive cells',
}


def parse(col):
    """Raw column -> (antibody, paper description, cycle, channel). Keren has no extra syntax."""
    return col, '', None, None

"""UPMC - CODEX, head & neck cancer. Knows only about itself."""

NAME = 'UPMC'

# Column names exactly as they appear in
# Datasets/UPMC/dataset_info/labeled_arcsinh_norm_data.parquet (also dataset_info/marker_names.csv)
COLUMNS = [
    'CD117', 'CD11b', 'CD11c', 'CD134', 'CD14', 'CD15', 'CD152', 'CD16', 'CD20', 'CD21', 'CD31',
    'CD34', 'CD38', 'CD3e', 'CD4', 'CD45', 'CD45RA', 'CD45RO', 'CD47', 'CD49f', 'CD56', 'CD57',
    'CD68', 'CD69', 'CD8', 'CollagenIV', 'FoxP3', 'GranzymeB', 'HLA-DR', 'ICOS', 'Ki67', 'PD1',
    'PDL1', 'PanCK', 'Podoplanin', 'TMEM16A', 'Vimentin', 'aSMA', 'p16',
]

FLAGS = {}


def parse(col):
    return col, '', None, None

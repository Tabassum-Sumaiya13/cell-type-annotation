"""HubMap - CODEX, healthy human intestine. Knows only about itself."""

NAME = 'HubMap'

# Column names exactly as they appear in Datasets/HubMap/cell_expression.parquet
COLUMNS = [
    'MUC2', 'SOX9', 'MUC1', 'CD31', 'Synapto', 'CD49f', 'CD15', 'CHGA', 'CDX2', 'ITLN1', 'CD4',
    'CD127', 'Vimentin', 'HLADR', 'CD8', 'CD11c', 'CD44', 'CD16', 'BCL2', 'CD3', 'CD123', 'CD38',
    'CD90', 'aSMA', 'CD21', 'NKG2D', 'CD66', 'CD57', 'CD206', 'CD68', 'CD34', 'aDef5', 'CD7',
    'CD36', 'CD138', 'CD45RO', 'Cytokeratin', 'CD117', 'CD19', 'Podoplanin', 'CD45', 'CD56',
    'CD69', 'Ki67', 'CD49a', 'CD163', 'CD161', 'OLFM4', 'FAP', 'CD25', 'CollIV', 'CK7', 'MUC6',
]

# The dataset README lists channels that were captured but NOT used for their clustering.
# They are mostly empty, so they must not enter the model.
FLAGS = {
    'OLFM4':  'captured but NOT used for clustering (README); mostly NaN',
    'FAP':    'captured but NOT used for clustering (README); mostly NaN',
    'CD25':   'captured but NOT used for clustering (README); mostly NaN',
    'CollIV': 'captured but NOT used for clustering (README); mostly NaN',
    'CK7':    'captured but NOT used for clustering (README); mostly NaN',
    'MUC6':   'captured but NOT used for clustering (README); B009-B012 only',
}


def parse(col):
    return col, '', None, None

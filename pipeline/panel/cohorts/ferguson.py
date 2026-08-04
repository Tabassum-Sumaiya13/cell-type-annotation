"""ferguson - IMC, head & neck cutaneous squamous cell carcinoma. Knows only about itself."""

NAME = 'ferguson'

# Column names exactly as they appear in
# Datasets/ferguson/csv_export/ferguson_cells_counts.csv (assay order, from marker_panel.csv)
COLUMNS = [
    'panCK', 'CD20', 'HH3', 'CD45RA', 'CD8a', 'podoplanin', 'CD16', 'CADM1', 'IDO', 'PDL1',
    'CD13', 'CD68', 'VISTA', 'CD31', 'CXCR3', 'pSTAT3', 'CCR7', 'CD14', 'FX111A', 'FoxP3',
    'PD1', 'CD45RO', 'OX40', 'NFKBp65', 'CD66a', 'Ki67', 'LAG3', 'CD3', 'granzB', 'PDL2',
    'CD4', 'HLADR', 'ICOS', 'TIM3', 'DNA1', 'DNA2',
]

FLAGS = {
    'CXCR3': 'median 29.25 = 45x the next marker - possible channel bleed',
}


def parse(col):
    return col, '', None, None

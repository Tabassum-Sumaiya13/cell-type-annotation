"""
Shared config + loaders for the harmonisation pipeline.

Central registry of the 5 cohorts: file paths, pixel size, and the columns that hold
image id / coordinates / patient id / cell size. Every downstream step imports from here so
the cohort-specific mess lives in exactly one place.
"""
import os, pandas as pd, numpy as np

ROOT      = r"d:\Desktop\FYDP\FYDP final works\cell type annotation"
DATASETS  = os.path.join(ROOT, "Datasets")
OUT       = os.path.join(ROOT, "harmonised")
AUDIT     = os.path.join(OUT, "_audit")
os.makedirs(OUT, exist_ok=True); os.makedirs(AUDIT, exist_ok=True)

# micrometres per pixel  (see DECISION_REGISTER V3/V4; HubMap adopted 0.377, medium-high)
PIXEL_UM = {'CRC':0.3774, 'HubMap':0.3774, 'Keren':0.3906, 'UPMC':0.3774, 'ferguson':1.0}

COHORTS = ['CRC', 'HubMap', 'Keren', 'UPMC', 'ferguson']


def load_geometry(cohort):
    """Return a standard dataframe:
       cell_id (0..N-1 within cohort), image_id, patient_id, x_px, y_px, area_px2 (NaN if none)
    Coordinates are still in pixels here; step 3 converts to um.
    """
    D = DATASETS
    if cohort == 'CRC':
        df = pd.read_csv(os.path.join(D, "CRC", "CRC_clusters_neighborhoods_markers.csv"),
                         usecols=['File Name', 'patients', 'X:X', 'Y:Y', 'size:size', 'Z:Z'])
        out = pd.DataFrame({
            'image_id':   df['File Name'].astype(str),
            'patient_id': 'CRC_p' + df['patients'].astype(str),
            'x_px': df['X:X'].astype('float64'),
            'y_px': df['Y:Y'].astype('float64'),
            # size:size is a 3D voxel count (Z 2..16) -> NOT a 2D area. Store 2D estimate = size/Z.
            'area_px2': (df['size:size'] / df['Z:Z']).astype('float64'),
        })

    elif cohort == 'HubMap':
        df = pd.read_parquet(os.path.join(D, "HubMap", "cell_locations.parquet"),
                             columns=['unique_region', 'x', 'y'])
        out = pd.DataFrame({
            'image_id':   df['unique_region'].astype(str),
            'patient_id': 'HM_' + df['unique_region'].str.split('_').str[0],   # donor
            'x_px': df['x'].astype('float64'),
            'y_px': df['y'].astype('float64'),
            'area_px2': np.nan,   # not in the parquet
        })

    elif cohort == 'Keren':
        loc = pd.read_csv(os.path.join(D, "Keren", "cell_locations.csv"))          # 197,678 labelled cells
        meta = pd.read_csv(os.path.join(D, "Keren", "sample_metadata.csv"))        # SampleID -> patient_id
        size = pd.read_csv(os.path.join(D, "Keren", "cellData.csv"),
                           usecols=['SampleID', 'cellLabelInImage', 'cellSize'])
        loc = loc.merge(size, on=['SampleID', 'cellLabelInImage'], how='left')
        loc = loc.merge(meta[['SampleID', 'patient_id']], on='SampleID', how='left')
        out = pd.DataFrame({
            'image_id':   'Keren_s' + loc['SampleID'].astype(str),
            'patient_id': 'Keren_p' + loc['patient_id'].astype('Int64').astype(str),
            'x_px': loc['X'].astype('float64'),
            'y_px': loc['Y'].astype('float64'),
            'area_px2': loc['cellSize'].astype('float64'),
        })

    elif cohort == 'UPMC':
        loc = pd.read_csv(os.path.join(D, "UPMC", "dataset_info", "cell_locations_and_labels.csv"),
                          usecols=['ACQUISITION_ID', 'X', 'Y', 'SIZE'])
        meta = pd.read_csv(os.path.join(D, "UPMC", "dataset_info", "sample_metadata.csv"),
                           usecols=['acquisition_id', 'patient_id'])
        loc = loc.merge(meta, left_on='ACQUISITION_ID', right_on='acquisition_id', how='left')
        out = pd.DataFrame({
            'image_id':   loc['ACQUISITION_ID'].astype(str),
            'patient_id': 'UPMC_p' + loc['patient_id'].astype('Int64').astype(str),
            'x_px': loc['X'].astype('float64'),
            'y_px': loc['Y'].astype('float64'),
            'area_px2': loc['SIZE'].astype('float64'),
        })

    elif cohort == 'ferguson':
        loc = pd.read_csv(os.path.join(D, "ferguson", "cell_locations.csv"))
        meta = pd.read_csv(os.path.join(D, "ferguson", "sample_metadata.csv"),
                           usecols=['acquisition_id', 'patient_id'])
        loc = loc.merge(meta, on='acquisition_id', how='left')
        out = pd.DataFrame({
            'image_id':   loc['acquisition_id'].astype(str),
            'patient_id': 'ferg_p' + loc['patient_id'].astype('Int64').astype(str),
            'x_px': loc['X'].astype('float64'),
            'y_px': loc['Y'].astype('float64'),
            'area_px2': np.nan,
        })
    else:
        raise ValueError(cohort)

    out.insert(0, 'cell_id', np.arange(len(out), dtype='int64'))
    out.insert(1, 'cohort', cohort)
    return out


def _marker_rename(cohort):
    """{raw_column -> canonical} for the USABLE phenotypic markers of a cohort (from Step 1)."""
    mm = pd.read_csv(os.path.join(AUDIT, "marker_map.csv"))
    mm = mm[(mm.cohort == cohort) & (mm.use == True)]
    return dict(zip(mm.raw_column, mm.canonical))


def load_expression(cohort):
    """Raw marker matrix aligned 1:1 with load_geometry(cohort) row order, so cell_id matches
    the cells/graph files. Columns = canonical marker names. Values still in native scale.
    Alignment is by natural key (never by blind position) for cohorts whose expression lives
    in a separate file; asserted non-null so a mismatch fails loudly."""
    D = DATASETS
    ren = _marker_rename(cohort)

    if cohort == 'CRC':                       # single file -> same row order as geometry
        cols = list(ren) + ['File Name']
        df = pd.read_csv(os.path.join(D, "CRC", "CRC_clusters_neighborhoods_markers.csv"), usecols=cols)
        X = df[list(ren)].rename(columns=ren)

    elif cohort == 'HubMap':                  # join on native cell_id
        base = pd.read_parquet(os.path.join(D, "HubMap", "cell_locations.parquet"), columns=['cell_id'])
        ex = pd.read_parquet(os.path.join(D, "HubMap", "cell_expression.parquet"),
                             columns=['cell_id'] + list(ren))
        ex = base.merge(ex, on='cell_id', how='left')
        assert ex[list(ren)].notna().all(axis=1).all(), "HubMap expr join left NaNs"
        X = ex[list(ren)].rename(columns=ren)

    elif cohort == 'Keren':                   # join on (SampleID, cellLabelInImage)
        loc = pd.read_csv(os.path.join(D, "Keren", "cell_locations.csv"),
                          usecols=['SampleID', 'cellLabelInImage'])
        ex = pd.read_csv(os.path.join(D, "Keren", "cell_expression.csv"),
                         usecols=['SampleID', 'cellLabelInImage'] + list(ren))
        ex = loc.merge(ex, on=['SampleID', 'cellLabelInImage'], how='left')
        assert ex[list(ren)].notna().all(axis=1).all(), "Keren expr join left NaNs"
        X = ex[list(ren)].rename(columns=ren)

    elif cohort == 'UPMC':                     # join on (acquisition, cell_id)
        loc = pd.read_csv(os.path.join(D, "UPMC", "dataset_info", "cell_locations_and_labels.csv"),
                          usecols=['ACQUISITION_ID', 'CELL_ID'])
        ex = pd.read_parquet(os.path.join(D, "UPMC", "dataset_info", "labeled_arcsinh_norm_data.parquet"),
                             columns=['sample_id', 'cell_id'] + list(ren))
        ex = loc.merge(ex, left_on=['ACQUISITION_ID', 'CELL_ID'],
                       right_on=['sample_id', 'cell_id'], how='left')
        assert ex[list(ren)].notna().all(axis=1).all(), "UPMC expr join left NaNs"
        X = ex[list(ren)].rename(columns=ren)

    elif cohort == 'ferguson':                 # join on (acquisition_id, cell_id)
        loc = pd.read_csv(os.path.join(D, "ferguson", "cell_locations.csv"),
                          usecols=['acquisition_id', 'cell_id'])
        ex = pd.read_csv(os.path.join(D, "ferguson", "cell_expression.csv"),
                         usecols=['acquisition_id', 'cell_id'] + list(ren))
        ex = loc.merge(ex, on=['acquisition_id', 'cell_id'], how='left')
        assert ex[list(ren)].notna().all(axis=1).all(), "ferguson expr join left NaNs"
        X = ex[list(ren)].rename(columns=ren)
    else:
        raise ValueError(cohort)

    X = X.astype('float32')
    X.insert(0, 'cell_id', np.arange(len(X), dtype='int64'))
    return X


def load_model(cohort, union=True):
    """Load the Step-7 model table and (if union=True) reindex the own-marker `x_*` block to
    the fixed 102-marker UNION order, adding a `mask_<marker>` (1 measured / 0 absent) for each.
    Absent markers become NaN + mask 0 (never 0-value). Returns the full DataFrame."""
    import json
    MODEL = os.path.join(OUT, "model")
    df = pd.read_parquet(os.path.join(MODEL, f"{cohort}_model.parquet"))
    if not union:
        return df
    lay = json.load(open(os.path.join(MODEL, "feature_columns.json")))
    UNION = lay["union_markers"]
    have = set(lay["per_cohort_markers"][cohort])          # explicit; never prefix-scan (x_um is a coordinate!)
    add = {}
    for m in UNION:
        if ('x_' + m) not in df.columns:
            add['x_' + m] = np.full(len(df), np.nan, 'float32')
        add['mask_' + m] = np.full(len(df), 1.0 if m in have else 0.0, 'float32')
    return pd.concat([df, pd.DataFrame(add, index=df.index)], axis=1)

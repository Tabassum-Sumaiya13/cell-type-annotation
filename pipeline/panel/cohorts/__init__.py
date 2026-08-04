"""
Per-cohort panel cleaners. One file per dataset. No file imports another.

To add a 6th dataset:
  1. copy any file here, rename it to the new cohort name
  2. fill in NAME, COLUMNS (raw column names, exactly as written in its file), FLAGS
  3. add the name to ORDER below
  4. run Step 1 - it stops and tells you if any antibody name is not in ../markers.csv

Nothing else in the pipeline needs editing.
"""
import importlib

# Order is fixed so report tables and panel_matrix.csv column order stay comparable
# between runs. Adding a new cohort at the END keeps old diffs readable.
ORDER = ['Keren', 'ferguson', 'UPMC', 'HubMap', 'CRC']


def load(name):
    return importlib.import_module(f"{__name__}.{name}")


def load_all():
    """Return [module, ...] in ORDER, checking each one declares what it must."""
    mods = []
    for n in ORDER:
        m = load(n)
        for attr in ('NAME', 'COLUMNS', 'FLAGS', 'parse'):
            if not hasattr(m, attr):
                raise SystemExit(f"cohort file '{n}.py' is missing '{attr}'")
        if m.NAME != n:
            raise SystemExit(f"cohort file '{n}.py' says NAME='{m.NAME}' - they must match")
        if len(set(m.COLUMNS)) != len(m.COLUMNS):
            dup = sorted({c for c in m.COLUMNS if m.COLUMNS.count(c) > 1})
            raise SystemExit(f"cohort '{n}' lists the same column twice: {dup}")
        mods.append(m)
    return mods

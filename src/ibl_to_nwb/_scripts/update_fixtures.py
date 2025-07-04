# This does not run on popeye

# download bwm units table
from pathlib import Path

import pandas as pd
from brainwidemap import bwm_query, download_aggregate_tables
from one.api import ONE

one = ONE()

# saving bwm_units_df.pqt
# bwm_units_df = bwm_units(one, min_qc=0)
bwm_units_df = pd.read_parquet(download_aggregate_tables(one=one))
outpath = Path(__file__).parent.parent / "fixtures" / "bwm_units_df.pqt"
outpath.parent.mkdir(parents=True, exist_ok=True)
bwm_units_df.to_parquet(outpath)
print(bwm_units_df.shape[0])

# saving bwm_df
# TODO proper freeze, also return_details and freeze together doesn't work
bwm_df = bwm_query(freeze="2023_12_bwm_release", one=one, return_details=True)
outpath = Path(__file__).parent.parent / "fixtures" / "bwm_df.pqt"
outpath.parent.mkdir(parents=True, exist_ok=True)
bwm_df.to_parquet(outpath)

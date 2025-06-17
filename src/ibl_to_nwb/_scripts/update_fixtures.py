# This does not run on popeye

# download bwm units table 
from one.api import ONE
from brainwidemap import bwm_units, bwm_query
from pathlib import Path

one = ONE()

# saving bwm_units_df.pqt
bwm_units_df = bwm_units(one)
outpath = Path(__file__).parent.parent / 'fixtures' / 'bwm_units_df.pqt'
outpath.parent.mkdir(parents=True, exist_ok=True)
bwm_units_df.to_parquet(outpath)

# saving bwm_df
# TODO proper freeze, also return_details and freeze together doesn't work
bwm_df = bwm_query(freeze="2023_12_bwm_release", one=one, return_details=True)
outpath = Path(__file__).parent.parent / 'fixtures' / 'bwm_df.pqt'
outpath.parent.mkdir(parents=True, exist_ok=True)
bwm_df.to_parquet(outpath)
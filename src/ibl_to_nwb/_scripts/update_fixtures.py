# download bwm units table 
from one.api import ONE
from brainwidemap import bwm_units
from pathlib import Path
one = ONE()
bwm_units_df = bwm_units(one)

outpath = Path(__file__).parent.parent / 'fixtures' / 'bwm_units_df.pqt'
outpath.parent.mkdir(parents=True, exist_ok=True)
bwm_units_df.to_parquet(outpath)

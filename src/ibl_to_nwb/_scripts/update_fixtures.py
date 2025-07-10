# This does not run on popeye

# download bwm units table
from pathlib import Path
import pandas as pd
from brainwidemap import bwm_query, download_aggregate_tables
from one.api import ONE
import json
from tqdm import tqdm

one = ONE()

# saving bwm_units_df.pqt
# bwm_units_df = bwm_units(one, min_qc=0)
print("bwm units table")
bwm_units_df = pd.read_parquet(download_aggregate_tables(one=one))
outpath = Path(__file__).parent.parent / "fixtures" / "bwm_units_df.pqt"
outpath.parent.mkdir(parents=True, exist_ok=True)
print(f"saving {outpath}")
bwm_units_df.to_parquet(outpath)

# saving bwm_df
# TODO proper freeze, also return_details and freeze together doesn't work
print("bwm sessions table")
bwm_df = bwm_query(freeze="2023_12_bwm_release", one=one, return_details=True)
outpath = Path(__file__).parent.parent / "fixtures" / "bwm_df.pqt"
outpath.parent.mkdir(parents=True, exist_ok=True)
print(f"saving {outpath}")
bwm_df.to_parquet(outpath)

# saving the entire qc from alyx
print("getting qc")
bwm_qc = {}
for eid in tqdm(bwm_df["eid"].unique()):
    bwm_qc[eid] = one.alyx.rest("sessions", "read", eid)["extended_qc"]
outpath = Path(__file__).parent.parent / "fixtures" / "bwm_qc.json"

print(f"saving {outpath}")
with open(outpath, "w") as json_file:
    json.dump(bwm_qc, json_file)

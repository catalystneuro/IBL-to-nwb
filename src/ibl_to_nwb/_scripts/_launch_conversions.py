# %%
import os
import sys
from pathlib import Path

import joblib
import numpy as np
from iblutil.util import setup_logger

# if running on SDSC, use the OneSdsc, else normal
if "USE_SDSC_ONE" in os.environ:
    print("using SDSC ONE")
    from deploy.iblsdsc import OneSdsc as ONE
else:
    print("using regular ONE")
    from one.api import ONE

from ibl_to_nwb import bwm_to_nwb
from ibl_to_nwb.fixtures import load_fixtures

_logger = setup_logger('bwm_to_nwb')

REVISION = "2025-05-06"
N_BATCHES = 10
if len(sys.argv) == 2:
    i_batch = int(sys.argv[1])
else:
    i_batch = 0

base_path = Path("/mnt/sdceph/users/ibl/data/quarantine/BWM_to_NWB/")
base_path.mkdir(exist_ok=True, parents=True)

bwm_df = load_fixtures.load_bwm_df()
eids = bwm_df["eid"].unique()

n_sessions = eids.shape[0]
eids_batches = np.array_split(eids, 10)
batch = eids_batches[i_batch]

# common
one_kwargs = dict(
    mode="local",
    cache_rest = None, # disables rest caching (write permission errors on popeye)
)

# instantiate one
one = ONE(**one_kwargs)


# %%
# mode = "raw"
# mode = "debug"
mode = "processed"

# %% the full thing
N_JOBS = len(batch)
N_JOBS = 1
eid = "0f25376f-2b78-4ddc-8c39-b6cdbe7bf5b9"
if N_JOBS == 1:
    eid = batch[0]
    bwm_to_nwb.convert_session(eid=eid, one=one, revision=REVISION, mode=mode, cleanup=False, base_path=base_path, verify=True)
else:
    jobs = (
        joblib.delayed(bwm_to_nwb.convert_session)(
            eid=eid, one=one, revision=REVISION, mode=mode, cleanup=True, base_path=base_path, verify=True
        ) for eid in batch
    )
    joblib.Parallel(n_jobs=N_JOBS)(jobs)

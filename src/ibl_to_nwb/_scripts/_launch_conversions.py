import os
from pathlib import Path
import joblib

# if running on SDSC, use the OneSdsc, else normal
if "USE_SDSC_ONE" in os.environ:
    print("using SDSC ONE")
    from deploy.iblsdsc import OneSdsc as ONE
else:
    print("using regular ONE")
    from one.api import ONE

from ibl_to_nwb import bwm_to_nwb
from brainwidemap.bwm_loading import bwm_query

REVISION = '2025-05-06'
N_JOBS = 1
output_folder = Path.home() / "ibl_scratch" / "nwbfiles"
base_path = Path.home() / "ibl_scratch" # FIXME or pass me down to setup_paths()

# eid needs to be defined before instantiation of ONE for local compatiblity.
eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"

# common
one_kwargs = dict(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    mode="remote",
)

# if not running on SDSC adding the cache folder explicitly
if "USE_SDSC_ONE" in os.environ:
    one_kwargs["cache_rest"] = None  # disables rest caching (write permission errors on popeye)
else:
    # Initialize IBL (ONE) client to download processed data for this session
    one_kwargs["cache_dir"] = base_path / "ibl_conversion" / eid / "cache" # base_path / "ibl_conversion" / eid / "cache"

# instantiate one
one = ONE(**one_kwargs)

# bwm_df = bwm_query(freeze='2023_12_bwm_release', one=one, return_details=True)
# eids = bwm_df['eid'].unique().tolist()
mode = "raw"

# if N_JOBS <= 1:

bwm_to_nwb.convert_session(eid=eid, one=one, revision=REVISION, mode=mode, cleanup=True)
# else:
#     jobs = (joblib.delayed(bwm_to_nwb.convert_session)(eid=eid, one=one, revision=REVISION, cleanup=True) for eid in eids)
#     joblib.Parallel(n_jobs=N_JOBS)(jobs)
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

# TODO logging and joblib
import logging
_logger = logging.getLogger('ibl_to_nwb')
_logger.setLevel(logging.INFO)
ch = logging.StreamHandler()  # Create a console handler
ch.setLevel(logging.DEBUG)  # Set the level for the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
_logger.addHandler(ch)

from ibl_to_nwb.fixtures import load_fixtures
from ibl_to_nwb import bwm_to_nwb

REVISION = '2025-05-06'
N_JOBS = 1

base_path = Path.home() / "ibl_bwm_to_nwb"
base_path = Path.home() / "ibl_scratch"
base_path.mkdir(exist_ok=True)

bwm_df = load_fixtures.load_bwm_df()
eids = bwm_df['eid']
# for eid in eids:

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

mode = "raw"
mode = "debug"
# if N_JOBS <= 1:

bwm_to_nwb.convert_session(eid=eid, one=one, revision=REVISION, mode=mode, cleanup=True, base_path=base_path)
# else:
#     jobs = (joblib.delayed(bwm_to_nwb.convert_session)(eid=eid, one=one, revision=REVISION, cleanup=True) for eid in eids)
#     joblib.Parallel(n_jobs=N_JOBS)(jobs)
# %%
import os
from pathlib import Path

from pynwb import NWBHDF5IO

from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency

# if running on SDSC, use the OneSdsc, else normal
if "USE_SDSC_ONE" in os.environ:
    print("using SDSC ONE")
    from deploy.iblsdsc import OneSdsc as ONE
else:
    print("using regular ONE")
    from one.api import ONE

import warnings

warnings.filterwarnings("once", category=UserWarning, module="ONE")

# base path setup
if "USE_SDSC_ONE" in os.environ:
    base_path = Path("/mnt/sdceph/users/ibl/data/quarantine/BWM_to_NWB/")
else:
    base_path = Path.home() / "ibl_scratch"  # local directory
base_path.mkdir(exist_ok=True, parents=True)

# right now, enforcing the use of SDSC one
# from deploy.iblsdsc import OneSdsc as ONE

nwbfile_path = Path(
    # "/home/georg/ibl_scratch/nwbfiles/sub-ibl_witten_26/sub-ibl_witten_26_ses-09394481-8dd2-4d5c-9327-f2753ede92d7_desc-processed_behavior+ecephys.nwb"
    "/home/georg/ibl_scratch/nwbfiles/sub-NYU-11/sub-NYU-11_ses-6713a4a7-faed-4df2-acab-ee4e63326f8d_desc-raw_ecephys+image.nwb"
)

with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
    nwbfile = io.read()
    eid = nwbfile.session_id

# %%
# instantiating one
if "USE_SDSC_ONE" in os.environ:
    one_kwargs = dict(
        mode="local",  # required for SDSC use
        cache_rest=None,  # at SDSC, no write permissions at the location of the rest cache
    )
else:
    one_kwargs = dict(
        base_url="https://openalyx.internationalbrainlab.org",
        mode="local",
    )

# %%
# if RESET_CACHE:
#     one = ONE(base_url="https://openalyx.internationalbrainlab.org")
#     one._remove_table_files()
#     one.load_cache()
#     del one

# instantiate one
one = ONE(**one_kwargs)

check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
print("all checks passed")

# %%

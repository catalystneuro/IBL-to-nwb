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

# right now, enforcing the use of SDSC one
# from deploy.iblsdsc import OneSdsc as ONE

nwbfile_path = Path(
    "/home/georg/ibl_scratch/nwbfiles/sub-ibl_witten_26/sub-ibl_witten_26_ses-09394481-8dd2-4d5c-9327-f2753ede92d7_desc-processed_behavior+ecephys.nwb"
)

with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
    nwbfile = io.read()
    eid = nwbfile.session_id


# %%
# path setup
base_path = Path.home() / "ibl_scratch"
output_folder = base_path / "nwbfiles"
output_folder.mkdir(exist_ok=True, parents=True)

# common
one_kwargs = dict(
    mode="local",
)

# if not running on SDSC adding the cache folder explicitly
if "USE_SDSC_ONE" in os.environ:
    one_kwargs["cache_rest"] = None  # disables rest caching (write permission errors on popeye)
else:
    # Initialize IBL (ONE) client to download processed data for this session
    one_cache_folder_path = base_path / "ibl_conversion" / eid / "cache"
    one_kwargs["cache_dir"] = one_cache_folder_path

# instantiate one
one = ONE(**one_kwargs)

check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
print("all checks passed")

# %%

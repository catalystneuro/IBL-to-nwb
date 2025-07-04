# %%
import os
from pathlib import Path

from pynwb import NWBHDF5IO

from ibl_to_nwb import bwm_to_nwb
from ibl_to_nwb.testing import check_nwbfile_for_consistency

# Set the filter to show each warning only once for a specific module

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

REVISION = "2025-05-06"
CONVERT = True
VERIFY = False
RESET_CACHE = False

# eid = "d832d9f7-c96a-4f63-8921-516ba4a7b61f" # no camera issue
# eid = "b81e3e11-9a60-4114-b894-09f85074d9c3" # cluster__uuid / eid issue
# eid = "4b7fbad4-f6de-43b4-9b15-c7c7ef44db4b" # duplicate camera interface
eid = "a8a8af78-16de-4841-ab07-fde4b5281a03"

# instantiating one
if "USE_SDSC_ONE" in os.environ:
    one_kwargs = dict(
        mode="local",  # required for SDSC use
        cache_rest=None,  # at SDSC, no write permissions at the location of the rest cache
    )
else:
    one_kwargs = dict(
        # base_url="https://openalyx.internationalbrainlab.org",
        base_url="https://alyx.internationalbrainlab.org",
        mode="local",
    )

# %%
if RESET_CACHE:
    # one = ONE(base_url="https://openalyx.internationalbrainlab.org")
    one = ONE(base_url="https://alyx.internationalbrainlab.org")
    # remove cache tables if present
    one._remove_table_files()
    one.load_cache()
    del one

# instantiate one
one = ONE(**one_kwargs)

# %% mode selection
# mode = "raw"
mode = "processed"

# %% the full thing
kwargs = dict(
    one=one,
    revision=REVISION,
    mode=mode,
    base_path=base_path,
    cleanup=False,
    log_to_file=False,
    verify=False,
    debug=True,
    overwrite=True,
)


def eid2nwbfilename(eid, one, mode="processed"):
    ref = one.eid2ref(eid)
    base_path = Path("/mnt/home/graiser/quarantine/BWM_to_NWB/nwbfiles")
    match mode:
        case "processed":
            suffix = "processed_behavior+ecephys"
    nwbfile_path = base_path / f"sub-{ref['subject']}" / f"sub-{ref['subject']}_ses-{eid}_desc-{suffix}.nwb"
    return nwbfile_path


if CONVERT:
    bwm_to_nwb.convert_session(eid=eid, **kwargs)

if VERIFY:
    nwbfile_path = eid2nwbfilename(eid, one, mode="processed")

    with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
        check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)

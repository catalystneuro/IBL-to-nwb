# %%
import os
import shutil
from pathlib import Path

import joblib

from ibl_to_nwb import bwm_to_nwb
from ibl_to_nwb.fixtures import load_fixtures

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
N_JOBS = 12
DEBUG = True
USE_JOBLIB = False

if DEBUG:
    # eid = "09394481-8dd2-4d5c-9327-f2753ede92d7"  # the spike timestamps issue for Heberto
    eid = "6713a4a7-faed-4df2-acab-ee4e63326f8d"  # the LF timestamps issue
    # eid = "d32876dd-8303-4720-8e7e-20678dc2fd71"  # no spikes['clusters'] ????
    N_JOBS = 1
    # crashes locally
else:
    # if not debugging
    # 3 folders: jobs are taken from a pile of eids in eids_todo
    # moved to eids_running when launched
    # and from there to eids_done when finished without error
    todo_dir = base_path / "eids_todo"
    running_dir = base_path / "eids_running"
    done_dir = base_path / "eids_done"
    for folder in [running_dir, done_dir]:
        folder.mkdir(exist_ok=True)

    # if not exists, create the folder with filenames == eids
    # from this todo_dir, move to running_dir when launched
    # there, when finished, will move to done_dir
    if not todo_dir.exists():
        todo_dir.mkdir(exist_ok=True)
        bwm_df = load_fixtures.load_bwm_df()

        for eid in bwm_df["eid"].values:
            (todo_dir / f"{eid}").touch()

    # subsetting to N jobs from the todo pile
    eids = [fpath.name for fpath in list(todo_dir.glob("*"))]
    if len(eids) < N_JOBS:
        N_JOBS = len(eids)
    eids_ = eids[:N_JOBS]

# instantiating one
if "USE_SDSC_ONE" in os.environ:
    one_kwargs = dict(
        mode="local",  # required for SDSC use
        cache_rest=None,  # at SDSC, no write permissions at the location of the rest cache
    )
else:
    one_kwargs = dict(
        # base_url="https://alyx.internationalbrainlab.org",  # when running the first time, this needs to be uncommented to get the cache tables
        mode="local",  # after the first run, this should be uncommented to be closest to the SDSC environment
        # make sure this path matches to what is set in the download_data.py script for local troubleshooting
        cache_dir=base_path / "ibl_conversion" / eid / "cache",  # base_path / "ibl_conversion" / eid / "cache"
    )


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
    verify=True,
)

if DEBUG:  # this is for debugging single sessions
    if USE_JOBLIB:
        jobs = joblib.delayed(bwm_to_nwb.convert_session_)(eid=eid, **kwargs)
        joblib.Parallel(n_jobs=N_JOBS)(jobs)
    else:
        bwm_to_nwb.convert_session(eid=eid, **kwargs)
else:
    for eid in eids_:
        shutil.move(todo_dir / f"{eid}", running_dir / f"{eid}")
    jobs = (joblib.delayed(bwm_to_nwb.convert_session_)(eid=eid, **kwargs) for eid in eids_)
    joblib.Parallel(n_jobs=N_JOBS)(jobs)

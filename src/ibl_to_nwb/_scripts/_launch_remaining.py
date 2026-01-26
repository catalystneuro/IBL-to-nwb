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

MODE = "raw"
# N_JOBS = 64 # 64 good value for processed
N_JOBS = 4 # for raw
DEBUG = False
USE_JOBLIB = True
RESET_CACHE = True
OVERWRITE = True
VERIFY=True
ALYX = 'openalyx'
REVISION = "2025-05-06"

if DEBUG:
    eid = "dc21e80d-97d7-44ca-a729-a8e3f9b14305" # the broken session
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
if ALYX == 'openalyx':
    one_url = "https://openalyx.internationalbrainlab.org"
    tables_dir = Path.home() / "Downloads" / "ONE" / "openalyx.internationalbrainlab.org"
if ALYX == 'alyx':
    one_url = "https://alyx.internationalbrainlab.org"
    tables_dir = Path.home() / "Downloads" / "ONE" / "alyx.internationalbrainlab.org"

if "USE_SDSC_ONE" in os.environ:
    one_kwargs = dict(
        mode="local",  # required for SDSC use
        cache_rest=None,  # at SDSC, no write permissions at the location of the rest cache
        tables_dir=tables_dir
    )
else:
    one_kwargs = dict(
        base_url=one_url,
        mode="local",
    )


# %%
if RESET_CACHE:
    one = ONE(base_url="https://alyx.internationalbrainlab.org")
    one._remove_table_files()
    one.load_cache()
    del one

# instantiate one
one = ONE(**one_kwargs)

# %% the full thing
kwargs = dict(
    one=one,
    revision=REVISION,
    mode=MODE,
    base_path=base_path,
    cleanup=True,
    log_to_file=True,
    verify=VERIFY,
    debug=DEBUG,
    overwrite=OVERWRITE,
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

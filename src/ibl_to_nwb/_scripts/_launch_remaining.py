# %%
import sys
import numpy as np
import os
from pathlib import Path
import joblib
import shutil

# Set the filter to show each warning only once for a specific module

# if running on SDSC, use the OneSdsc, else normal
if "USE_SDSC_ONE" in os.environ:
    print("using SDSC ONE")
    from deploy.iblsdsc import OneSdsc as ONE
else:
    print("using regular ONE")
    from one.api import ONE

import warnings
warnings.filterwarnings('once', category=UserWarning, module='ONE')

from ibl_to_nwb.fixtures import load_fixtures
from ibl_to_nwb import bwm_to_nwb

from iblutil.util import setup_logger
# _logger = setup_logger('bwm_to_nwb')
# import logging
# _logger = logging.getLogger('bwm_to_nwb')
# _logger.setLevel(logging.DEBUG)

REVISION = "2025-05-06"
N_JOBS = 48
RESET = False

base_path = Path("/mnt/sdceph/users/ibl/data/quarantine/BWM_to_NWB/")
base_path.mkdir(exist_ok=True, parents=True)

todo_dir = base_path / 'eids_todo'
running_dir = base_path / 'eids_running'
done_dir = base_path / 'eids_done'
for folder in [running_dir, done_dir]:
    folder.mkdir(exist_ok=True)

# if not exists, create the folder with filenames == eids
# from this todo_dir, move to running_dir when launched
# there, when finished, will move to done_dir

if not todo_dir.exists():
    todo_dir.mkdir(exist_ok=True)
    bwm_df = load_fixtures.load_bwm_df()

    for eid in bwm_df['eid'].values:
        (todo_dir / f'{eid}').touch()

eids = [fpath.name for fpath in list(todo_dir.glob('*'))]
if len(eids) < N_JOBS:
    N_JOBS = len(eids)
eids_ = eids[:N_JOBS]

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
if N_JOBS == 1:
    eid = eids_[0]
    bwm_to_nwb.convert_session_(eid=eid, one=one, revision=REVISION, mode=mode, cleanup=False, base_path=base_path, verify=True)
else:
    for eid in eids_:
        shutil.move(todo_dir / f'{eid}', running_dir / f'{eid}')
    jobs = (
        joblib.delayed(bwm_to_nwb.convert_session)(
            eid=eid, one=one, revision=REVISION, mode=mode, cleanup=True, base_path=base_path, verify=True
        ) for eid in eids_
    )
    joblib.Parallel(n_jobs=N_JOBS)(jobs)

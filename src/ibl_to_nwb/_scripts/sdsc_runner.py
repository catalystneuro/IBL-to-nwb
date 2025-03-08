import joblib
from pathlib import Path

import ibldandi
from deploy.iblsdsc import OneSdsc as ONE
#from one.api import ONE

from brainwidemap.bwm_loading import bwm_query

REVISION = '2025-05-06'
N_JOBS = 1
output_folder = Path.home() / "ibl_scratch" / "nwbfiles"


one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    mode="remote",
)
bwm_df = bwm_query(freeze='2023_12_bwm_release', one=one, return_details=True)
eids = bwm_df['eid'].unique().tolist()


if N_JOBS <= 1:
    ibldandi.convert_session(eid=eids[0], one=one, revision=REVISION, cleanup=True)
else:
    jobs = (joblib.delayed(ibldandi.convert_session)(eid=eid, one=one, revision=REVISION, cleanup=True) for eid in eids)
    joblib.Parallel(n_jobs=N_JOBS)(jobs)
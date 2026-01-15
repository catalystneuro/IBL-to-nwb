# %%
from pathlib import Path

# only to be used on SDSC
from deploy.iblsdsc import OneSdsc as ONE
from pynwb import NWBHDF5IO

from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency

# instantiate one
one = ONE(cache_rest=None)

# %% gather all present nwbfiles
base_path = Path("/mnt/sdceph/users/ibl/data/quarantine/BWM_to_NWB/nwbfiles")
nwbfiles = list(base_path.rglob('*.nwb'))
print(len(nwbfiles))

# %% compare with bwm_df
from ibl_to_nwb.fixtures import load_fixtures
bwm_df = load_fixtures.load_bwm_df()
print(bwm_df['eid'].unique().shape)

# %% missing eids


# %% iterate over all and check all
for i, nwbfile_path in enumerate(nwbfiles):
    with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
        nwbfile = io.read()
        eid = nwbfile.session_id
        check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
        print(f"{i}/{len(nwbfiles)} - {eid} - {nwbfile_path} - passed")

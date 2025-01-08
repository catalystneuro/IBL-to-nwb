# %%
from pathlib import Path

from one.api import ONE
from pynwb import NWBHDF5IO

from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency

# path setup
nwbfile_path = Path("/home/georg/ibl_scratch/nwbfiles/sub-NR_0031/sub-NR_0031_ses-caa5dddc-9290-4e27-9f5e-575ba3598614_desc-processed-debug.nwb")
nwbfile = NWBHDF5IO.read_nwb(nwbfile_path)

eid, revision = nwbfile.session_id.split(':') # this is the hack that has to be removed eventually

# path setup
base_path = Path.home() / "ibl_scratch"
output_folder = base_path / "nwbfiles"
output_folder.mkdir(exist_ok=True, parents=True)

# %%
# Initialize IBL (ONE) client to download processed data for this session
one_cache_folder_path = base_path / "ibl_conversion" / eid / "cache"
one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    mode="remote",
    cache_dir=one_cache_folder_path,
)

check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
# %%

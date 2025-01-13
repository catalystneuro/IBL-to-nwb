# %%
import sys
from pathlib import Path

from one.api import ONE
from pynwb import NWBHDF5IO

from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency, check_raw_nwbfile_for_consistency

nwbfile_path = sys.argv[1]
if "raw" in nwbfile_path:
    raw = True

nwbfile = NWBHDF5IO.read_nwb(nwbfile_path)

eid, revision = nwbfile.session_id.split(":")  # this is the hack that has to be removed eventually

# path setup
base_path = Path.home() / "ibl_scratch"
output_folder = base_path / "nwbfiles"
output_folder.mkdir(exist_ok=True, parents=True)

# Initialize IBL (ONE) client to download processed data for this session
one_cache_folder_path = base_path / "ibl_conversion" / eid / "cache"
one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    mode="remote",
    cache_dir=one_cache_folder_path,
)

if raw:
    check_raw_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
else:
    check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
# %%

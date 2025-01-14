# %%
import os
from pathlib import Path

# if running on SDSC, use the OneSdsc, else normal
if "USE_SDSC_ONE" in os.environ:
    print("using SDSC ONE")
    from deploy.iblsdsc import OneSdsc as ONE
else:
    print("using regular ONE")
    from one.api import ONE

from pynwb import NWBHDF5IO

from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency, check_raw_nwbfile_for_consistency

# nwbfile_path = sys.argv[1]
nwbfile_path = "/mnt/home/graiser/ibl_scratch/nwbfiles/sub-NR_0031/sub-NR_0031_ses-caa5dddc-9290-4e27-9f5e-575ba3598614_desc-raw_ecephys+image.nwb"
if "raw" in nwbfile_path:
    raw = True

with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
    nwbfile = io.read()
    eid, revision = nwbfile.session_id.split(":")  # this is the hack that has to be removed eventually

# path setup
base_path = Path.home() / "ibl_scratch"
output_folder = base_path / "nwbfiles"
output_folder.mkdir(exist_ok=True, parents=True)
# session_scratch_folder = base_path / eid

# common
one_kwargs = dict(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    mode="remote",
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

if raw:
    check_raw_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
else:
    check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
# %%
print("all checks passed")

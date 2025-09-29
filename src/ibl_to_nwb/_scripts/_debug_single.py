# %%
import os
from pathlib import Path

from pynwb import NWBHDF5IO

from ibl_to_nwb import bwm_to_nwb
from ibl_to_nwb.testing import check_nwbfile_for_consistency
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
CONVERT = True
VERIFY = False
RESET_CACHE = False
ALYX = 'openalyx'
MODE = "raw"

# eid = "6fb1e12c-883b-46d1-a745-473cde3232c8" # channel IDs are not part of the extractor when using alyx
# eid = "dd4da095-4a99-4bf3-9727-f735077dba66" # z value outside the atlas volume
eid = "6713a4a7-faed-4df2-acab-ee4e63326f8d" # timestamps issue (for heberto)
eid = "004d8fd5-41e7-4f1b-a45b-0d4ad76fe446" # KeyError: ''
eid = "1f095590-6669-46c9-986b-ccaf0620c5e9" # npx 4?


# instantiating onegit
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
    print(f"attempting to reset cache tables ... ")
    one = ONE(base_url=one_url)
    # remove cache tables if present
    if next(one._tables_dir.glob('*sessions.pqt')).exists():
        one._remove_table_files()
        print(f"... removed cache tables for base_url {one_url}")
    else:
        print("... no cache files found at directory.")
    one.load_cache()
    del one

# instantiate one
one = ONE(**one_kwargs)

print(f'using cache tables from {one._tables_dir}')


# %% the full thing
kwargs = dict(
    one=one,
    revision=REVISION,
    mode=MODE,
    base_path=base_path,
    cleanup=False,
    log_to_file=False,
    verify=False,
    debug=True,
    overwrite=True,
    scratch_path=Path.home() / "scratch"
)

def eid2nwbfilename(eid, one, mode="processed"):
    ref = one.eid2ref(eid)
    base_path = Path("/mnt/home/graiser/quarantine/BWM_to_NWB/nwbfiles")
    match mode:
        case "processed":
            suffix = "processed_behavior+ecephys"
        case "raw":
            suffix = "raw_ecephys+image"

    nwbfile_path = base_path / f"sub-{ref['subject']}" / f"sub-{ref['subject']}_ses-{eid}_desc-{suffix}.nwb"
    return nwbfile_path

if CONVERT:
    print(f"converting {eid} ... ")
    bwm_to_nwb.convert_session(eid=eid, **kwargs)
    print(f" ... done")

if VERIFY:
    print(f"verifying {eid} ... ")
    nwbfile_path = eid2nwbfilename(eid, one, mode=MODE)
    with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
        check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
    print(f" ... all checks passed!")

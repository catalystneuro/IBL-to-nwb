from pathlib import Path

from one.api import ONE

from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency

nwbfile_path = ""

# eid = sys.argv[1]
eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"

# path setup
base_path = Path.home() / "ibl_scratch"
output_folder = base_path / "nwbfiles"
output_folder.mkdir(exist_ok=True, parents=True)

# Initialize IBL (ONE) client to download processed data for this session
one_cache_folder_path = base_path / "ibl_conversion" / eid / "cache"
one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    # mode="local",
    mode="remote",
    # silent=True,
    cache_dir=one_cache_folder_path,
)

subject_id = one.eid2ref(eid)["subject"]

subject_folder_path = output_folder / f"sub-{subject_id}"
subject_folder_path.mkdir(exist_ok=True)
# if raw:
#     fname = f"sub-{subject_id}_ses-{eid}_desc-raw.nwb"
# else:
fname = f"sub-{subject_id}_ses-{eid}_desc-processed.nwb"

nwbfile_path = subject_folder_path / fname
check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)

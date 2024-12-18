import os

os.environ["JUPYTER_PLATFORM_DIRS"] = "1"  # Annoying

import os
from pathlib import Path

from one.api import ONE

from ibl_to_nwb.converters import BrainwideMapConverter
from ibl_to_nwb.datainterfaces import (
    BrainwideMapTrialsInterface,
    IblPoseEstimationInterface,
    IblSortingInterface,
    LickInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)
from ibl_to_nwb.testing._consistency_checks import check_written_nwbfile_for_consistency

# select eid
# -> run download_data_local first with this eid to set up the local folder structure and one cache
eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"

# folders
base_path = Path.home() / "ibl_scratch"
base_path.mkdir(exist_ok=True)
nwbfiles_folder_path = base_path / "nwbfiles"
nwbfiles_folder_path.mkdir(exist_ok=True)

stub_test: bool = False
cleanup: bool = False

# assert len(os.environ.get("DANDI_API_KEY", "")) > 0, "Run `export DANDI_API_KEY=...`!"
revision = None

# Initialize IBL (ONE) client to download processed data for this session
one_cache_folder_path = base_path / "ibl_conversion" / eid / "cache"
one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=True,
    cache_dir=one_cache_folder_path,
)

# Initialize as many of each interface as we need across the streams
data_interfaces = list()

# These interfaces should always be present in source data
data_interfaces.append(IblSortingInterface(one=one, session=eid, revision=revision))
data_interfaces.append(BrainwideMapTrialsInterface(one=one, session=eid, revision=revision))
data_interfaces.append(WheelInterface(one=one, session=eid, revision=revision))

# These interfaces may not be present; check if they are before adding to list
pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
for pose_estimation_file in pose_estimation_files:
    camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
    data_interfaces.append(IblPoseEstimationInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
for pupil_tracking_file in pupil_tracking_files:
    camera_name = pupil_tracking_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
    data_interfaces.append(PupilTrackingInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
for roi_motion_energy_file in roi_motion_energy_files:
    camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
    data_interfaces.append(RoiMotionEnergyInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
    data_interfaces.append(LickInterface(one=one, session=eid, revision=revision))

# Run conversion
session_converter = BrainwideMapConverter(one=one, session=eid, data_interfaces=data_interfaces, verbose=True)

metadata = session_converter.get_metadata()
subject_id = metadata["Subject"]["subject_id"]

subject_folder_path = nwbfiles_folder_path / f"sub-{subject_id}"
subject_folder_path.mkdir(exist_ok=True)
nwbfile_path = subject_folder_path / f"sub-{subject_id}_ses-{eid}_desc-processed_.nwb"

session_converter.run_conversion(
    nwbfile_path=nwbfile_path,
    metadata=metadata,
    overwrite=True,
)

# if cleanup:
#     rmtree(cache_folder)
#     rmtree(nwbfile_path.parent)

check_written_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)

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
from ibl_to_nwb.testing import check_written_nwbfile_for_consistency

session_id = "d32876dd-8303-4720-8e7e-20678dc2fd71"

# Specify the revision of the pose estimation data
# Setting to 'None' will use whatever the latest released revision is
revision = None

base_path = Path("E:/IBL")
base_path.mkdir(exist_ok=True)
nwbfiles_folder_path = base_path / "nwbfiles"
nwbfiles_folder_path.mkdir(exist_ok=True)

# Initialize IBL (ONE) client to download processed data for this session
one_cache_folder_path = base_path / "cache"
ibl_client = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=True,
    cache_dir=one_cache_folder_path,
)

# Initialize as many of each interface as we need across the streams
data_interfaces = list()

# These interfaces should always be present in source data
data_interfaces.append(IblSortingInterface(session=session_id, cache_folder=one_cache_folder_path / "sorting"))
data_interfaces.append(BrainwideMapTrialsInterface(one=ibl_client, session=session_id))
data_interfaces.append(WheelInterface(one=ibl_client, session=session_id))

# These interfaces may not be present; check if they are before adding to list
pose_estimation_files = ibl_client.list_datasets(eid=session_id, filename="*.dlc*")
for pose_estimation_file in pose_estimation_files:
    camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
    data_interfaces.append(
        IblPoseEstimationInterface(
            one=ibl_client,
            session=session_id,
            camera_name=camera_name,
            include_video=False,
            include_pose=True,
            revision=revision,
        )
    )

pupil_tracking_files = ibl_client.list_datasets(eid=session_id, filename="*features*")
for pupil_tracking_file in pupil_tracking_files:
    camera_name = pupil_tracking_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
    data_interfaces.append(PupilTrackingInterface(one=ibl_client, session=session_id, camera_name=camera_name))

roi_motion_energy_files = ibl_client.list_datasets(eid=session_id, filename="*ROIMotionEnergy.npy*")
for roi_motion_energy_file in roi_motion_energy_files:
    camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
    data_interfaces.append(RoiMotionEnergyInterface(one=ibl_client, session=session_id, camera_name=camera_name))

if ibl_client.list_datasets(eid=session_id, collection="alf", filename="licks*"):
    data_interfaces.append(LickInterface(one=ibl_client, session=session_id))

# Run conversion
session_converter = BrainwideMapConverter(
    one=ibl_client, session=session_id, data_interfaces=data_interfaces, verbose=False
)

metadata = session_converter.get_metadata()
subject_id = metadata["Subject"]["subject_id"]

subject_folder_path = nwbfiles_folder_path / f"sub-{subject_id}"
subject_folder_path.mkdir(exist_ok=True)
nwbfile_path = subject_folder_path / f"sub-{subject_id}_ses-{session_id}_desc-processed_behavior+ecephys.nwb"

session_converter.run_conversion(
    nwbfile_path=nwbfile_path,
    metadata=metadata,
    overwrite=True,
)

check_written_nwbfile_for_consistency(one=ibl_client, nwbfile_path=nwbfile_path)

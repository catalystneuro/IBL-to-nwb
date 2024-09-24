import os

os.environ["JUPYTER_PLATFORM_DIRS"] = "1"  # Annoying

import os
from pathlib import Path

from one.api import ONE

from src.ibl_to_nwb import (
    BrainwideMapConverter,
    BrainwideMapTrialsInterface,
    IblPoseEstimationInterface,
    IblSortingInterface,
    LickInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)

stub_test = False
cleanup = False

base_path = Path("E:/IBL")
session = "d32876dd-8303-4720-8e7e-20678dc2fd71"

nwbfile_path = base_path / "nwbfiles" / session / f"{session}.nwb"
nwbfile_path.parent.mkdir(parents=True, exist_ok=True)

nwbfile_path.parent.mkdir(exist_ok=True)

# Download behavior and spike sorted data for this session
# session_path = base_path / "ibl_conversion" / session
cache_folder = base_path / "ibl_conversion" / session / "cache"
session_one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=True,
    cache_dir=cache_folder,
)

# Initialize as many of each interface as we need across the streams
data_interfaces = list()

# These interfaces should always be present in source data
data_interfaces.append(IblSortingInterface(session=session, cache_folder=cache_folder / "sorting"))
data_interfaces.append(BrainwideMapTrialsInterface(one=session_one, session=session))
data_interfaces.append(WheelInterface(one=session_one, session=session))

# These interfaces may not be present; check if they are before adding to list
pose_estimation_files = session_one.list_datasets(eid=session, filename="*.dlc*")
for pose_estimation_file in pose_estimation_files:
    camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
    data_interfaces.append(
        IblPoseEstimationInterface(one=session_one, session=session, camera_name=camera_name, include_video=False)
    )

pupil_tracking_files = session_one.list_datasets(eid=session, filename="*features*")
for pupil_tracking_file in pupil_tracking_files:
    camera_name = pupil_tracking_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
    data_interfaces.append(PupilTrackingInterface(one=session_one, session=session, camera_name=camera_name))

roi_motion_energy_files = session_one.list_datasets(eid=session, filename="*ROIMotionEnergy.npy*")
for roi_motion_energy_file in roi_motion_energy_files:
    camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
    data_interfaces.append(RoiMotionEnergyInterface(one=session_one, session=session, camera_name=camera_name))

if session_one.list_datasets(eid=session, collection="alf", filename="licks*"):
    data_interfaces.append(LickInterface(one=session_one, session=session))

# Run conversion
session_converter = BrainwideMapConverter(
    one=session_one, session=session, data_interfaces=data_interfaces, verbose=False
)

metadata = session_converter.get_metadata()
metadata["NWBFile"]["session_id"] = metadata["NWBFile"]["session_id"] + "-processed-only"

session_converter.run_conversion(
    nwbfile_path=nwbfile_path,
    metadata=metadata,
    overwrite=True,
)
import sys
from datetime import datetime
from pathlib import Path

# from deploy.iblsdsc import OneSdsc as ONE
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
from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency


def get_last_before(eid: str, one: ONE, revision: str):
    revisions = one.list_revisions(eid)
    revisions = [datetime.strptime(revision, "%Y-%m-%d") for revision in revisions[1:]]
    revision = datetime.strptime(revision, "%Y-%m-%d")
    revisions = sorted(revisions)
    ix = sum([not (rev > revision) for rev in revisions])
    return revisions[ix]


def convert(eid: str, one: ONE, data_interfaces: list, raw: bool):
    # Run conversion
    session_converter = BrainwideMapConverter(one=one, session=eid, data_interfaces=data_interfaces, verbose=True)
    metadata = session_converter.get_metadata()
    subject_id = metadata["Subject"]["subject_id"]

    subject_folder_path = output_folder / f"sub-{subject_id}"
    subject_folder_path.mkdir(exist_ok=True)
    if raw:
        fname = f"sub-{subject_id}_ses-{eid}_desc-raw.nwb"
    else:
        fname = f"sub-{subject_id}_ses-{eid}_desc-processed.nwb"

    nwbfile_path = subject_folder_path / fname
    session_converter.run_conversion(
        nwbfile_path=nwbfile_path,
        metadata=metadata,
        overwrite=True,
    )
    return nwbfile_path


if __name__ == "__main__":
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
        mode="local",
        # silent=True,
        cache_dir=one_cache_folder_path,
    )

    revision = get_last_before(eid=eid, one=one, revision="2024-07-10")

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
        data_interfaces.append(
            IblPoseEstimationInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
        )

    pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
    for pupil_tracking_file in pupil_tracking_files:
        camera_name = pupil_tracking_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
        data_interfaces.append(PupilTrackingInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
        data_interfaces.append(
            RoiMotionEnergyInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
        )

    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces.append(LickInterface(one=one, session=eid, revision=revision))

    nwbfile_path = convert(eid=eid, one=one, data_interfaces=data_interfaces, raw=False)

    # check
    check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)

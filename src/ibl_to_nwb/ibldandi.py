import os
import shutil
from pathlib import Path
from typing import List

import spikeglx

from ibl_to_nwb.helpers import create_symlinks

from ibl_to_nwb.converters import BrainwideMapConverter, IblSpikeGlxConverter
from ibl_to_nwb.datainterfaces import (
    BrainwideMapTrialsInterface,
    IblPoseEstimationInterface,
    IblSortingInterface,
    LickInterface,
    PupilTrackingInterface,
    RawVideoInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)

from brainwidemap.bwm_loading import bwm_query


def _get_processed_data_interfaces(one, eid, revision=None):
    """
    Returns a list of the data interfaces to build the processed NWB file for this session
    :param one:
    :param eid:
    :param revision:
    :return:
    """
    data_interfaces = []
    data_interfaces.append(IblSortingInterface(one=one, session=eid, revision=revision))
    data_interfaces.append(BrainwideMapTrialsInterface(one=one, session=eid, revision=revision))
    data_interfaces.append(WheelInterface(one=one, session=eid, revision=revision))

    # # These interfaces may not be present; check if they are before adding to list
    pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
    for pose_estimation_file in pose_estimation_files:
        camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
        data_interfaces.append(
            IblPoseEstimationInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
        )

    pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
    for pupil_tracking_file in pupil_tracking_files:
        camera_name = pupil_tracking_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
        data_interfaces.append(
            PupilTrackingInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
        )

    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
        data_interfaces.append(
            RoiMotionEnergyInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
        )

    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces.append(LickInterface(one=one, session=eid, revision=revision))
    return data_interfaces


def _get_raw_data_interfaces(one, eid, session_folder=None) -> List:
    """
    Returns a list of the data interfaces to build the raw NWB file for this session
    :param one:
    :param eid:
    :param session_folder: if the data is in a temporary directory that doesn't match the ONE cache directory
    :return:
    """
    session_folder = one.eid2path(eid) if session_folder is None else Path(session_folder)
    # check and decompress
    for file_cbin in session_folder.rglob("*.cbin"):
        if not file_cbin.with_suffix(".bin").exists():
            print(f"decompressing {file_cbin}")
            spikeglx.Reader(file_cbin).decompress_to_scratch()

    data_interfaces = []

    # get the pid/pname mapping for this eid
    bwm_df = bwm_query(freeze='2023_12_bwm_release', one=one, return_details=True)
    pname_pid_map = bwm_df.set_index('eid').loc[eid][['probe_name','pid']].to_dict()
    # Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
    spikeglx_subconverter = IblSpikeGlxConverter(folder_path=session_folder, one=one, eid=eid, pname_pid_map=pname_pid_map)
    data_interfaces.append(spikeglx_subconverter)

    # video
    metadata_retrieval = BrainwideMapConverter(one=one, session=eid, data_interfaces=[], verbose=False)
    subject_id = metadata_retrieval.get_metadata()["Subject"]["subject_id"]
    pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
    for pose_estimation_file in pose_estimation_files:
        camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
        video_interface = RawVideoInterface(
            nwbfiles_folder_path=output_folder,
            subject_id=subject_id,
            one=one,
            session=eid,
            camera_name=camera_name,
        )
        data_interfaces.append(video_interface)
    return data_interfaces


def convert_session(eid=None, one=None, revision=None, cleanup=True):

    assert one is not None
    # path setup
    base_path = Path.home() / "ibl_scratch"
    output_folder = base_path / "nwbfiles"
    output_folder.mkdir(exist_ok=True, parents=True)
    session_scratch_folder = base_path / eid
    session_folder = one.eid2path(eid)

    # creates the raw NWB file
    create_symlinks(session_folder, session_scratch_folder)
    session_converter = BrainwideMapConverter(one=one, session=eid, data_interfaces=_get_raw_data_interfaces(one, eid, session_folder=session_folder), verbose=True)
    metadata = session_converter.get_metadata()
    metadata["NWBFile"]["session_id"] = f"{eid}:{revision}"  # FIXME this hack has to go
    subject_id = metadata["Subject"]["subject_id"]
    session_converter.run_conversion(
        nwbfile_path=output_folder.joinpath(f"sub-{subject_id}", f"sub-{subject_id}_ses-{eid}_desc-raw_ecephys+image.nwb"),
        metadata=metadata,
        overwrite=True,
    )
    if cleanup:
        # find . -type l -exec unlink {} \;")
        os.system(f"find {session_scratch_folder} -type l -exec unlink {{}} \;")
        shutil.rmtree(session_scratch_folder)

    # creates the processed NWB file
    session_converter = BrainwideMapConverter(one=one, session=eid, data_interfaces=_get_processed_data_interfaces(one, eid, revision=session_folder), verbose=True)
    metadata = session_converter.get_metadata()
    metadata["NWBFile"]["session_id"] = f"{eid}:{revision}"  # FIXME this hack has to go
    session_converter.run_conversion(
        nwbfile_path=f"sub-{subject_id}_ses-{eid}_desc-processed_behavior+ecephys.nwb",
        metadata=metadata,
        overwrite=True,
    )

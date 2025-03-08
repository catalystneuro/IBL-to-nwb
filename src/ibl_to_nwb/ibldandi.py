import os
import shutil
from pathlib import Path
from typing import List

import spikeglx

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

import os
from pathlib import Path
from one.alf.spec import is_uuid_string


"""
########     ###    ######## ##     ##
##     ##   ## ##      ##    ##     ##
##     ##  ##   ##     ##    ##     ##
########  ##     ##    ##    #########
##        #########    ##    ##     ##
##        ##     ##    ##    ##     ##
##        ##     ##    ##    ##     ##
"""

def setup_paths(eid, one, base_path=Path.home() / "ibl_scratch"):
    # TODO here we need to figure out what is where now eventually

    paths = dict(
        output_folder=base_path / "nwbfiles",
        session_folder=one.eid2path(eid),  # <- to be changed
        session_scratch_folder=base_path / eid, # <- to be changed to be locally on the node
    )

    # inferred from above
    paths["spikeglx_source_folder_path"] = paths["session_folder"] / "raw_ephys_data"

    # just to be on the safe side
    for _, path in paths.items():
        path.mkdir(exist_ok=True, parents=True)

    return paths


def create_symlinks(source_dir, target_dir, remove_uuid=True, filter=None):
    """replicates the tree under source_dir at target dir in the form of symlinks"""

    for root, dirs, files in os.walk(source_dir):
        for file in files:
            source_file_path = Path(root) / file
            if filter is not None:
                if filter not in str(source_file_path):
                    continue

            target_file_path = target_dir / source_file_path.relative_to(source_dir)
            target_file_path.parent.mkdir(parents=True, exist_ok=True)

            if remove_uuid:
                parent, name = target_file_path.parent, target_file_path.name
                name_parts = name.split(".")
                if is_uuid_string(name_parts[-2]):
                    name_parts.remove(name_parts[-2])
                target_file_path = parent / ".".join(name_parts)
            if not target_file_path.exists():
                target_file_path.symlink_to(source_file_path)


def paths_cleanup(paths):
    # unlink the symlinks in the scratch folder and remove the scratch 
    os.system(f"find {paths['session_scratch_folder']} -type l -exec unlink {{}} \;")
    shutil.rmtree(paths["session_scratch_folder"])



"""
########     ###    ########    ###       #### ##    ## ######## ######## ########  ########    ###     ######  ########  ######
##     ##   ## ##      ##      ## ##       ##  ###   ##    ##    ##       ##     ## ##         ## ##   ##    ## ##       ##    ##
##     ##  ##   ##     ##     ##   ##      ##  ####  ##    ##    ##       ##     ## ##        ##   ##  ##       ##       ##
##     ## ##     ##    ##    ##     ##     ##  ## ## ##    ##    ######   ########  ######   ##     ## ##       ######    ######
##     ## #########    ##    #########     ##  ##  ####    ##    ##       ##   ##   ##       ######### ##       ##             ##
##     ## ##     ##    ##    ##     ##     ##  ##   ###    ##    ##       ##    ##  ##       ##     ## ##    ## ##       ##    ##
########  ##     ##    ##    ##     ##    #### ##    ##    ##    ######## ##     ## ##       ##     ##  ######  ########  ######
"""

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
        data_interfaces.append(PupilTrackingInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
        data_interfaces.append(
            RoiMotionEnergyInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
        )

    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces.append(LickInterface(one=one, session=eid, revision=revision))
    return data_interfaces


def _get_raw_data_interfaces(one, eid, paths) -> List:
    """
    Returns a list of the data interfaces to build the raw NWB file for this session
    :param one:
    :param eid:
    :return:
    """
    data_interfaces = []

    # get the pid/pname mapping for this eid
    bwm_df = bwm_query(
        freeze="2023_12_bwm_release", one=one, return_details=True
    )  # TODO proper freeze, also return_details and freeze together doesn't work

    pname_pid_map = bwm_df.set_index("eid").loc[eid][["probe_name", "pid"]].to_dict()

    # Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
    spikeglx_subconverter = IblSpikeGlxConverter(
        folder_path=paths["session_folder"], one=one, eid=eid, pname_pid_map=pname_pid_map
    )
    data_interfaces.append(spikeglx_subconverter)

    # video
    metadata_retrieval = BrainwideMapConverter(one=one, session=eid, data_interfaces=[], verbose=False)
    subject_id = metadata_retrieval.get_metadata()["Subject"]["subject_id"]

    pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
    for pose_estimation_file in pose_estimation_files:
        camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
        video_interface = RawVideoInterface(
            nwbfiles_folder_path=paths["output_folder"],
            subject_id=subject_id,
            one=one,
            session=eid,
            camera_name=camera_name,
        )
        data_interfaces.append(video_interface)
    return data_interfaces

"""
########  ########  ######## ########
##     ## ##     ## ##       ##     ##
##     ## ##     ## ##       ##     ##
########  ########  ######   ########
##        ##   ##   ##       ##
##        ##    ##  ##       ##
##        ##     ## ######## ##
"""
def decompress_ephys_cbins(folder):
    # decompress cbin if necessary
    for file_cbin in folder.rglob("*.cbin"):
        if not file_cbin.with_suffix(".bin").exists():
            print(f"decompressing {file_cbin}")
            spikeglx.Reader(file_cbin).decompress_to_scratch()

"""
 ######   #######  ##    ## ##     ## ######## ########  ########
##    ## ##     ## ###   ## ##     ## ##       ##     ##    ##
##       ##     ## ####  ## ##     ## ##       ##     ##    ##
##       ##     ## ## ## ## ##     ## ######   ########     ##
##       ##     ## ##  ####  ##   ##  ##       ##   ##      ##
##    ## ##     ## ##   ###   ## ##   ##       ##    ##     ##
 ######   #######  ##    ##    ###    ######## ##     ##    ##
"""
def convert_session(eid=None, one=None, revision=None, cleanup=True, mode='raw'):
    assert one is not None
    
    # path setup
    paths = setup_paths(eid, one)
    # symlink the entire session from the main storage to a local scratch
    # TODO potentially not safe - tbd how
    create_symlinks(paths["session_folder"], paths["session_scratch_folder"])
    
    # we want this probably because we will re-run processed more often than raw
    match mode: 
        case 'raw':
            decompress_ephys_cbins(paths['']) # TODO tbd where they will be now
            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=_get_raw_data_interfaces(one, eid, session_folder=paths[""]),  # TODO tbd where they will be now
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            session_converter.run_conversion(
                nwbfile_path=paths["output_folder"].joinpath(
                    f"sub-{subject_id}", f"sub-{subject_id}_ses-{eid}_desc-raw_ecephys+image.nwb"
                ),
                metadata=metadata,
                ibl_metadata=dict(revision=revision),
                overwrite=True,
            )

        case 'processed':
            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=_get_processed_data_interfaces(one, eid, revision=revision),
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            session_converter.run_conversion(
                nwbfile_path=f"sub-{subject_id}_ses-{eid}_desc-processed_behavior+ecephys.nwb",
                metadata=metadata,
                ibl_metadata=dict(revision=revision),
                overwrite=True,
            )

    if cleanup:
        paths_cleanup(paths)
        
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

from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency
from ibl_to_nwb.fixtures import load_fixtures

import os
from pathlib import Path
from one.alf.spec import is_uuid_string
from one.api import ONE

import logging

def setup_logger():
    # Create a logger
    logger = logging.getLogger('ibl_to_nwb')
    logger.setLevel(logging.DEBUG)

    # Create file handler
    file_handler = logging.FileHandler(Path.home() / 'bwm_conversion.log')
    file_handler.setLevel(logging.DEBUG)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # Create a formatter and set it for both handlers
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

_logger = setup_logger()

"""
########     ###    ######## ##     ##
##     ##   ## ##      ##    ##     ##
##     ##  ##   ##     ##    ##     ##
########  ##     ##    ##    #########
##        #########    ##    ##     ##
##        ##     ##    ##    ##     ##
##        ##     ##    ##    ##     ##
"""

def setup_paths(one: ONE, eid: str, base_path: Path = Path.home() / "ibl_bmw_to_nwb") -> dict:
    """ setup a dictionary that ontains all relevant paths for the conversion

    Args:
        one (ONE): _description_
        eid (str): _description_
        base_path (Path, optional): unclear if necessary. Defaults to Path.home()/"ibl_bmw_to_nwb".

    Returns:
        dict: _description_
    """

    subject = one.eid2ref(eid)['subject']
    paths = dict(
        output_folder = base_path / "nwbfiles" / f"sub-{subject}",
        session_folder = one.eid2path(eid),  # <- this is the folder on the main storage: /mnt/sdcepth/users/ibl/data
        scratch_folder = Path('/scratch') # <- this is to be changed to /scratch on the node
    )

    # inferred from above
    paths["session_scratch_folder"] = paths["scratch_folder"] / eid
    paths["spikeglx_source_folder"] = paths["session_scratch_folder"] / "raw_ephys_data" # <- this will be based on the session_scratch_folder 

    # just to be on the safe side
    for _, path in paths.items():
        path.mkdir(exist_ok=True, parents=True)

    return paths


# def create_symlinks(source_dir: Path, target_dir: Path, remove_uuid=True, filter=None):
#     """replicates the tree under source_dir at target dir in the form of symlinks"""

#     for root, dirs, files in os.walk(source_dir):
#         for file in files:
#             source_file_path = Path(root) / file
#             if filter is not None:
#                 if filter not in str(source_file_path):
#                     continue

#             target_file_path = target_dir / source_file_path.relative_to(source_dir)
#             target_file_path.parent.mkdir(parents=True, exist_ok=True)

#             if remove_uuid:
#                 parent, name = target_file_path.parent, target_file_path.name
#                 name_parts = name.split(".")
#                 if is_uuid_string(name_parts[-2]):
#                     name_parts.remove(name_parts[-2])
#                 target_file_path = parent / ".".join(name_parts)
#             if not target_file_path.exists():
#                 target_file_path.symlink_to(source_file_path)

def remove_uuid_from_filepath(file_path: Path) -> Path:
    """if the filename contains an uuid string, it is removed. Otherwise, just returns the path.

    Args:
        file_path (Path): _description_

    Returns:
        Path: _description_
    """
    
    dir, name = file_path.parent, file_path.name
    name_parts = name.split(".")
    if is_uuid_string(name_parts[-2]):
        name_parts.remove(name_parts[-2])
        _logger.debug(f"removing uuid from file {file_path}")
        return dir / ".".join(name_parts)
    else:
        return file_path

# def tree_copy(source_dir: Path, target_dir: Path, remove_uuid:bool=True, filter:str='.cbin'):
#     """copies all files found under source_dir (including subdirectories) to target_dir. Replicates the tree,
#     optionally removes uuids from filenames and exludes files in filter
#     this could have include or exclude

#     Args:
#         source_dir (Path): _description_
#         target_dir (Path): _description_
#         remove_uuid (bool, optional): _description_. Defaults to True.
#         filter (str, optional): _description_. Defaults to '.cbin'.
#     """

#     for root, dirs, files in os.walk(source_dir):
#         for file in files:
#             source_file_path = Path(root) / file
#             if filter is not None:
#                 if filter not in str(source_file_path):
#                     continue

#             target_file_path = target_dir / source_file_path.relative_to(source_dir)
#             target_file_path.parent.mkdir(parents=True, exist_ok=True)

#             if remove_uuid:
#                 parent, name = target_file_path.parent, target_file_path.name
#                 name_parts = name.split(".")
#                 if is_uuid_string(name_parts[-2]):
#                     name_parts.remove(name_parts[-2])
#                 target_file_path = parent / ".".join(name_parts)
#             if not target_file_path.exists():
#                 shutil.copy(source_file_path, target_file_path)

def filter_file_paths(file_paths: list[Path], include: list|None = None, exclude: list|None = None) ->list[Path]:
    # include filter
    if include is not None:
        file_paths_ = []
        if not isinstance(include, list):
            include = [include]
        for incl in include:
            [file_paths_.append(f) for f in file_paths if incl in f.name]
        file_paths = list(set(file_paths_))

    # exclude filter
    if exclude is not None:
        exclude_paths = []
        if not isinstance(exclude, list):
            exclude = [exclude]
            for excl in exclude:
                [exclude_paths.append(f) for f in file_paths if excl in f.name]
        file_paths = list(set(file_paths) - set(exclude_paths))

    return list(file_paths)

def tree_copy(source_dir: Path, target_dir: Path, remove_uuid:bool=True, include=None, exclude=None):
    # include and exclude can be lists
    file_paths = list(source_dir.rglob('**/*'))
    if include is not None or exclude is not None:
        file_paths = filter_file_paths(file_paths, include, exclude)
    
    for source_file_path in file_paths:
        if source_file_path.is_file():
            target_file_path = target_dir / source_file_path.relative_to(source_dir)
            if remove_uuid:
                target_file_path = remove_uuid_from_filepath(target_file_path)
            if not target_file_path.exists():
                _logger.debug(f"copying {source_file_path} to {target_file_path}")
                shutil.copy(source_file_path, target_file_path)
            else:
                _logger.debug(f"skipping copy for {source_file_path} to {target_file_path}, exists already")

def paths_cleanup(paths: dict):
    # unlink the symlinks in the scratch folder and remove the scratch 
    # os.system(f"find {paths['session_scratch_folder']} -type l -exec unlink {{}} \;")
    _logger.debug(f"removing {paths['session_scratch_folder']}")
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

def _get_processed_data_interfaces(one: ONE, eid: str, revision:str=None) -> list:
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


def _get_raw_data_interfaces(one, eid: str, paths: dict, revision=None) -> list:
    """
    Returns a list of the data interfaces to build the raw NWB file for this session
    :param one:
    :param eid:
    :return:
    """
    data_interfaces = []

    # get the pid/pname mapping for this eid
    bwm_df = load_fixtures.load_bwm_df()
    df = bwm_df.groupby('eid').get_group(eid)
    pname_pid_map = df.set_index('probe_name')['pid'].to_dict()

    # Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
    spikeglx_subconverter = IblSpikeGlxConverter(
        folder_path=paths["spikeglx_source_folder"], one=one, eid=eid, pname_pid_map=pname_pid_map, revision=revision,
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
def decompress_ephys_cbins(source_folder:Path, target_folder:Path|None=None, remove_uuid:bool=True):
    # target is the folder to compress into

    # decompress cbin if necessary
    for file_cbin in source_folder.rglob("*.cbin"):
        if target_folder is not None:
            target_bin = (target_folder / file_cbin.relative_to(source_folder)).with_suffix('.bin')
            # target_bin = target_folder / file_cbin.with_suffix('.bin').name
        else:
            target_bin = file_cbin.with_suffix(".bin")
        target_bin_no_uuid = remove_uuid_from_filepath(target_bin)
        target_bin_no_uuid.parent.mkdir(parents=True, exist_ok=True)

        if not target_bin_no_uuid.exists():
            _logger.info(f"decompressing {file_cbin}")
            
            # find corresponding meta file
            name = remove_uuid_from_filepath(file_cbin).stem
            file_meta, = list(file_cbin.parent.glob(f'{name}*.meta'))
            file_ch, = list(file_cbin.parent.glob(f'{name}*.ch'))
            # if file_cbin.name.split('.')[-2] == 'nidq':
            #     file_meta, = list(file_cbin.parent.glob(f'{name}*{band}.meta'))
            #     file_ch, = list(file_cbin.parent.glob(f'{name}*{band}.ch'))
            # else:
            #     band = file_cbin.name.split('.')[-2]
            #     name = '.'.join(file_cbin.name.split('.')[:-2])
            #     file_meta, = list(file_cbin.parent.glob(f'{name}*{band}.meta'))
            #     file_ch, = list(file_cbin.parent.glob(f'{name}*{band}.ch'))
            
            # copies over the meta file which will still have an uuid
            # spikeglx.Reader(file_cbin).decompress_to_scratch(file_meta=file_meta, file_ch=file_ch, scratch_dir=target_bin.parent)
            spikeglx.Reader(file_cbin, meta_file=file_meta, ch_file=file_ch).decompress_to_scratch(scratch_dir=target_bin.parent)

            if remove_uuid:
                shutil.move(target_bin, target_bin_no_uuid)
            
            # remove uuid from meta file at target directory
            if target_folder is not None and remove_uuid is True:
                file_meta_target = remove_uuid_from_filepath(target_bin.parent / file_meta.name)
                if not file_meta_target.exists():
                    shutil.move(target_bin.parent / file_meta.name, file_meta_target)
                    _logger.info(f"moving {target_bin.parent / file_meta.name} to {file_meta_target}")

"""
 ######   #######  ##    ## ##     ## ######## ########  ########
##    ## ##     ## ###   ## ##     ## ##       ##     ##    ##
##       ##     ## ####  ## ##     ## ##       ##     ##    ##
##       ##     ## ## ## ## ##     ## ######   ########     ##
##       ##     ## ##  ####  ##   ##  ##       ##   ##      ##
##    ## ##     ## ##   ###   ## ##   ##       ##    ##     ##
 ######   #######  ##    ##    ###    ######## ##     ##    ##
"""
def convert_session(eid: str=None, one:ONE=None, revision:str=None, cleanup:bool=True, mode:str='raw', base_path:Path=None, verify:bool=True):
    """converts the session associated with the eid and the revision to .nwb

    Args:
        eid (str, optional): _description_. Defaults to None.
        one (ONE, optional): _description_. Defaults to None.
        revision (str, optional): _description_. Defaults to None.
        cleanup (bool, optional): _description_. Defaults to True.
        mode (str, optional): _description_. Defaults to 'raw'.
        base_path (Path, optional): _description_. Defaults to None.
        verify (bool, optional): _description_. Defaults to True.
    """
    
    # path setup
    paths = setup_paths(one, eid, base_path=base_path)

    match mode: 
        case 'raw':
            decompress_ephys_cbins(paths['session_folder'], paths['session_scratch_folder'])
            # now copy the remaining files, copy everything that is not cbin
            tree_copy(paths['session_folder'] / 'raw_ephys_data', paths['session_scratch_folder'] / 'raw_ephys_data', exclude='.cbin')

            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=_get_raw_data_interfaces(one, eid, paths),  # TODO tbd where they will be now
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            fname = f"sub-{subject_id}_ses-{eid}_desc-raw_ecephys+image.nwb"
        
        case 'processed':
            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=_get_processed_data_interfaces(one, eid, revision=revision),
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            fname = f"sub-{subject_id}_ses-{eid}_desc-processed_behavior+ecephys.nwb"
            
        case 'debug':
            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=[WheelInterface(one=one, session=eid, revision=revision)],
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            fname = f"sub-{subject_id}_ses-{eid}_desc-debug.nwb"

    _logger.info(f"converting: {eid} with mode:{mode} ... ")
    session_converter.run_conversion(
        nwbfile_path=paths["output_folder"] / fname,
        metadata=metadata,
        ibl_metadata=dict(revision=revision),
        overwrite=True,
    )
    _logger.info(f" ... done successfully: {eid} with mode:{mode}")

    if cleanup:
        paths_cleanup(paths)

    if verify:
        check_nwbfile_for_consistency(one=one, nwbfile_path=paths["output_folder"] / fname)
        _logger.info(f"all checks passed for {eid} with mode:{mode}")
        
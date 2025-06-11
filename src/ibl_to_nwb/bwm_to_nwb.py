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
import traceback

"""
########     ###    ######## ##     ##
##     ##   ## ##      ##    ##     ##
##     ##  ##   ##     ##    ##     ##
########  ##     ##    ##    #########
##        #########    ##    ##     ##
##        ##     ##    ##    ##     ##
##        ##     ##    ##    ##     ##
"""


def setup_paths(one: ONE, eid: str, base_path: Path = None, scratch_path: Path = None) -> dict:
    """
    This function creates a structured dictionary of paths necessary for the NWB conversion,
    including output folders, session folders, and scratch directories. It also ensures
    that all specified directories exist.

    Parameters:
    -----------
    one : ONE
        An instance of the ONE (Open Neurophysiology Environment) API.
    eid : str
        The experiment ID for the session being converted.
    base_path : Path, optional
        The base path for output files. If None, defaults to ~/ibl_bmw_to_nwb.
    scratch_path : Path, optional
        The path for temporary/scratch files. If None, defaults to /scratch.

    Returns:
    --------
    dict
        A dictionary containing the following paths:
        - output_folder: Path to store the output NWB files.
        - session_folder: Path to the original session data.
        - scratch_folder: Path for temporary files.
        - session_scratch_folder: Path for session-specific temporary files.
        - spikeglx_source_folder: Path to the raw ephys data within the scratch folder.
    """

    base_path = Path.home() / "ibl_bmw_to_nwb" if base_path is None else base_path
    scratch_path = Path("/scratch") if scratch_path is None else scratch_path
    subject = one.eid2ref(eid)["subject"]
    paths = dict(
        output_folder=base_path / "nwbfiles" / f"sub-{subject}",
        session_folder=one.eid2path(eid),  # <- this is the folder on the main storage: /mnt/sdcepth/users/ibl/data
        scratch_folder=scratch_path,  # <- this is to be changed to /scratch on the node
    )
    if "USE_SDSC_ONE" in os.environ:
        paths["scratch_folder"] = (Path("/scratch"),)  # <- on SDSC, a per node /scratch folder exists for this purpose
    else:
        paths["scratch_folder"] = Path.home() / "ibl_scratch"  # for local usage

    # inferred from above
    paths["session_scratch_folder"] = paths["scratch_folder"] / eid
    paths["spikeglx_source_folder"] = (
        paths["session_scratch_folder"] / "raw_ephys_data"
    )  # <- this will be based on the session_scratch_folder

    # just to be on the safe side
    for _, path in paths.items():
        path.mkdir(exist_ok=True, parents=True)

    return paths


def remove_uuid_from_filepath(file_path: Path) -> Path:
    # if the filename contains an uuid string, it is removed. Otherwise, just returns the path.

    dir, name = file_path.parent, file_path.name
    name_parts = name.split(".")
    if is_uuid_string(name_parts[-2]):
        name_parts.remove(name_parts[-2])
        # _logger.debug(f"removing uuid from file {file_path}")
        return dir / ".".join(name_parts)
    else:
        return file_path


def filter_file_paths(file_paths: list[Path], include: list | None = None, exclude: list | None = None) -> list[Path]:
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


def tree_copy(source_dir: Path, target_dir: Path, remove_uuid: bool = True, include=None, exclude=None):
    # include and exclude can be lists
    file_paths = list(source_dir.rglob("**/*"))
    if include is not None or exclude is not None:
        file_paths = filter_file_paths(file_paths, include, exclude)

    for source_file_path in file_paths:
        if source_file_path.is_file():
            target_file_path = target_dir / source_file_path.relative_to(source_dir)
            if remove_uuid:
                target_file_path = remove_uuid_from_filepath(target_file_path)
            if not target_file_path.exists():
                # _logger.debug(f"copying {source_file_path} to {target_file_path}")
                shutil.copy(source_file_path, target_file_path)
            # else:
            #     _logger.debug(f"skipping copy for {source_file_path} to {target_file_path}, exists already")


def paths_cleanup(paths: dict):
    # unlink the symlinks in the scratch folder and remove the scratch
    # os.system(f"find {paths['session_scratch_folder']} -type l -exec unlink {{}} \;")
    # _logger.debug(f"removing {paths['session_scratch_folder']}")
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


def get_camera_name_from_file(filepath):
    # smaller helper
    filename = Path(filepath).name
    if filename.startswith("_ibl_"):
        filename = filename.split("_ibl_")[1]  # remove namespace
    camera_name = filename.split(".")[0]  # remove suffixes
    return camera_name


def _get_processed_data_interfaces(one: ONE, eid: str, revision: str = None) -> list:
    # Returns a list of the data interfaces to build the processed NWB file for this session

    data_interfaces = []
    data_interfaces.append(IblSortingInterface(one=one, session=eid, revision=revision))
    data_interfaces.append(BrainwideMapTrialsInterface(one=one, session=eid, revision=revision))
    data_interfaces.append(WheelInterface(one=one, session=eid, revision=revision))

    # # These interfaces may not be present; check if they are before adding to list
    pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
    for pose_estimation_file in pose_estimation_files:
        # camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
        # camera_name = Path(pose_estimation_file).stem.split('_ibl_')[1].split('.')[0]
        camera_name = get_camera_name_from_file(pose_estimation_file)
        data_interfaces.append(IblPoseEstimationInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

    pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
    camera_names = []
    for pupil_tracking_file in pupil_tracking_files:
        camera_names.append(get_camera_name_from_file(pupil_tracking_file))
    camera_names = set(camera_names)
    for camera_name in camera_names:
        data_interfaces.append(PupilTrackingInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    camera_names = []
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_names.append(get_camera_name_from_file(roi_motion_energy_file))
    camera_names = set(camera_names)
    for camera_name in camera_names:
        data_interfaces.append(RoiMotionEnergyInterface(one=one, session=eid, camera_name=camera_name, revision=revision))

    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces.append(LickInterface(one=one, session=eid, revision=revision))
    return data_interfaces


def _get_raw_data_interfaces(one, eid: str, paths: dict, revision=None) -> list:
    # Returns a list of the data interfaces to build the raw NWB file for this session

    data_interfaces = []

    # get the pid/pname mapping for this eid
    bwm_df = load_fixtures.load_bwm_df()
    df = bwm_df.groupby("eid").get_group(eid)
    pname_pid_map = df.set_index("probe_name")["pid"].to_dict()

    # Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
    spikeglx_subconverter = IblSpikeGlxConverter(
        folder_path=paths["spikeglx_source_folder"],
        one=one,
        eid=eid,
        pname_pid_map=pname_pid_map,
        revision=revision,
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


def decompress_ephys_cbins(source_folder: Path, target_folder: Path | None = None, remove_uuid: bool = True):
    # target is the folder to compress into

    # decompress cbin if necessary
    cbin_files = source_folder.rglob("*.cbin")
    if len(cbin_files) == 0:
        # TODO should copmlain
        # _logger.critical('no .cbin files found to decompress')
        ...

    for file_cbin in cbin_files:
        if target_folder is not None:
            target_bin = (target_folder / file_cbin.relative_to(source_folder)).with_suffix(".bin")
            # target_bin = target_folder / file_cbin.with_suffix('.bin').name
        else:
            target_bin = file_cbin.with_suffix(".bin")
        target_bin_no_uuid = remove_uuid_from_filepath(target_bin)
        target_bin_no_uuid.parent.mkdir(parents=True, exist_ok=True)

        if not target_bin_no_uuid.exists():
            # _logger.info(f"decompressing {file_cbin}")

            # find corresponding meta file
            name = remove_uuid_from_filepath(file_cbin).stem
            (file_meta,) = list(file_cbin.parent.glob(f"{name}*.meta"))
            (file_ch,) = list(file_cbin.parent.glob(f"{name}*.ch"))

            # copies over the meta file which will still have an uuid
            spikeglx.Reader(file_cbin, meta_file=file_meta, ch_file=file_ch).decompress_to_scratch(scratch_dir=target_bin.parent)

            if remove_uuid:
                shutil.move(target_bin, target_bin_no_uuid)

            # remove uuid from meta file at target directory
            if target_folder is not None and remove_uuid is True:
                file_meta_target = remove_uuid_from_filepath(target_bin.parent / file_meta.name)
                if not file_meta_target.exists():
                    shutil.move(target_bin.parent / file_meta.name, file_meta_target)
                    # _logger.info(f"moving {target_bin.parent / file_meta.name} to {file_meta_target}")


"""
 ######   #######  ##    ## ##     ## ######## ########  ########
##    ## ##     ## ###   ## ##     ## ##       ##     ##    ##
##       ##     ## ####  ## ##     ## ##       ##     ##    ##
##       ##     ## ## ## ## ##     ## ######   ########     ##
##       ##     ## ##  ####  ##   ##  ##       ##   ##      ##
##    ## ##     ## ##   ###   ## ##   ##       ##    ##     ##
 ######   #######  ##    ##    ###    ######## ##     ##    ##
"""


def convert_session_(**kwargs):
    # a poor mans logger
    try:
        convert_session(**kwargs)
    except Exception as e:
        eid = kwargs["eid"]
        # _logger = logging.getLogger(f'bwm_to_nwb.{eid}')
        with open(kwargs["base_path"] / f"{eid}_err.log", "w") as fH:
            fH.writelines(traceback.format_exception(e))
    return None


def convert_session(
    eid: str = None,
    one: ONE = None,
    revision: str = None,
    cleanup: bool = True,
    mode: str = "raw",
    base_path: Path = None,
    verify: bool = True,
    log_to_file=False,
    debug=False,
    scratch_path=None,
) -> Path:
    """
    Converts a session associated with the given experiment ID (eid) and revision to NWB format.

    This function handles the conversion process for different modes (raw, processed, debug),
    sets up logging, manages file paths, and performs cleanup and verification if specified.

    Parameters:
    -----------
    eid : str, optional
        The experiment ID of the session to be converted.
    one : ONE, optional
        An instance of the ONE API for data retrieval.
    revision : str, optional
        The revision of the data to be used for conversion.
    cleanup : bool, default=True
        If True, removes intermediate data after conversion
    mode : str, default="raw"
        The conversion mode. Can be "raw", "processed", or "debug".
    base_path : Path, optional
        The base path for output and temporary files.
    verify : bool, default=True
        If True, performs consistency checks on the converted NWB file.
    log_to_file : bool, default=False
        If True, logs the conversion process to a file.
    debug : bool, default=False
        If True, runs in debug mode.
    scratch_path : Path, optional
        The path for temporary/scratch files.

    Returns:
    --------
    Path
        The path to the created NWB file.
    """

    # path setup
    paths = setup_paths(one, eid, base_path=base_path, scratch_path=scratch_path)

    # create sublogger with a seperate file handle to log each conversion into a seperate file
    _logger = logging.getLogger(f"bwm_to_nwb.{eid}")
    _logger.setLevel(logging.DEBUG)
    _logger.debug(f"logger set up for {eid}")
    if log_to_file:
        handler = logging.FileHandler(base_path / f"{eid}.log")
        handler.setLevel(logging.DEBUG)
        _logger.addHandler(handler)
        _logger.debug(f"initializing data interfaces for mode {mode} ")

    match mode:
        case "raw":
            _logger.debug("decompressing raw ephys data ... ")
            decompress_ephys_cbins(paths["session_folder"], paths["session_scratch_folder"])
            # now copy the remaining files, copy everything that is not cbin
            _logger.debug("copying raw ephys data to local scratch ... ")
            tree_copy(
                paths["session_folder"] / "raw_ephys_data",
                paths["session_scratch_folder"] / "raw_ephys_data",
                exclude=".cbin",
            )
            _logger.debug(" ...done")

            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=_get_raw_data_interfaces(one, eid, paths),  # TODO tbd where they will be now
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            fname = f"sub-{subject_id}_ses-{eid}_desc-raw_ecephys+image.nwb"

        case "processed":
            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=_get_processed_data_interfaces(one, eid, revision=revision),
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            fname = f"sub-{subject_id}_ses-{eid}_desc-processed_behavior+ecephys.nwb"

        case "debug":
            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=[
                    IblSortingInterface(one=one, session=eid, revision=revision),
                ],
                # data_interfaces=[WheelInterface(one=one, session=eid, revision=revision)],
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            fname = f"sub-{subject_id}_ses-{eid}_desc-debug.nwb"

    _logger.info(f"converting: {eid} with mode:{mode} ... ")
    nwbfile_path = paths["output_folder"] / fname
    session_converter.run_conversion(
        nwbfile_path=nwbfile_path,
        metadata=metadata,
        ibl_metadata=dict(revision=revision),
        overwrite=True,
    )
    _logger.info(f" ... conversion done. File written to {nwbfile_path}")

    if cleanup:
        paths_cleanup(paths)
        _logger.info(" cleanup done")

    if verify:
        check_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)
        _logger.info(f"all checks passed for {eid} with mode:{mode}")

    if not debug:
        # for keeping track of the jobs
        running_dir = base_path / "eids_running"
        done_dir = base_path / "eids_done"
        shutil.move(running_dir / f"{eid}", done_dir / f"{eid}")

    return nwbfile_path

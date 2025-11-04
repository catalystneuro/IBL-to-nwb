import logging
import os
import shutil
import traceback
from pathlib import Path

import one
from one.alf.spec import is_uuid_string
from one.api import ONE
from brainbox.io.one import SessionLoader

from ibl_to_nwb.converters import BrainwideMapConverter, IblSpikeGlxConverter
from ibl_to_nwb.datainterfaces import (
    BrainwideMapTrialsInterface,
    IblAnatomicalLocalizationInterface,
    IblSortingInterface,
    IblPoseEstimationInterface,
    LickInterface,
    PassiveIntervalsInterface,
    PassiveReplayStimInterface,
    PassiveRFMInterface,
    PupilTrackingInterface,
    RawVideoInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)
from ibl_to_nwb.fixtures import load_fixtures
from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency
from ibl_to_nwb.utils import decompress_ephys_cbins

"""
########     ###    ######## ##     ##
##     ##   ## ##      ##    ##     ##
##     ##  ##   ##     ##    ##     ##
########  ##     ##    ##    #########
##        #########    ##    ##     ##
##        ##     ##    ##    ##     ##
##        ##     ##    ##    ##     ##
"""

def get_logger(eid: str):
    # helper to get the eid specific logger
    _logger = logging.getLogger(f"bwm_to_nwb.{eid}")
    return _logger

def setup_paths(
    one: ONE,
    eid: str,
    base_path: Path = None,
    decompressed_ephys_path: Path = None,
    logs_path: Path = None,
) -> dict:
    """
    This function creates a structured dictionary of paths necessary for the NWB conversion,
    including output folders, session folders, logs, and scratch directories for ephys data.

    Architecture:
    -------------
    Two separate directories for different purposes:
    - logs_path: Persistent conversion logs (small, kept for auditing)
    - decompressed_ephys_path: Temporary decompressed ephys files (large, deleted after conversion)

    Parameters:
    -----------
    one : ONE
        An instance of the ONE (Open Neurophysiology Environment) API.
    eid : str
        The experiment ID for the session being converted.
    base_path : Path, optional
        The base path for output files. If None, defaults to ~/ibl_bmw_to_nwb.
    decompressed_ephys_path : Path, optional
        Path for temporary decompressed ephys files. If None, defaults based on environment.
        Recommended: Use a location with fast I/O and automatic cleanup (e.g., /scratch on HPC).
    logs_path : Path, optional
        Path for persistent conversion logs. If None, defaults to base_path/conversion_logs.
        Logs are small and should be kept for debugging/auditing.

    Returns:
    --------
    dict
        A dictionary containing the following paths:
        - output_folder: Path to store the output NWB files.
        - session_folder: Path to the original session data (ONE cache).
        - logs_folder: Path for conversion logs (persistent).
        - decompressed_ephys_folder: Path for temporary decompressed ephys files.
        - session_decompressed_ephys_folder: Path for this session's ephys files.
        - spikeglx_source_folder: Path to the raw ephys data for this session.
    """

    base_path = Path.home() / "ibl_bmw_to_nwb" if base_path is None else base_path

    # Logs go to a persistent location (defaults to base_path/conversion_logs)
    if logs_path is None:
        logs_path = base_path / "conversion_logs"

    # Decompressed ephys uses fast temporary storage (defaults based on environment)
    if decompressed_ephys_path is None:
        if "USE_SDSC_ONE" in os.environ:
            decompressed_ephys_path = Path("/scratch")  # <- on SDSC, a per node /scratch folder exists
        else:
            decompressed_ephys_path = base_path / "decompressed_ephys"  # for local usage

    subject = one.eid2ref(eid)["subject"]
    paths = dict(
        output_folder=base_path / "nwbfiles",
        subject=subject,  # Store subject for later use in constructing full paths
        session_folder=one.eid2path(eid),  # <- this is the folder on the main storage
        logs_folder=logs_path,  # Separate logs directory
        decompressed_ephys_folder=decompressed_ephys_path,  # Explicit name for ephys scratch
    )

    # Session-specific paths derived from above
    paths["session_decompressed_ephys_folder"] = paths["decompressed_ephys_folder"] / eid
    paths["spikeglx_source_folder"] = paths["session_decompressed_ephys_folder"] / "raw_ephys_data"

    # Backward compatibility (deprecated - will be removed in future)
    paths["scratch_folder"] = paths["decompressed_ephys_folder"]  # Alias for old code
    paths["session_scratch_folder"] = paths["session_decompressed_ephys_folder"]  # Alias
    paths["ephys_scratch_folder"] = paths["decompressed_ephys_folder"]  # Alias
    paths["session_ephys_scratch_folder"] = paths["session_decompressed_ephys_folder"]  # Alias

    # Create base directories
    paths["output_folder"].mkdir(exist_ok=True, parents=True)
    paths["logs_folder"].mkdir(exist_ok=True, parents=True)
    paths["decompressed_ephys_folder"].mkdir(exist_ok=True, parents=True)
    paths["session_decompressed_ephys_folder"].mkdir(exist_ok=True, parents=True)
    paths["spikeglx_source_folder"].mkdir(exist_ok=True, parents=True)

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
            if target_file_path.exists():
                continue

            target_file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy(source_file_path, target_file_path)
            except FileNotFoundError:
                # Re-attempt after ensuring parent directories exist (handles race conditions)
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
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

def check_camera_health_by_loading(one: ONE = None, session: str = None, revision: str = None):
    try:
        session_loader = SessionLoader(one=one, eid=session, revision=revision)
        session_loader.load_pose(tracker='lightningPose')
        return True
    except: # ALFObjectNotFound or ValueError
        return False

def check_camera_health_by_qc(bwm_qc, eid, camera_name):
    view = camera_name.split('Camera')[0].capitalize()
    qc = bwm_qc[eid][f'video{view}']
    if qc in ['CRITICAL','FAIL']:
        return False
    else:
        return True

def _get_processed_data_interfaces(one: ONE, eid: str, revision: str = None) -> list:
    # Returns a list of the data interfaces to build the processed NWB file for this session
    bwm_qc = load_fixtures.load_bwm_qc()
    _logger = get_logger(eid)

    data_interfaces = []
    interface_kwargs = dict(one=one, session=eid, revision=revision)
    data_interfaces.append(IblSortingInterface(**interface_kwargs))

    # Add anatomical localization after sorting (creates electrodes and links units)
    insertions = one.alyx.rest('insertions', 'list', session=eid)
    probe_name_to_probe_id_dict = {ins['name']: ins['id'] for ins in insertions}
    data_interfaces.append(IblAnatomicalLocalizationInterface(
        one=one, eid=eid, probe_name_to_probe_id_dict=probe_name_to_probe_id_dict, revision=revision
    ))

    data_interfaces.append(BrainwideMapTrialsInterface(**interface_kwargs))
    data_interfaces.append(WheelInterface(**interface_kwargs))

    # Passive period data - add each interface if its data is available
    if PassiveIntervalsInterface.check_availability(one, eid)["available"]:
        data_interfaces.append(PassiveIntervalsInterface(**interface_kwargs))

    if PassiveReplayStimInterface.check_availability(one, eid)["available"]:
        data_interfaces.append(PassiveReplayStimInterface(**interface_kwargs))

    if PassiveRFMInterface.check_availability(one, eid)["available"]:
        data_interfaces.append(PassiveRFMInterface(**interface_kwargs))

    # These interfaces may not be present; check if they are before adding to list
    # pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
    # ugly hack, but workaround for one.list_datasets() with revision behavior
    pose_estimation_files = set([Path(f).name for f in one.list_datasets(eid=eid, filename="*.dlc*")])
    for pose_estimation_file in pose_estimation_files:
        # parse file name to camera
        camera_name = get_camera_name_from_file(pose_estimation_file)
        if check_camera_health_by_qc(bwm_qc, eid, camera_name) and check_camera_health_by_loading(**interface_kwargs):
            data_interfaces.append(IblPoseEstimationInterface(camera_name=camera_name, tracker='lightningPose', **interface_kwargs))

    pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
    camera_names = []
    for pupil_tracking_file in pupil_tracking_files:
        camera_names.append(get_camera_name_from_file(pupil_tracking_file))
    camera_names = set(camera_names)
    for camera_name in camera_names:
        if check_camera_health_by_qc(bwm_qc, eid, camera_name):
            data_interfaces.append(PupilTrackingInterface(camera_name=camera_name, **interface_kwargs))

    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    camera_names = []
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_names.append(get_camera_name_from_file(roi_motion_energy_file))
    camera_names = set(camera_names)
    for camera_name in camera_names:
        if check_camera_health_by_qc(bwm_qc, eid, camera_name):
            data_interfaces.append(RoiMotionEnergyInterface(camera_name=camera_name, **interface_kwargs))
    
    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces.append(LickInterface(**interface_kwargs))
    return data_interfaces


def _get_raw_data_interfaces(one, eid: str, paths: dict, revision=None) -> list:
    # Returns a list of the data interfaces to build the raw NWB file for this session
    data_interfaces = []

    # get the pid/pname mapping for this eid
    insertions = one.alyx.rest('insertions', 'list', session=eid)
    probe_name_to_probe_id_dict = {ins['name']: ins['id'] for ins in insertions}

    # Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
    spikeglx_subconverter = IblSpikeGlxConverter(
        folder_path=paths["spikeglx_source_folder"],
        one=one,
        eid=eid,
        probe_name_to_probe_id_dict=probe_name_to_probe_id_dict,
        revision=revision,
    )
    data_interfaces.append(spikeglx_subconverter)

    # Add anatomical localization after SpikeGLX (links to existing electrodes from recording)
    data_interfaces.append(IblAnatomicalLocalizationInterface(
        one=one, eid=eid, probe_name_to_probe_id_dict=probe_name_to_probe_id_dict, revision=revision
    ))

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
 ######   #######  ##    ## ##     ## ######## ########  ########
##    ## ##     ## ###   ## ##     ## ##       ##     ##    ##
##       ##     ## ####  ## ##     ## ##       ##     ##    ##
##       ##     ## ## ## ## ##     ## ######   ########     ##
##       ##     ## ##  ####  ##   ##  ##       ##   ##      ##
##    ## ##     ## ##   ###   ## ##   ##       ##    ##     ##
 ######   #######  ##    ##    ###    ######## ##     ##    ##
"""


def convert_session_(**kwargs):
    # a poor mans logger diverting errors into a seperate file
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
    decompressed_ephys_path=None,
    overwrite=False,
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
    decompressed_ephys_path : Path, optional
        Directory for temporary decompressed ephys files.

    Returns:
    --------
    Path
        The path to the created NWB file.
    """
    # temporary injection
    if eid == "dc21e80d-97d7-44ca-a729-a8e3f9b14305":
        revision = "2025-06-04"

    # path setup
    paths = setup_paths(one, eid, base_path=base_path, decompressed_ephys_path=decompressed_ephys_path)

    # create sublogger with a seperate file handle to log each conversion into a seperate file
    _logger = logging.getLogger(f"bwm_to_nwb.{eid}")
    _logger.setLevel(logging.DEBUG)
    _logger.debug(f"logger set up for {eid}")
    if log_to_file:
        handler = logging.FileHandler(base_path / f"{eid}.log")
        handler.setLevel(logging.DEBUG)
        _logger.addHandler(handler)
        _logger.debug(f"initializing data interfaces for {eid} with mode {mode} ")

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
            data_interfaces = []
            # These interfaces may not be present; check if they are before adding to list
            pose_estimation_files = set([Path(f).name for f in one.list_datasets(eid=eid, filename="*.dlc*")])
            for pose_estimation_file in pose_estimation_files:
                camera_name = get_camera_name_from_file(pose_estimation_file)
                data_interfaces.append(
                    IblPoseEstimationInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
                )

            session_converter = BrainwideMapConverter(
                one=one,
                session=eid,
                data_interfaces=data_interfaces,
                verbose=True,
            )
            metadata = session_converter.get_metadata()
            subject_id = metadata["Subject"]["subject_id"]
            fname = f"sub-{subject_id}_ses-{eid}_desc-debug.nwb"

    _logger.info(f"converting: {eid} with mode:{mode} ... ")
    nwbfile_path = paths["output_folder"] / fname

    if nwbfile_path.exists():
        if overwrite:
            _logger.warning(f"file: {nwbfile_path} exists already, overwriting")
            os.remove(nwbfile_path)  # for processed. if raw TODO video folder needs to be removed as well
        else:
            _logger.error(f"file: {nwbfile_path} exists already, quitting")
            raise FileExistsError

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

    # if not debug:
    #     # for keeping track of the jobs
    #     running_dir = base_path / "eids_running"
    #     done_dir = base_path / "eids_done"
    #     shutil.move(running_dir / f"{eid}", done_dir / f"{eid}")

    return nwbfile_path

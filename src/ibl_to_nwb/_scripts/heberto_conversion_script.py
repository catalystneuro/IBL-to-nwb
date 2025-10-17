"""Master script to convert IBL sessions (raw and/or processed) with cleanup options.

This script provides a complete conversion pipeline that can be run standalone on any computer.
It orchestrates both raw and processed conversions and includes file cleanup utilities.

You can specify a session either by:
1. EID (session UUID string)
2. Index (0-458) from the Brain Wide Map sessions list
"""

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from one.api import ONE
from pynwb import NWBFile
from ndx_ibl import IblSubject
from ndx_ibl_bwm import ibl_bwm_metadata
import shutil
import logging
import time
import sys

from neuroconv import ConverterPipe
from neuroconv.tools import configure_and_write_nwbfile

from ibl_to_nwb.converters import IblSpikeGlxConverter, BrainwideMapConverter
from ibl_to_nwb.datainterfaces import (
    IblSortingInterface,
    IblAnatomicalLocalizationInterface,
    BrainwideMapTrialsInterface,
    WheelInterface,
    PassivePeriodDataInterface,
    LickInterface,
    IblPoseEstimationInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    RawVideoInterface,
)
from ibl_to_nwb.bwm_to_nwb import (
    setup_paths,
    get_camera_name_from_file,
    check_camera_health_by_qc,
    check_camera_health_by_loading,
    decompress_ephys_cbins,
    tree_copy,
)
from ibl_to_nwb.fixtures import load_fixtures
from ibl_to_nwb.utils import add_probe_electrodes_with_localization


# ============================================================================
# LOGGING SETUP
# ============================================================================
def setup_logger(log_file_path: Path):
    """Setup logger that writes to file in real-time.

    Parameters
    ----------
    log_file_path : Path
        Path to the log file

    Returns
    -------
    logging.Logger
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("IBL_Conversion")
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    logger.handlers = []

    # Create file handler with unbuffered writing
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_handler.setLevel(logging.INFO)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Ensure unbuffered output
    file_handler.stream.reconfigure(line_buffering=True)

    return logger


def download_session_data(
    eid: str,
    one: ONE,
    redownload_data: bool = False,
    stub_test: bool = False,
    revision: str | None = None,
    base_path: Path | None = None,
    scratch_path: Path | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    """Download all datasets for a session from ONE API.

    Parameters
    ----------
    eid : str
        Session experiment ID
    one : ONE
        ONE API instance
    redownload_data : bool, optional
        If True, always re-download data. If False, use cached data when available.
    stub_test : bool, optional
        If True, skip downloading large raw ephys datasets for faster testing.
    revision : str, optional
        Data revision identifier.
    base_path : Path, optional
        Base path for outputs; used to keep caching consistent with conversion.
    scratch_path : Path, optional
        Scratch directory for temporary files and session cache.
    logger : logging.Logger, optional
        Logger instance

    Returns
    -------
    dict
        Dictionary with download timing and size information
    """
    if logger:
        logger.info(
            "Downloading session data from ONE%s..."
            % (f" (revision {revision})" if revision else "")
        )
    download_start = time.time()

    # Setup paths to check cache location
    paths = setup_paths(one, eid, base_path=base_path, scratch_path=scratch_path)

    # Check if we need to clear cached data
    if redownload_data and paths["session_folder"].exists():
        if logger:
            logger.info(f"REDOWNLOAD_DATA is True - clearing cached data for session {eid}")
        # Remove cached files for this session
        shutil.rmtree(paths["session_folder"])
        paths["session_folder"].mkdir(parents=True, exist_ok=True)

    # Download all datasets for this session
    datasets = one.list_datasets(eid, revision=revision) if revision else one.list_datasets(eid)
    skipped_datasets = []
    if stub_test:
        skip_patterns = (
            "raw_ephys_data",
            "raw_video_data",
            "spikes.amps",
            "spikes.depths",
            "spikes.waveforms",
            "spikes.samples",
            "spikes.templates",
            "templates.waveforms",
            "templates.amps",
            "clusters.waveforms",
            "waveforms.",
        )
        filtered_datasets = []
        for dataset in datasets:
            if any(pattern in dataset for pattern in skip_patterns):
                skipped_datasets.append(dataset)
                continue
            filtered_datasets.append(dataset)
        if logger and skipped_datasets:
            logger.info(
                "Stub mode active: skipping download of %d heavy datasets"
                % len(skipped_datasets)
            )
        datasets = filtered_datasets

    if logger:
        logger.info(f"Found {len(datasets)} datasets to download")

    # Check if data is already cached
    cached_files = list(paths["session_folder"].rglob("*")) if paths["session_folder"].exists() else []
    if cached_files and not redownload_data:
        if logger:
            logger.info(f"Using cached data from {paths['session_folder']} ({len(cached_files)} files)")
    else:
        if logger:
            logger.info("Downloading data from ONE API...")

    for dataset in datasets:
        one.load_dataset(eid, dataset)

    download_time = time.time() - download_start

    # Calculate total size of downloaded data
    total_size_bytes = 0
    if paths["session_folder"].exists():
        for file_path in paths["session_folder"].rglob("*"):
            if file_path.is_file():
                total_size_bytes += file_path.stat().st_size

    total_size_gb = total_size_bytes / (1024**3)

    if logger:
        logger.info(f"Download step completed in {download_time:.2f}s")
        logger.info(f"Total downloaded data size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")
        logger.info(f"Download rate: {total_size_gb / (download_time / 3600):.2f} GB/hour")

    return {
        "download_time": download_time,
        "num_datasets": len(datasets),
        "total_size_bytes": total_size_bytes,
        "total_size_gb": total_size_gb,
    }


def convert_raw_session(
    eid: str,
    one: ONE,
    stub_test: bool = False,
    revision: str = None,
    base_path: Path = None,
    scratch_path: Path = None,
    logger: logging.Logger = None,
):
    """Convert IBL raw session to NWB.

    Parameters
    ----------
    eid : str
        Session experiment ID
    one : ONE
        ONE API instance
    stub_test : bool, optional
        Use stub mode for testing
    revision : str, optional
        Data revision
    base_path : Path, optional
        Base path for output files
    scratch_path : Path, optional
        Scratch path for temporary files
    scratch_path : Path, optional
        Scratch path for temporary files
    logger : logging.Logger, optional
        Logger instance
    """

    if logger:
        logger.info(f"Starting RAW conversion for session {eid}")

    # Setup paths
    start_time = time.time()
    paths = setup_paths(one, eid, base_path=base_path, scratch_path=scratch_path)
    if logger:
        logger.info(f"Paths setup completed in {time.time() - start_time:.2f}s")

    # Get probe insertion IDs
    insertions = one.alyx.rest("insertions", "list", session=eid)
    pname_pid_map = {ins["name"]: ins["id"] for ins in insertions}

    include_ecephys = not stub_test
    run_anatomical_localization = True

    # ========================================================================
    # STEP 1: Decompress raw ephys data
    # ========================================================================
    if include_ecephys:
        if logger:
            logger.info("Decompressing raw ephys data...")
        decompress_start = time.time()

        # Decompress .cbin files from ONE cache to scratch folder
        if logger:
            logger.info("Decompressing .cbin files...")
        decompress_ephys_cbins(paths["session_folder"], paths["session_scratch_folder"])

        # Copy metadata files (.meta, .ch, etc.) to scratch folder
        if logger:
            logger.info("Copying metadata files...")
        tree_copy(
            paths["session_folder"] / "raw_ephys_data",
            paths["session_scratch_folder"] / "raw_ephys_data",
            exclude=".cbin",
        )

        decompress_time = time.time() - decompress_start
        if logger:
            logger.info(f"Decompression completed in {decompress_time:.2f}s")
    else:
        if logger:
            logger.info("Stub test mode active: skipping raw ephys decompression")

    # ========================================================================
    # STEP 2: Define data interfaces
    # ========================================================================
    if logger:
        logger.info("Creating data interfaces...")
    interface_creation_start = time.time()

    data_interfaces = []

    spikeglx_converter = None
    if include_ecephys:
        # SpikeGLX converter
        spikeglx_converter = IblSpikeGlxConverter(
            folder_path=str(paths["spikeglx_source_folder"]),
            one=one,
            eid=eid,
            pname_pid_map=pname_pid_map,
            revision=revision,
        )
        data_interfaces.append(spikeglx_converter)
    elif logger:
        logger.info("Stub test mode active: skipping SpikeGLX converter setup")

    # Anatomical localization
    if pname_pid_map:
        anat_interface = IblAnatomicalLocalizationInterface(
            one=one,
            eid=eid,
            pname_pid_map=pname_pid_map,
            revision=revision,
        )
        data_interfaces.append(anat_interface)
        if not include_ecephys and logger:
            logger.info("Stub mode active: using metadata-only electrodes for anatomical localization")

    # Raw video interfaces (skip in stub mode to avoid large downloads)
    if not stub_test:
        metadata_retrieval = BrainwideMapConverter(one=one, session=eid, data_interfaces=[], verbose=False)
        subject_id = metadata_retrieval.get_metadata()["Subject"]["subject_id"]

        pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
        for pose_estimation_file in pose_estimation_files:
            camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
            video_interface = RawVideoInterface(
                nwbfiles_folder_path=base_path,
                subject_id=subject_id,
                one=one,
                session=eid,
                camera_name=camera_name,
            )
            data_interfaces.append(video_interface)
    elif logger:
        logger.info("Stub test mode active: skipping raw video interfaces")

    interface_creation_time = time.time() - interface_creation_start
    if logger:
        logger.info(f"Data interfaces created in {interface_creation_time:.2f}s")

    # ========================================================================
    # STEP 3: Create converter
    # ========================================================================
    converter = ConverterPipe(data_interfaces=data_interfaces)

    # ========================================================================
    # STEP 4: Get metadata
    # ========================================================================
    metadata = converter.get_metadata()
    nwbfile_metadata = metadata.setdefault("NWBFile", {})
    subject_metadata_block = metadata.setdefault("Subject", {})

    # Add IBL-specific metadata
    (session_metadata,) = one.alyx.rest(url="sessions", action="list", id=eid)
    (lab_metadata,) = one.alyx.rest("labs", "list", name=session_metadata["lab"])

    # Session metadata
    session_start_time = datetime.fromisoformat(session_metadata["start_time"])
    tzinfo = ZoneInfo(lab_metadata["timezone"])
    session_start_time = session_start_time.replace(tzinfo=tzinfo)

    nwbfile_metadata["session_start_time"] = session_start_time
    nwbfile_metadata["session_id"] = session_metadata["id"]
    nwbfile_metadata["lab"] = lab_metadata.get("name", session_metadata["lab"])
    nwbfile_metadata["institution"] = lab_metadata.get("institution")
    if session_metadata.get("task_protocol"):
        nwbfile_metadata["protocol"] = session_metadata["task_protocol"]

    # Subject metadata
    subject_metadata_list = one.alyx.rest("subjects", "list", nickname=session_metadata["subject"])
    subject_metadata = subject_metadata_list[0]

    subject_metadata_block["subject_id"] = subject_metadata["nickname"]
    subject_metadata_block["sex"] = subject_metadata["sex"]
    subject_metadata_block["species"] = subject_metadata_block.get("species", "Mus musculus")
    if subject_metadata.get("reference_weight"):
        subject_metadata_block["weight"] = subject_metadata["reference_weight"] * 1e-3
    date_of_birth = datetime.strptime(subject_metadata["birth_date"], "%Y-%m-%d")
    subject_metadata_block["date_of_birth"] = date_of_birth.replace(tzinfo=tzinfo)

    for ibl_key, nwb_name in [
        ("last_water_restriction", "last_water_restriction"),
        ("remaining_water", "remaining_water_ml"),
        ("expected_water", "expected_water_ml"),
        ("url", "url"),
    ]:
        if ibl_key in subject_metadata and subject_metadata[ibl_key] is not None:
            subject_metadata_block[nwb_name] = subject_metadata[ibl_key]

    # ========================================================================
    # STEP 5: Configure conversion options
    # ========================================================================
    conversion_options = {}

    # Apply stub_test to SpikeGLX interfaces and enable progress bars
    if include_ecephys and spikeglx_converter is not None:
        spikeglx_options = {}
        for interface_name in spikeglx_converter.data_interface_objects.keys():
            spikeglx_options[interface_name] = {
                "stub_test": stub_test,
                "iterator_opts": {
                    "display_progress": True,
                    "progress_bar_options": {"desc": f"Writing {interface_name}"},
                },
            }
        conversion_options["IblSpikeGlxConverter"] = spikeglx_options

    # ========================================================================
    # STEP 6: Create NWBFile and add data
    # ========================================================================
    if logger:
        logger.info("Creating NWBFile and adding data...")
    conversion_start = time.time()

    subject_metadata_for_ndx = metadata.pop("Subject")
    ibl_subject = IblSubject(**subject_metadata_for_ndx)

    nwbfile = NWBFile(**metadata["NWBFile"])
    nwbfile.subject = ibl_subject
    nwbfile.add_lab_meta_data(lab_meta_data=ibl_bwm_metadata(revision=revision))

    if not include_ecephys:
        if logger:
            logger.info("Adding Neuropixels electrodes from metadata (stub mode)...")
        for probe_name, pid in pname_pid_map.items():
            add_probe_electrodes_with_localization(
                nwbfile=nwbfile,
                one=one,
                eid=eid,
                probe_name=probe_name,
                pid=pid,
                revision=revision,
            )

    # Add data from all interfaces
    for interface_name, data_interface in converter.data_interface_objects.items():
        interface_conversion_options = conversion_options.get(interface_name, {})
        data_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, **interface_conversion_options)

    conversion_time = time.time() - conversion_start
    if logger:
        logger.info(f"Data conversion completed in {conversion_time:.2f}s")

    # ========================================================================
    # STEP 7: Write NWB file
    # ========================================================================
    if logger:
        logger.info("Writing NWB file...")
    write_start = time.time()

    subject_id = nwbfile.subject.subject_id
    output_dir = Path(paths["output_folder"]) / ("stub" if stub_test else "full")
    output_dir.mkdir(parents=True, exist_ok=True)
    nwbfile_path = output_dir / f"sub-{subject_id}_ses-{eid}_desc-raw_ecephys.nwb"

    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend="hdf5",
    )

    write_time = time.time() - write_start

    # Get NWB file size
    nwb_size_bytes = nwbfile_path.stat().st_size
    nwb_size_gb = nwb_size_bytes / (1024**3)

    if logger:
        logger.info(f"NWB file written in {write_time:.2f}s")
        logger.info(f"RAW NWB file size: {nwb_size_gb:.2f} GB ({nwb_size_bytes:,} bytes)")
        logger.info(f"Write speed: {nwb_size_gb / (write_time / 3600):.2f} GB/hour")
        logger.info(f"RAW conversion total time: {time.time() - start_time:.2f}s")
        logger.info(f"RAW conversion completed: {nwbfile_path}")

    return {
        "nwbfile_path": nwbfile_path,
        "nwb_size_bytes": nwb_size_bytes,
        "nwb_size_gb": nwb_size_gb,
        "write_time": write_time,
    }


def convert_processed_session(
    eid: str,
    one: ONE,
    stub_test: bool = False,
    revision: str = None,
    base_path: Path = None,
    scratch_path: Path = None,
    skip_spike_properties: list = None,
    logger: logging.Logger = None,
):
    """Convert IBL processed session to NWB.

    Parameters
    ----------
    eid : str
        Session experiment ID
    one : ONE
        ONE API instance
    stub_test : bool, optional
        Use stub mode for testing
    revision : str, optional
        Data revision
    base_path : Path, optional
        Base path for output files
    skip_spike_properties : list, optional
        List of spike properties to skip
    logger : logging.Logger, optional
        Logger instance
    """

    if logger:
        logger.info(f"Starting PROCESSED conversion for session {eid}")

    # Setup paths
    start_time = time.time()
    paths = setup_paths(one, eid, base_path=base_path, scratch_path=scratch_path)
    if logger:
        logger.info(f"Paths setup completed in {time.time() - start_time:.2f}s")

    # Get probe insertion IDs
    insertions = one.alyx.rest("insertions", "list", session=eid)
    pname_pid_map = {ins["name"]: ins["id"] for ins in insertions}

    # ========================================================================
    # STEP 1: Define data interfaces
    # ========================================================================
    if logger:
        logger.info("Creating data interfaces...")
    interface_creation_start = time.time()

    data_interfaces = []
    interface_kwargs = dict(one=one, session=eid, revision=revision)

    # Spike sorting
    sorting_interface = IblSortingInterface(**interface_kwargs)
    data_interfaces.append(sorting_interface)

    # Anatomical localization
    if pname_pid_map:
        anat_interface = IblAnatomicalLocalizationInterface(
            one=one,
            eid=eid,
            pname_pid_map=pname_pid_map,
            revision=revision,
        )
        data_interfaces.append(anat_interface)

    # Behavioral data
    data_interfaces.append(BrainwideMapTrialsInterface(**interface_kwargs))
    data_interfaces.append(WheelInterface(**interface_kwargs))
    data_interfaces.append(PassivePeriodDataInterface(**interface_kwargs))

    # Licks
    if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
        data_interfaces.append(LickInterface(**interface_kwargs))

    # Video interfaces - pose estimation
    bwm_qc = load_fixtures.load_bwm_qc()
    pose_estimation_files = set([Path(f).name for f in one.list_datasets(eid=eid, filename="*.dlc*")])
    for pose_estimation_file in pose_estimation_files:
        camera_name = get_camera_name_from_file(pose_estimation_file)
        if stub_test or (check_camera_health_by_qc(bwm_qc, eid, camera_name) and check_camera_health_by_loading(**interface_kwargs)):
            data_interfaces.append(IblPoseEstimationInterface(camera_name=camera_name, tracker='lightningPose', **interface_kwargs))

    # Pupil tracking
    pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
    camera_names = set([get_camera_name_from_file(f) for f in pupil_tracking_files])
    for camera_name in camera_names:
        if stub_test or check_camera_health_by_qc(bwm_qc, eid, camera_name):
            data_interfaces.append(PupilTrackingInterface(camera_name=camera_name, **interface_kwargs))

    # ROI motion energy
    roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
    camera_names = set([get_camera_name_from_file(f) for f in roi_motion_energy_files])
    for camera_name in camera_names:
        if stub_test or check_camera_health_by_qc(bwm_qc, eid, camera_name):
            data_interfaces.append(RoiMotionEnergyInterface(camera_name=camera_name, **interface_kwargs))

    interface_creation_time = time.time() - interface_creation_start
    if logger:
        logger.info(f"Data interfaces created in {interface_creation_time:.2f}s")

    # ========================================================================
    # STEP 2: Create converter
    # ========================================================================
    converter = ConverterPipe(data_interfaces=data_interfaces)

    # ========================================================================
    # STEP 3: Get metadata
    # ========================================================================
    metadata = converter.get_metadata()
    nwbfile_metadata = metadata.setdefault("NWBFile", {})
    subject_metadata_block = metadata.setdefault("Subject", {})

    # Add IBL-specific metadata
    (session_metadata,) = one.alyx.rest(url="sessions", action="list", id=eid)
    (lab_metadata,) = one.alyx.rest("labs", "list", name=session_metadata["lab"])

    # Session metadata
    session_start_time = datetime.fromisoformat(session_metadata["start_time"])
    tzinfo = ZoneInfo(lab_metadata["timezone"])
    session_start_time = session_start_time.replace(tzinfo=tzinfo)

    nwbfile_metadata["session_start_time"] = session_start_time
    nwbfile_metadata["session_id"] = session_metadata["id"]
    nwbfile_metadata["lab"] = lab_metadata.get("name", session_metadata["lab"])
    nwbfile_metadata["institution"] = lab_metadata.get("institution")
    if session_metadata.get("task_protocol"):
        nwbfile_metadata["protocol"] = session_metadata["task_protocol"]

    # Subject metadata
    subject_metadata_list = one.alyx.rest("subjects", "list", nickname=session_metadata["subject"])
    subject_metadata = subject_metadata_list[0]

    subject_metadata_block["subject_id"] = subject_metadata["nickname"]
    subject_metadata_block["sex"] = subject_metadata["sex"]
    subject_metadata_block["species"] = subject_metadata_block.get("species", "Mus musculus")
    if subject_metadata.get("reference_weight"):
        subject_metadata_block["weight"] = subject_metadata["reference_weight"] * 1e-3
    date_of_birth = datetime.strptime(subject_metadata["birth_date"], "%Y-%m-%d")
    subject_metadata_block["date_of_birth"] = date_of_birth.replace(tzinfo=tzinfo)

    for ibl_key, nwb_name in [
        ("last_water_restriction", "last_water_restriction"),
        ("remaining_water", "remaining_water_ml"),
        ("expected_water", "expected_water_ml"),
        ("url", "url"),
    ]:
        if ibl_key in subject_metadata and subject_metadata[ibl_key] is not None:
            subject_metadata_block[nwb_name] = subject_metadata[ibl_key]

    # ========================================================================
    # STEP 4: Configure conversion options
    # ========================================================================
    conversion_options = {}

    # Sorting interface options
    sorting_options = {"stub_test": stub_test}
    if skip_spike_properties and stub_test:
        sorting_options["skip_properties"] = skip_spike_properties
    conversion_options["IblSortingInterface"] = sorting_options

    # Trials interface options
    conversion_options["BrainwideMapTrialsInterface"] = {
        "stub_test": stub_test,
    }

    # Wheel interface options
    conversion_options["WheelInterface"] = {
        "stub_test": stub_test,
    }

    # ========================================================================
    # STEP 5: Create NWBFile and add data
    # ========================================================================
    if logger:
        logger.info("Creating NWBFile and adding data (converting)...")
    conversion_start = time.time()

    subject_metadata_for_ndx = metadata.pop("Subject")
    ibl_subject = IblSubject(**subject_metadata_for_ndx)

    nwbfile = NWBFile(**metadata["NWBFile"])
    nwbfile.subject = ibl_subject
    nwbfile.add_lab_meta_data(lab_meta_data=ibl_bwm_metadata(revision=revision))

    for probe_name, pid in pname_pid_map.items():
        add_probe_electrodes_with_localization(
            nwbfile=nwbfile,
            one=one,
            eid=eid,
            probe_name=probe_name,
            pid=pid,
            revision=revision,
        )

    # Add data from all interfaces
    for interface_name, data_interface in converter.data_interface_objects.items():
        interface_conversion_options = conversion_options.get(interface_name, {})
        data_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, **interface_conversion_options)

    conversion_time = time.time() - conversion_start
    if logger:
        logger.info(f"Conversion completed in {conversion_time:.2f}s")

    # ========================================================================
    # STEP 6: Write NWB file
    # ========================================================================
    if logger:
        logger.info("Writing NWB file...")
    write_start = time.time()

    subject_id = nwbfile.subject.subject_id
    output_dir = Path(paths["output_folder"]) / ("stub" if stub_test else "full")
    output_dir.mkdir(parents=True, exist_ok=True)
    nwbfile_path = output_dir / f"sub-{subject_id}_ses-{eid}_desc-processed_behavior+ecephys.nwb"

    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend="hdf5",
    )

    write_time = time.time() - write_start

    # Get NWB file size
    nwb_size_bytes = nwbfile_path.stat().st_size
    nwb_size_gb = nwb_size_bytes / (1024**3)

    if logger:
        logger.info(f"NWB file written in {write_time:.2f}s")
        logger.info(f"PROCESSED NWB file size: {nwb_size_gb:.2f} GB ({nwb_size_bytes:,} bytes)")
        logger.info(f"Write speed: {nwb_size_gb / (write_time / 3600):.2f} GB/hour")
        logger.info(f"PROCESSED conversion total time: {time.time() - start_time:.2f}s")
        logger.info(f"PROCESSED conversion completed: {nwbfile_path}")

    return {
        "nwbfile_path": nwbfile_path,
        "nwb_size_bytes": nwb_size_bytes,
        "nwb_size_gb": nwb_size_gb,
        "write_time": write_time,
    }


def cleanup_decompressed_files(eid: str, scratch_path: Path):
    """Remove decompressed .bin files for this session from scratch folder.

    This removes the temporary decompressed files but preserves the original
    downloaded .cbin files in the cache directory.
    """
    session_scratch = scratch_path / eid / "raw_ephys_data"
    if session_scratch.exists():
        shutil.rmtree(session_scratch)


def cleanup_downloaded_files(eid: str, one: ONE):
    """CAUTION: Remove downloaded .cbin files for this session.

    This permanently deletes the original downloaded files from the cache.
    Use with extreme caution - you will need to re-download if needed again.
    """
    # Find all datasets for this session
    datasets = one.list_datasets(eid=eid)
    files_to_delete = []

    for dataset in datasets:
        file_path = one.eid2path(eid) / dataset
        if file_path.exists():
            files_to_delete.append(file_path)

    if files_to_delete:
        for file_path in files_to_delete:
            file_path.unlink()

        # Clean up empty directories
        session_dir = one.eid2path(eid)
        if session_dir.exists() and not any(session_dir.iterdir()):
            session_dir.rmdir()


def get_eid_from_index_or_eid(session_identifier):
    """Get EID from either an index (0-458) or an EID string.

    Parameters
    ----------
    session_identifier : int or str
        Either an index into the BWM sessions list (0-458) or an EID string

    Returns
    -------
    str
        The EID (session UUID)
    """
    if isinstance(session_identifier, int):
        # Load BWM dataframe and get unique sessions
        bwm_df = load_fixtures.load_bwm_df()
        unique_sessions = bwm_df.drop_duplicates('eid').reset_index(drop=True)

        if session_identifier < 0 or session_identifier >= len(unique_sessions):
            raise ValueError(f"Index {session_identifier} out of range. Valid range: 0-{len(unique_sessions)-1}")

        return unique_sessions.iloc[session_identifier]['eid']
    else:
        # Assume it's already an EID string
        return session_identifier


if __name__ == "__main__":
    # ========================================================================
    # MAIN CONFIGURATION
    # ========================================================================

    # Conversion options
    CONVERT_RAW = True
    CONVERT_PROCESSED = True
    STUB_TEST = True          # Use stub mode for faster testing (subset of data)
    REDOWNLOAD_DATA = False   # If True, always re-download; if False, use cached data when available
    CLEANUP_DECOMPRESSED = False  # Remove decompressed .bin files after conversion
    CLEANUP_DOWNLOADED = False    # CAUTION: Remove downloaded .cbin files (NOT recommended)

    # Paths - using /media/heberto/Expansion as base
    base_folder = Path("/media/heberto/Expansion")
    cache_dir = base_folder / "ibl_data"
    base_path = base_folder  # setup_paths() will add "nwbfiles" subdirectory
    scratch_path = base_folder / "temporary_files"

    # Session to convert - Either:
    # - An EID string: "fece187f-b47f-4870-a1d6-619afe942a7d"
    # - An index (0-458): 0, 1, 2, etc.
    session_identifier = "fece187f-b47f-4870-a1d6-619afe942a7d"  # Or use an integer index
    revision = "2024-05-06"

    # Initialize ONE
    one = ONE(base_url="https://openalyx.internationalbrainlab.org", cache_dir=cache_dir, silent=True)

    # Load all BWM sessions
    bwm_df = load_fixtures.load_bwm_df()
    unique_sessions = bwm_df.drop_duplicates('eid').reset_index(drop=True)
    all_eids = unique_sessions['eid'].tolist()

    print(f"Total sessions to process: {len(all_eids)}")

    # Loop through all sessions
    for session_idx, eid in enumerate(all_eids):
        print(f"\nProcessing session {session_idx + 1}/{len(all_eids)}: {eid}")

        # Setup logging for this session
        log_file_path = scratch_path / f"conversion_log_{eid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logger = setup_logger(log_file_path)
        logger.info("="*80)
        logger.info(f"IBL CONVERSION SCRIPT STARTED")
        logger.info(f"Session {session_idx + 1}/{len(all_eids)}")
        logger.info(f"Session ID: {eid}")
        logger.info(f"Revision: {revision}")
        logger.info(f"Convert RAW: {CONVERT_RAW}")
        logger.info(f"Convert PROCESSED: {CONVERT_PROCESSED}")
        logger.info(f"Stub test mode: {STUB_TEST}")
        logger.info(f"Re-download data: {REDOWNLOAD_DATA}")
        logger.info(f"Log file: {log_file_path}")
        logger.info("="*80)

        # ========================================================================
        # DOWNLOAD SESSION DATA
        # ========================================================================

        script_start_time = time.time()

        # Download all data first (shared between raw and processed)
        logger.info("\n" + "="*80)
        logger.info("DOWNLOADING SESSION DATA")
        logger.info("="*80)
        download_info = download_session_data(
            eid=eid,
            one=one,
            redownload_data=REDOWNLOAD_DATA,
            stub_test=STUB_TEST,
            revision=revision,
            base_path=base_path,
            scratch_path=scratch_path,
            logger=logger,
        )

        # ========================================================================
        # RUN CONVERSIONS
        # ========================================================================

        raw_info = None
        processed_info = None

        # Convert raw session
        if CONVERT_RAW:
            logger.info("\n" + "="*80)
            logger.info("STARTING RAW CONVERSION")
            logger.info("="*80)
            raw_info = convert_raw_session(
                eid=eid,
                one=one,
                stub_test=STUB_TEST,
                revision=revision,
                base_path=base_path,
                scratch_path=scratch_path,
                logger=logger,
            )

        # Convert processed session
        if CONVERT_PROCESSED:
            logger.info("\n" + "="*80)
            logger.info("STARTING PROCESSED CONVERSION")
            logger.info("="*80)
            processed_info = convert_processed_session(
                eid=eid,
                one=one,
                stub_test=STUB_TEST,
                revision=revision,
                base_path=base_path,
                scratch_path=scratch_path,
                skip_spike_properties=["spike_amplitudes", "spike_relative_depths"],
                logger=logger,
            )

        # ========================================================================
        # COMPRESSION SUMMARY
        # ========================================================================

        logger.info("\n" + "="*80)
        logger.info("COMPRESSION SUMMARY")
        logger.info("="*80)
        logger.info(f"Source data size: {download_info['total_size_gb']:.2f} GB ({download_info['total_size_bytes']:,} bytes)")

        if raw_info:
            compression_ratio_raw = download_info['total_size_gb'] / raw_info['nwb_size_gb'] if raw_info['nwb_size_gb'] > 0 else 0
            logger.info(f"RAW NWB size: {raw_info['nwb_size_gb']:.2f} GB ({raw_info['nwb_size_bytes']:,} bytes)")
            logger.info(f"RAW compression ratio: {compression_ratio_raw:.2f}x (source/output)")

        if processed_info:
            compression_ratio_processed = download_info['total_size_gb'] / processed_info['nwb_size_gb'] if processed_info['nwb_size_gb'] > 0 else 0
            logger.info(f"PROCESSED NWB size: {processed_info['nwb_size_gb']:.2f} GB ({processed_info['nwb_size_bytes']:,} bytes)")
            logger.info(f"PROCESSED compression ratio: {compression_ratio_processed:.2f}x (source/output)")

        if raw_info and processed_info:
            total_nwb_size_gb = raw_info['nwb_size_gb'] + processed_info['nwb_size_gb']
            total_nwb_size_bytes = raw_info['nwb_size_bytes'] + processed_info['nwb_size_bytes']
            overall_compression = download_info['total_size_gb'] / total_nwb_size_gb if total_nwb_size_gb > 0 else 0
            logger.info(f"Total NWB output: {total_nwb_size_gb:.2f} GB ({total_nwb_size_bytes:,} bytes)")
            logger.info(f"Overall compression ratio: {overall_compression:.2f}x (source/combined output)")

        # ========================================================================
        # CLEANUP
        # ========================================================================

        if CLEANUP_DECOMPRESSED:
            logger.info("\n" + "="*80)
            logger.info("CLEANING UP DECOMPRESSED FILES")
            logger.info("="*80)
            cleanup_decompressed_files(eid, scratch_path)
            logger.info("Decompressed files cleaned up")

        if CLEANUP_DOWNLOADED:
            logger.info("\n" + "="*80)
            logger.info("CLEANING UP DOWNLOADED FILES (CAUTION)")
            logger.info("="*80)
            cleanup_downloaded_files(eid, one)
            logger.info("Downloaded files cleaned up")

        # ========================================================================
        # FINAL SUMMARY
        # ========================================================================
        script_total_time = time.time() - script_start_time
        logger.info("\n" + "="*80)
        logger.info("CONVERSION COMPLETED")
        logger.info(f"Total script execution time: {script_total_time:.2f}s ({script_total_time/60:.2f} minutes)")
        logger.info("="*80)

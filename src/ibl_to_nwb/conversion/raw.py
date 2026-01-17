from __future__ import annotations

import logging
import shutil
import time
import warnings
from datetime import datetime
from pathlib import Path

from zoneinfo import ZoneInfo

from neuroconv import ConverterPipe
from neuroconv.tools import configure_and_write_nwbfile
from neuroconv.tools.hdmf import GenericDataChunkIterator
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from ndx_ibl import IblMetadata, IblSubject
from one.api import ONE
from one import alf
from pynwb import NWBFile, read_nwb

from ..converters import BrainwideMapConverter, IblSpikeGlxConverter
from ..datainterfaces import IblAnatomicalLocalizationInterface, IblNIDQInterface, RawVideoInterface, SessionEpochsInterface
from ..fixtures import load_fixtures
from ..utils import (
    add_probe_electrodes_with_localization,
    check_camera_health_by_qc,
    decompress_ephys_cbins,
    get_ibl_subject_metadata,
    sanitize_subject_id_for_dandi,
    setup_paths,
    tree_copy,
)


def _valid_existing_nwb(nwb_path: Path, overwrite: bool, logger: logging.Logger | None = None) -> bool:
    if overwrite or not nwb_path.exists():
        return False

    try:
        read_nwb(str(nwb_path))
    except Exception as exc:
        if logger:
            logger.warning(
                "Existing NWB at %s failed validation (reason: %s); regenerating.",
                nwb_path,
                exc,
            )
        return False

    if logger:
        logger.info("Skipping conversion because %s already exists and is readable.", nwb_path)
    return True


def convert_raw_session(
    eid: str,
    one: ONE,
    stub_test: bool = False,
    base_path: Path | None = None,
    logger: logging.Logger | None = None,
    overwrite: bool = False,
    redecompress_ephys: bool = False,
) -> dict:
    """Convert IBL raw session to NWB.

    In stub mode, ephys data is automatically included if decompressed binaries
    are already available (similar to how videos are auto-included if cached).

    Parameters
    ----------
    eid : str
        Experiment ID (session UUID)
    one : ONE
        ONE API instance
    stub_test : bool, optional
        If True, creates minimal NWB for testing without downloading large files.
        Ephys and videos are auto-included if already available locally.
    base_path : Path, optional
        Base output directory for NWB files. The decompressed ephys path will be
        derived from this base path as base_path/decompressed_ephys.
    logger : logging.Logger, optional
        Logger instance for conversion progress
    overwrite : bool, optional
        If True, overwrite existing NWB files
    redecompress_ephys : bool, optional
        If True, force re-decompression of ephys data even if already decompressed

    Returns
    -------
    dict
        Conversion result information including NWB file path and timing
    """

    # ========================================================================
    # SUPPRESS HARMLESS WARNINGS
    # ========================================================================
    # Suppress SpikeGLX geometry warnings
    # These occur when .meta files lack snsShankMap/snsGeomMap fields (common for LF and NIDQ)
    # The default Neuropixel geometry is correctly used - these warnings are cosmetic
    warnings.filterwarnings(
        "ignore",
        message="Meta data doesn't have geometry.*returning defaults",
        category=UserWarning,
        module="spikeglx"
    )

    # Suppress ONE API ALFWarning about multiple revisions
    # Camera data often has mixed revisions (empty string "" and dated revisions like "2023-04-20")
    # This happens when some files were re-processed but not all - the ONE API handles this correctly
    # by selecting the appropriate revision, so the warning is informational only
    warnings.filterwarnings(
        "ignore",
        message="Multiple revisions:.*",
        category=alf.exceptions.ALFWarning
    )

    if logger:
        logger.info(f"Starting RAW conversion for session {eid}")

    # Setup paths (decompressed_ephys_path is derived internally from base_path)
    start_time = time.time()
    paths = setup_paths(one, eid, base_path=base_path)
    if logger:
        logger.info(f"Paths setup completed in {time.time() - start_time:.2f}s")

    session_info = one.alyx.rest("sessions", "read", id=eid)
    subject_nickname = session_info.get("subject")
    if isinstance(subject_nickname, dict):
        subject_nickname = subject_nickname.get("nickname") or subject_nickname.get("name")
    if not subject_nickname:
        subject_nickname = "unknown"

    # New structure: nwbfiles/{full|stub}/sub-{subject}/*.nwb
    conversion_type = "stub" if stub_test else "full"
    # Sanitize subject nickname for DANDI compliance (replace underscores with hyphens)
    subject_id_for_filenames = sanitize_subject_id_for_dandi(subject_nickname)
    output_dir = Path(paths["output_folder"]) / conversion_type / f"sub-{subject_id_for_filenames}"
    output_dir.mkdir(parents=True, exist_ok=True)
    provisional_nwbfile_path = output_dir / f"sub-{subject_id_for_filenames}_ses-{eid}_desc-raw_ecephys.nwb"

    if _valid_existing_nwb(provisional_nwbfile_path, overwrite=overwrite, logger=logger):
        size_bytes = provisional_nwbfile_path.stat().st_size
        size_gb = size_bytes / (1024**3)
        return {
            "nwbfile_path": provisional_nwbfile_path,
            "nwb_size_bytes": size_bytes,
            "nwb_size_gb": size_gb,
            "write_time": 0.0,
            "skipped": True,
        }

    # Get probe insertion IDs (fast lookup from histology QC table)
    # NO fallback - if fixture is missing, installation is broken
    probe_name_to_probe_id_dict = load_fixtures.get_probe_name_to_probe_id_dict(eid)

    # Log probe information
    if logger:
        if len(probe_name_to_probe_id_dict) == 0:
            logger.warning("No probe insertions found for session %s", eid)
        elif len(probe_name_to_probe_id_dict) == 1:
            probe_name = list(probe_name_to_probe_id_dict.keys())[0]
            logger.info("Single-probe session detected: %s", probe_name)
        else:
            logger.info(
                "Multi-probe session detected: %d probes (%s)",
                len(probe_name_to_probe_id_dict),
                ", ".join(probe_name_to_probe_id_dict.keys()),
            )

    scratch_ephys_folder = paths["session_decompressed_ephys_folder"] / "raw_ephys_data"
    existing_bins = (
        scratch_ephys_folder.exists() and next(scratch_ephys_folder.rglob("*.bin"), None) is not None
    )

    # In stub mode: auto-include ephys if decompressed binaries are available
    # In full mode: always include ephys (will decompress if needed)
    if stub_test:
        include_ecephys = existing_bins and not redecompress_ephys
        if not include_ecephys and logger:
            logger.info(
                "Stub mode: No decompressed Neuropixels binaries found in %s; "
                "skipping SpikeGLX interfaces. Run a full conversion first to decompress data, "
                "or set REDECOMPRESS_EPHYS=True to force decompression in stub mode.",
                scratch_ephys_folder,
            )
    else:
        include_ecephys = True

    # ========================================================================
    # STEP 1: Decompress raw ephys data
    # ========================================================================
    if include_ecephys:
        if logger:
            logger.info("Preparing raw ephys data on scratch...")
        decompress_start = time.time()

        bins_available = existing_bins

        if scratch_ephys_folder.exists() and redecompress_ephys:
            if logger:
                logger.info(
                    "REDECOMPRESS_EPHYS is True - removing existing decompressed data at %s",
                    scratch_ephys_folder,
                )
            shutil.rmtree(scratch_ephys_folder)
            scratch_ephys_folder.mkdir(parents=True, exist_ok=True)
            bins_available = False

        if bins_available:
            if logger:
                logger.info(
                    "Reusing existing decompressed Neuropixels data from %s (set REDECOMPRESS_EPHYS=True to refresh).",
                    scratch_ephys_folder,
                )
        else:
            if logger:
                logger.info("Decompressing .cbin files...")
            decompress_ephys_cbins(paths["session_folder"], paths["session_decompressed_ephys_folder"])
            bins_available = True

        # Note: Metadata files (.meta, .ch) are automatically copied alongside .bin files
        # by spikeglx.Reader.decompress_to_scratch() during decompression above

        decompress_time = time.time() - decompress_start
        if logger:
            logger.info(f"Scratch data preparation completed in {decompress_time:.2f}s")
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
        # Clean up macOS hidden files before Neo scans directory
        # This prevents Neo's scan_files() from encountering ._* AppleDouble files
        if bins_available and paths["session_decompressed_ephys_folder"].exists():
            import platform
            if platform.system() == "Darwin":
                for hidden_file in paths["session_decompressed_ephys_folder"].rglob("._*"):
                    hidden_file.unlink()
                if logger:
                    logger.debug("Removed macOS hidden files from scratch folder")

        # SpikeGLX converter
        if logger and stub_test:
            logger.info("✓ Stub mode: Including SpikeGLX ephys data (decompressed binaries available)")
        spikeglx_converter = IblSpikeGlxConverter(
            folder_path=paths["spikeglx_source_folder"],
            one=one,
            eid=eid,
            probe_name_to_probe_id_dict=probe_name_to_probe_id_dict,
        )
        data_interfaces.append(spikeglx_converter)

        # Add NIDQ interface if available (behavioral sync signals)
        # NIDQ is stored at session level (raw_ephys_data folder)
        if IblNIDQInterface.check_availability(one, eid)["available"]:
            nidq_interface = IblNIDQInterface(
                folder_path=str(paths["spikeglx_source_folder"]),
                one=one,
                eid=eid,
                verbose=False,
            )
            data_interfaces.append(nidq_interface)
            if logger:
                logger.info("✓ NIDQ interface added (behavioral sync signals)")
        else:
            if logger:
                logger.warning(f"NIDQ data not available for session {eid} - skipping NIDQ interface")
    elif logger:
        if not stub_test:
            logger.info("SpikeGLX data not available: skipping SpikeGLX converter setup (see message above for details)")

    # Anatomical localization (loads probe info and histology QC internally)
    anat_interface = IblAnatomicalLocalizationInterface(one=one, eid=eid)
    if anat_interface.probe_name_to_probe_id_dict:  # Only add if has probes with good histology
        data_interfaces.append(anat_interface)
        if not include_ecephys and logger:
            logger.info("Stub mode active: using metadata-only electrodes for anatomical localization")

    # Session epochs (high-level task vs passive phases)
    if SessionEpochsInterface.check_availability(one, eid)["available"]:
        session_epochs_interface = SessionEpochsInterface(one=one, session=eid)
        data_interfaces.append(session_epochs_interface)
        if logger:
            logger.info("✓ Session epochs interface added (task and passive phases)")

    # Raw video interfaces
    # In stub mode, only include videos if already downloaded (avoid triggering large downloads)
    # In full mode, always include videos (they will be downloaded if needed)
    metadata_retrieval = BrainwideMapConverter(one=one, session=eid, data_interfaces=[], verbose=False)
    subject_id_from_metadata = metadata_retrieval.get_metadata()["Subject"]["subject_id"]
    # Sanitize subject ID for DANDI-compliant filenames
    subject_id_for_video_paths = sanitize_subject_id_for_dandi(subject_id_from_metadata)

    # Video files should be organized alongside NWB files
    # In stub mode: nwbfiles/stub/sub-{subject}/, in full mode: nwbfiles/full/sub-{subject}/
    conversion_mode = "stub" if stub_test else "full"
    video_base_path = Path(paths["output_folder"]) / conversion_mode

    # Add video interfaces for cameras that have timestamps
    # Check all camera types (left, right, body)
    for camera_view in ["left", "right", "body"]:
        camera_times_pattern = f"*{camera_view}Camera.times*"
        video_filename = f"raw_video_data/_iblrig_{camera_view}Camera.raw.mp4"

        # Check if camera has timestamps (required for video interface)
        has_timestamps = bool(one.list_datasets(eid=eid, filename=camera_times_pattern))
        if not has_timestamps:
            continue

        # Check if video dataset exists
        has_video = bool(one.list_datasets(eid=eid, filename=video_filename))
        if not has_video:
            if logger:
                logger.debug(f"No video file found for {camera_view}Camera - skipping")
            continue

        # In stub mode, check if video is already in cache (avoid triggering downloads)
        if stub_test:
            # Check cache without downloading - construct expected path from eid2path
            session_path = one.eid2path(eid)
            if session_path is None:
                # Session path not in cache, skip video
                if logger:
                    logger.info(f"✗ Stub mode: {camera_view}Camera video not in cache - skipping to avoid download")
                continue

            expected_video_path = session_path / video_filename
            video_in_cache = expected_video_path.exists()

            if not video_in_cache:
                if logger:
                    logger.info(f"✗ Stub mode: {camera_view}Camera video not in cache - skipping to avoid download")
                continue

            if logger:
                logger.info(f"✓ Stub mode: Including {camera_view}Camera video (already in cache)")
        else:
            if logger:
                logger.info(f"Adding {camera_view}Camera video interface")

        # Add video interface
        video_interface = RawVideoInterface(
            nwbfiles_folder_path=video_base_path,
            subject_id=subject_id_for_video_paths,
            one=one,
            session=eid,
            camera_name=camera_view,
        )
        data_interfaces.append(video_interface)

    interface_creation_time = time.time() - interface_creation_start
    if logger:
        logger.info(f"Data interfaces created in {interface_creation_time:.2f}s")

        # Log data availability summary
        datasets = one.list_datasets(eid)
        dataset_strs = [str(d) for d in datasets]

        # Check key data sources
        has_lightning_left = any("leftCamera.lightningPose" in ds for ds in dataset_strs)
        has_lightning_right = any("rightCamera.lightningPose" in ds for ds in dataset_strs)
        has_dlc_left = any("leftCamera.dlc" in ds for ds in dataset_strs)
        has_dlc_right = any("rightCamera.dlc" in ds for ds in dataset_strs)
        has_video_body = any("bodyCamera.raw.mp4" in ds for ds in dataset_strs)

        logger.info("Data availability summary:")
        logger.info("  Pose estimation:")
        logger.info(f"    Lightning Pose (left): {'✓' if has_lightning_left else '✗'}")
        logger.info(f"    Lightning Pose (right): {'✓' if has_lightning_right else '✗'}")
        logger.info(f"    DLC (left): {'✓' if has_dlc_left else '✗'}")
        logger.info(f"    DLC (right): {'✓' if has_dlc_right else '✗'}")
        logger.info(f"  Body camera video: {'✓' if has_video_body else '✗'}")

        # Warn about missing key data
        missing = []
        if not has_lightning_left and not has_dlc_left:
            missing.append("left camera pose estimation")
        if not has_lightning_right and not has_dlc_right:
            missing.append("right camera pose estimation")

        if missing:
            logger.warning("Missing data sources: %s", ", ".join(missing))

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

    # Get subject metadata using centralized utility function
    subject_metadata_block.update(
        get_ibl_subject_metadata(one=one, session_metadata=session_metadata, tzinfo=tzinfo)
    )

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
                "iterator_options": {
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
    nwbfile.add_lab_meta_data(lab_meta_data=IblMetadata(revision="2025-05-06"))

    if probe_name_to_probe_id_dict:
        if logger:
            if include_ecephys:
                logger.info(
                    "Pre-populating electrode table from anatomical localization before SpikeGLX data."
                )
            else:
                logger.info("Adding Neuropixels electrodes from metadata (stub mode)...")
        for probe_name, pid in probe_name_to_probe_id_dict.items():
            # Resolve .meta file path from ONE cache (already downloaded, no query needed)
            meta_collection = f"raw_ephys_data/{probe_name}"
            meta_datasets = [d for d in one.list_datasets(eid=eid, collection=meta_collection) if d.endswith(".ap.meta")]
            meta_path = None
            if meta_datasets:
                # Get path from ONE cache (already cached locally)
                meta_path = one.eid2path(eid) / meta_datasets[0]

            add_probe_electrodes_with_localization(
                nwbfile=nwbfile,
                one=one,
                eid=eid,
                probe_name=probe_name,
                pid=pid,
                meta_path=meta_path,  # Explicit path to ONE cache - no fallback needed
            )

    # Add data from all interfaces
    for interface_name, data_interface in converter.data_interface_objects.items():
        interface_conversion_options = conversion_options.get(interface_name, {})
        data_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, **interface_conversion_options)

    conversion_time = time.time() - conversion_start
    if logger:
        logger.info(f"Data added to NWBFile object in {conversion_time:.2f}s")

    # ========================================================================
    # STEP 7: Write NWB file to disk
    # ========================================================================
    if logger:
        logger.info("Writing NWB file to disk...")
    write_start = time.time()

    # Use sanitized subject ID for filename (DANDI compliance)
    subject_id_for_filename = sanitize_subject_id_for_dandi(nwbfile.subject.subject_id)
    nwbfile_path = output_dir / f"sub-{subject_id_for_filename}_ses-{eid}_desc-raw_ecephys.nwb"

    # Get default backend configuration
    backend_configuration = get_default_backend_configuration(nwbfile=nwbfile, backend="hdf5")

    # Customize chunking for ElectricalSeries to not chunk across channels
    # This ensures all channels are in each chunk, which is better for channel-wise access patterns
    for location, dataset_config in backend_configuration.dataset_configurations.items():
        # Check if this is an ElectricalSeries data dataset
        if "ElectricalSeries" in location and location.endswith("/data"):
            # Get the full shape (frames, channels)
            full_shape = dataset_config.full_shape
            number_of_frames = full_shape[0]
            number_of_channels = full_shape[1]
            dtype = dataset_config.dtype

            # Calculate chunk size with ALL channels (no chunking across channels)
            # Adapted from neuroconv's get_electrical_series_chunk_shape but with all channels
            chunk_mb = 10.0
            bytes_per_frame = number_of_channels * dtype.itemsize
            chunk_frames = int((chunk_mb * 1e6) // bytes_per_frame)
            chunk_frames = max(1, min(chunk_frames, number_of_frames))
            chunk_shape = (chunk_frames, number_of_channels)

            # Use neuroconv's buffer shape estimation to ensure compatibility
            # This guarantees buffer_axis % chunk_axis == 0 (required by validation)
            buffer_gb = 1.0  # Default buffer size
            buffer_shape = GenericDataChunkIterator.estimate_default_buffer_shape(
                buffer_gb=buffer_gb,
                chunk_shape=chunk_shape,
                maxshape=full_shape,
                dtype=dtype
            )

            # Update both chunk_shape and buffer_shape atomically using model_copy
            # This avoids intermediate validation errors during assignment
            updated_config = dataset_config.model_copy(
                update={"chunk_shape": chunk_shape, "buffer_shape": buffer_shape}
            )
            # Replace the config in the backend_configuration dict
            backend_configuration.dataset_configurations[location] = updated_config
            dataset_config = updated_config  # Update local reference

            if logger:
                logger.info(f"  Custom chunking for {location}:")
                logger.info(f"    Shape: {full_shape}")
                logger.info(f"    Chunk: {dataset_config.chunk_shape}")
                logger.info(f"    Buffer: {dataset_config.buffer_shape}")
                chunk_size_mb = (chunk_frames * number_of_channels * dtype.itemsize) / 1e6
                logger.info(f"    Chunk size: {chunk_size_mb:.2f} MB")

    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend_configuration=backend_configuration,
    )

    write_time = time.time() - write_start

    # Get NWB file size
    nwb_size_bytes = nwbfile_path.stat().st_size
    nwb_size_gb = nwb_size_bytes / (1024**3)

    if logger:
        total_time_seconds = time.time() - start_time
        total_time_hours = total_time_seconds / 3600
        logger.info(f"NWB file written in {write_time:.2f}s")
        logger.info(f"RAW NWB file size: {nwb_size_gb:.2f} GB ({nwb_size_bytes:,} bytes)")
        logger.info(f"Write speed: {nwb_size_gb / (write_time / 3600):.2f} GB/hour")
        logger.info(f"RAW conversion total time: {total_time_seconds:.2f}s")
        logger.info(f"RAW conversion total time: {total_time_hours:.2f} hours")
        logger.info(f"RAW conversion completed: {nwbfile_path}")
        logger.info(f"RAW NWB saved to: {nwbfile_path}")

    return {
        "nwbfile_path": nwbfile_path,
        "nwb_size_bytes": nwb_size_bytes,
        "nwb_size_gb": nwb_size_gb,
        "write_time": write_time,
    }

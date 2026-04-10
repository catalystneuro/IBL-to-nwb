"""Standalone script to convert Neuropixels 2.0 raw ephys data to NWB.

This script handles the NP2.0-specific part of the conversion: multi-shank raw
ephys recordings where each shank is stored in a separate compressed file
(probe00a/, probe00b/, etc.).

For processed/behavioral data (trials, wheel, licks, pose, passive, units),
use convert_single_bwm_to_nwb.py once the session is registered on openalyx.
The behavioral data follows the standard IBL ALF format and works with the
normal convert_session() pipeline.

Data sources for RAW NWB:
- Raw ephys (AP and LF bands) via IblNeuropixels2Converter
- NIDQ behavioral sync signals
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.tools import configure_and_write_nwbfile
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from neuroconv.utils import dict_deep_update
from ndx_ibl import IblMetadata, IblSubject
from one.api import ONE
from pynwb import NWBFile, NWBHDF5IO

from ibl_to_nwb.converters import IblNeuropixels2Converter
from ibl_to_nwb.datainterfaces import IblNIDQInterface
from ibl_to_nwb.utils import decompress_ephys_cbins


def setup_logger(log_file_path: Path) -> logging.Logger:
    """Configure a logger that writes to disk and stdout."""

    logger = logging.getLogger("IBL_NP2_Conversion")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    logger.propagate = False  # Prevent duplicate logs from root logger

    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file_path, mode="a")
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    file_handler.stream.reconfigure(line_buffering=True)

    # Capture Python warnings in the logging system
    logging.captureWarnings(True)
    warnings_logger = logging.getLogger('py.warnings')
    warnings_logger.addHandler(file_handler)
    warnings_logger.addHandler(console_handler)

    return logger


def setup_np2_paths(
    session_folder: Path,
    base_path: Path,
    eid: str,
) -> dict:
    """
    Create a structured dictionary of paths for NP2.0 NWB conversion.

    Unlike the standard setup_paths(), this works with local data that may not
    be registered in the ONE cache yet.

    Parameters
    ----------
    session_folder : Path
        Path to the session folder containing raw_ephys_data/
    base_path : Path
        Base path for output files
    eid : str
        Session identifier (used for organizing output)

    Returns
    -------
    dict
        Dictionary containing paths for conversion
    """
    decompressed_ephys_root = base_path / "decompressed_ephys"
    session_decompressed_ephys_folder = decompressed_ephys_root / eid

    paths = dict(
        output_folder=base_path / "nwbfiles",
        session_folder=session_folder,
        session_decompressed_ephys_folder=session_decompressed_ephys_folder,
        spikeglx_source_folder=session_decompressed_ephys_folder / "raw_ephys_data",
    )

    # Create directories
    paths["output_folder"].mkdir(exist_ok=True, parents=True)
    paths["session_decompressed_ephys_folder"].mkdir(exist_ok=True, parents=True)

    return paths


def get_base_metadata(target_eid: str) -> dict:
    """Get base metadata for NWB files."""
    session_start_time = datetime(2025, 5, 19, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    metadata = {
        "NWBFile": {
            "session_start_time": session_start_time,
            "session_id": target_eid,
            "identifier": target_eid,
            "lab": "steinmetzlab",
            "institution": "University of Washington",
        },
        "Subject": {
            "subject_id": "KM_038",
            "species": "Mus musculus",
            "description": "IBL subject",
        },
    }
    return metadata


def convert_raw_np2_session(
    paths: dict,
    target_eid: str,
    one: ONE,
    probe_name_to_probe_id_dict: dict,
    stub_test: bool,
    include_lf_band: bool,
    logger: logging.Logger,
) -> dict:
    """Convert raw ephys data to NWB file."""
    logger.info("Starting RAW NP2.0 conversion...")
    conversion_start = time.time()

    # Get metadata
    metadata = get_base_metadata(target_eid)
    metadata["NWBFile"]["session_description"] = "IBL Neuropixels 2.0 raw ephys recording"

    # Create converter
    bands = ["ap", "lf"] if include_lf_band else ["ap"]
    converter = IblNeuropixels2Converter(
        folder_path=paths["session_decompressed_ephys_folder"],
        one=one,
        eid=target_eid,
        probe_name_to_probe_id_dict=probe_name_to_probe_id_dict,
        bands=bands,
        verbose=True,
        logger=logger,
    )

    logger.info(f"Created converter with {len(converter.data_interface_objects)} interfaces")
    for key in sorted(converter.data_interface_objects.keys()):
        interface = converter.data_interface_objects[key]
        extractor = interface.recording_extractor
        n_channels = extractor.get_num_channels()
        n_samples = extractor.get_num_samples()
        fs = extractor.get_sampling_frequency()
        duration = n_samples / fs
        logger.info(f"  {key}: {n_channels} channels, {duration:.1f}s @ {fs:.0f} Hz")

    # Merge converter metadata (deep merge to preserve our base metadata)
    converter_metadata = converter.get_metadata()
    metadata = dict_deep_update(metadata, converter_metadata)
    metadata["NWBFile"]["session_description"] = "IBL Neuropixels 2.0 raw ephys recording"

    # Create subject and NWBFile
    subject_metadata = metadata.pop("Subject")
    ibl_subject = IblSubject(**subject_metadata)
    nwbfile = NWBFile(**metadata["NWBFile"])
    nwbfile.subject = ibl_subject
    nwbfile.add_lab_meta_data(lab_meta_data=IblMetadata(revision=IblNeuropixels2Converter.REVISION))

    # Add NIDQ interface
    try:
        nidq_interface = IblNIDQInterface(
            folder_path=str(paths["spikeglx_source_folder"]),
            one=one,
            eid=target_eid,
            verbose=False,
        )
        nidq_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)
        logger.info("  Added NIDQ data")
    except Exception as e:
        logger.warning(f"  Could not add NIDQ: {e}")

    # Configure conversion options
    conversion_options = {}
    for key in converter.data_interface_objects.keys():
        conversion_options[key] = {
            "stub_test": stub_test,
            "iterator_options": {
                "display_progress": True,
                "progress_bar_options": {"desc": f"Writing {key}"},
            },
        }

    # Add ephys data
    logger.info("Adding ephys data to NWBFile...")
    converter.add_to_nwbfile(
        nwbfile=nwbfile,
        metadata=metadata,
        conversion_options=conversion_options,
    )

    # Write NWB file
    conversion_type = "stub" if stub_test else "full"
    output_dir = paths["output_folder"] / conversion_type / "sub-KM-038"
    output_dir.mkdir(parents=True, exist_ok=True)
    nwbfile_path = output_dir / f"sub-KM-038_ses-{target_eid}_desc-raw_ecephys.nwb"

    logger.info(f"Writing RAW NWB file to {nwbfile_path}...")
    write_start = time.time()
    backend_configuration = get_default_backend_configuration(nwbfile=nwbfile, backend="hdf5")
    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend_configuration=backend_configuration,
    )
    write_time = time.time() - write_start

    nwb_size_bytes = nwbfile_path.stat().st_size
    nwb_size_gb = nwb_size_bytes / (1024**3)

    total_time = time.time() - conversion_start
    logger.info(f"RAW conversion completed in {total_time:.2f}s")
    logger.info(f"  File: {nwbfile_path}")
    logger.info(f"  Size: {nwb_size_gb:.4f} GB ({nwb_size_bytes:,} bytes)")

    return {
        "nwbfile_path": nwbfile_path,
        "nwb_size_bytes": nwb_size_bytes,
        "nwb_size_gb": nwb_size_gb,
        "write_time": write_time,
    }


def validate_nwb_file(nwbfile_path: Path, logger: logging.Logger) -> bool:
    """Validate an NWB file by reading it back."""
    try:
        with NWBHDF5IO(str(nwbfile_path), mode="r") as io:
            nwbfile_read = io.read()

            # Check electrode groups (may be empty if no ephys)
            if nwbfile_read.electrode_groups:
                n_groups = len(nwbfile_read.electrode_groups)
                logger.info(f"  Electrode groups: {n_groups}")
            else:
                logger.info("  Electrode groups: 0 (no ephys data)")

            # Check electrodes (may be None if no ephys)
            if nwbfile_read.electrodes is not None:
                n_electrodes = len(nwbfile_read.electrodes)
                logger.info(f"  Electrodes: {n_electrodes}")

            # Check acquisition
            n_acquisition = len(nwbfile_read.acquisition)
            logger.info(f"  Acquisition objects: {n_acquisition}")

            # Check processing modules
            logger.info(f"  Processing modules: {list(nwbfile_read.processing.keys())}")

            # Check trials
            if nwbfile_read.trials is not None:
                logger.info(f"  Trials: {len(nwbfile_read.trials)} trials")

        return True
    except Exception as e:
        logger.error(f"Validation FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    # ========================================================================
    # MAIN CONFIGURATION
    # ========================================================================

    STUB_TEST = True                # Work on lightweight subsets of data
    REDECOMPRESS_EPHYS = False      # Force regeneration of decompressed SpikeGLX binaries
    INCLUDE_LF_BAND = True          # Include LF band data (2.5 kHz) in addition to AP (30 kHz)

    # Paths configuration
    base_folder = Path("/media/heberto/Expansion")
    cache_dir = base_folder / "ibl_cache"
    base_path = base_folder / "ibl_conversion"

    # NP2.0 test session (KM_038)
    # This session has 3 physical probes x 4 shanks = 12 shank folders
    TARGET_EID = "0fc48eb3-0a80-4287-95f6-892a00c3cac1"
    target_eid = (sys.argv[1] if len(sys.argv) > 1 else TARGET_EID).strip()

    # Session folder in the cache (must be pre-downloaded)
    session_folder = cache_dir / "steinmetzlab" / "Subjects" / "KM_038" / "2025-05-19" / "001"

    if not session_folder.exists():
        raise FileNotFoundError(
            f"Session folder not found: {session_folder}\n"
            "NP2.0 data must be pre-downloaded from the internal alyx server."
        )

    # Probe insertion IDs for this session
    probe_name_to_probe_id_dict = {
        "probe00": "placeholder_pid_probe00",
        "probe01": "placeholder_pid_probe01",
        "probe02": "placeholder_pid_probe02",
    }

    # Setup ONE for metadata access (using openalyx for subject info)
    one = ONE(
        base_url="https://openalyx.internationalbrainlab.org",
        cache_dir=cache_dir,
        password='international',
        silent=True,
    )

    # Setup logging
    logs_path = base_path / "conversion_logs"
    logs_path.mkdir(exist_ok=True, parents=True)
    log_file_path = logs_path / f"np2_conversion_{target_eid}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    logger = setup_logger(log_file_path)

    logger.info("=" * 80)
    logger.info("IBL NEUROPIXELS 2.0 RAW CONVERSION SCRIPT")
    logger.info("=" * 80)
    logger.info(f"EID: {target_eid}")
    logger.info(f"Session folder: {session_folder}")
    logger.info(f"Stub test mode: {STUB_TEST}")
    logger.info(f"Include LF band: {INCLUDE_LF_BAND}")
    logger.info(f"Re-decompress ephys: {REDECOMPRESS_EPHYS}")
    logger.info(f"Log file: {log_file_path}")
    logger.info("=" * 80)

    script_start_time = time.time()

    # ========================================================================
    # STEP 1: Setup paths
    # ========================================================================
    logger.info("Setting up paths...")
    paths = setup_np2_paths(session_folder, base_path, target_eid)
    logger.info(f"  Session folder: {paths['session_folder']}")
    logger.info(f"  Decompressed ephys: {paths['session_decompressed_ephys_folder']}")
    logger.info(f"  Output folder: {paths['output_folder']}")

    # ========================================================================
    # STEP 2: Decompress raw ephys data
    # ========================================================================
    scratch_ephys_folder = paths["spikeglx_source_folder"]

    # Check for existing decompressed shank data
    existing_shank_folders = []
    if scratch_ephys_folder.exists():
        existing_shank_folders = [
            f for f in scratch_ephys_folder.iterdir()
            if f.is_dir() and f.name.startswith("probe") and len(f.name) == 8
            and list(f.glob("*.ap.bin"))
        ]
    existing_ephys_bins = len(existing_shank_folders) > 0
    existing_nidq = any(scratch_ephys_folder.glob("*.nidq.bin")) if scratch_ephys_folder.exists() else False

    logger.info("Preparing raw ephys data...")
    decompress_start = time.time()

    if scratch_ephys_folder.exists() and REDECOMPRESS_EPHYS:
        logger.info(f"REDECOMPRESS_EPHYS is True - removing existing data at {scratch_ephys_folder}")
        shutil.rmtree(scratch_ephys_folder)
        scratch_ephys_folder.mkdir(parents=True, exist_ok=True)
        existing_ephys_bins = False
        existing_nidq = False

    need_decompress = not existing_ephys_bins or not existing_nidq
    if need_decompress:
        if not existing_ephys_bins:
            logger.info("  Need to decompress ephys data (no shank folders found)")
        if not existing_nidq:
            logger.info("  Need to decompress NIDQ data")
        logger.info("Decompressing .cbin files (using multithreading)...")
        decompress_ephys_cbins(paths["session_folder"], paths["session_decompressed_ephys_folder"])
    else:
        logger.info(f"Reusing existing decompressed data from {scratch_ephys_folder}")

    decompress_time = time.time() - decompress_start
    logger.info(f"Decompression completed in {decompress_time:.2f}s")

    # Count shank folders
    shank_folders = sorted([
        f for f in scratch_ephys_folder.iterdir()
        if f.is_dir() and f.name.startswith("probe") and len(f.name) == 8
    ])
    logger.info(f"Found {len(shank_folders)} shank folders: {[f.name for f in shank_folders]}")

    # ========================================================================
    # STEP 3: Run raw conversion
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("STARTING RAW CONVERSION")
    logger.info("=" * 80)
    raw_info = convert_raw_np2_session(
        paths=paths,
        target_eid=target_eid,
        one=one,
        probe_name_to_probe_id_dict=probe_name_to_probe_id_dict,
        stub_test=STUB_TEST,
        include_lf_band=INCLUDE_LF_BAND,
        logger=logger,
    )

    logger.info("Validating RAW NWB file...")
    if validate_nwb_file(raw_info["nwbfile_path"], logger):
        logger.info("RAW NWB validation PASSED")
    else:
        logger.error("RAW NWB validation FAILED")

    # ========================================================================
    # SUMMARY
    # ========================================================================
    script_total_time = time.time() - script_start_time
    logger.info("\n" + "=" * 80)
    logger.info("CONVERSION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"RAW NWB: {raw_info['nwbfile_path']}")
    logger.info(f"  Size: {raw_info['nwb_size_gb']:.4f} GB ({raw_info['nwb_size_bytes']:,} bytes)")
    logger.info(f"Total time: {script_total_time:.2f}s ({script_total_time/60:.2f} minutes)")
    logger.info("=" * 80)
    logger.info("")
    logger.info("For processed/behavioral data, use convert_single_bwm_to_nwb.py")
    logger.info("once the session is registered on openalyx.")

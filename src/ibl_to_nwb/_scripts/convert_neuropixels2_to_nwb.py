"""Standalone script to convert an IBL Neuropixels 2.0 session to an NWB file.

This script is adapted from convert_single_bwm_to_nwb.py but handles the specific
case of Neuropixels 2.0 multi-shank recordings where each shank is stored in a
separate compressed file (probe00a/, probe00b/, etc.).

NOTE: Data download is disabled because NP2.0 sessions are not yet available on
openalyx. The data must be pre-downloaded to the local cache folder.

Data sources included:
- Raw ephys (AP and LF bands) via IblNeuropixels2Converter
- NIDQ behavioral sync signals
- Pose estimation (Lightning Pose) for all cameras
- Lick times
- Wheel position and movements
- ROI motion energy for all cameras
- Trials data

Data sources NOT available for this session:
- Raw videos (not uploaded to server yet)
- Anatomical localization (histology not processed yet)
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from neuroconv.tools import configure_and_write_nwbfile
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
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


if __name__ == "__main__":
    # ========================================================================
    # MAIN CONFIGURATION
    # ========================================================================

    STUB_TEST = True                # Work on lightweight subsets of data
    REDECOMPRESS_EPHYS = False      # Force regeneration of decompressed SpikeGLX binaries
    OVERWRITE = True                # Regenerate NWBs even if existing files validate
    INCLUDE_EPHYS = True           # Include raw ephys data (requires decompression - slow first run)
    INCLUDE_LF_BAND = True          # Include LF band data (2.5 kHz) in addition to AP (30 kHz)
    INCLUDE_NIDQ = True            # Include NIDQ behavioral sync signals (requires decompression)
    INCLUDE_BEHAVIOR = True         # Include behavioral data (wheel, licks, trials)
    INCLUDE_POSE = True             # Include pose estimation data (Lightning Pose)
    INCLUDE_MOTION_ENERGY = True    # Include ROI motion energy data

    # --------------------------------------------------------------------------
    # NOTE: Data download is DISABLED for NP2.0 sessions
    # --------------------------------------------------------------------------
    # NP2.0 data is not yet available on openalyx. The session data must be
    # pre-downloaded to the local cache folder before running this script.
    #
    # To download NP2.0 data, use the internal alyx server:
    #   ONE.setup(base_url="https://alyx.internationalbrainlab.org", ...)
    #
    # The following features from convert_single_bwm_to_nwb.py are disabled:
    #   - REDOWNLOAD_DATA: Data must be pre-downloaded
    #   - download_session_data(): Not called
    #   - RUN_CONSISTENCY_CHECKS: Requires ONE API access to source data
    # --------------------------------------------------------------------------

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
    # NOTE: These would normally come from load_fixtures, but NP2.0 sessions
    # may not be in the fixtures yet. For now, we use placeholder IDs.
    # TODO: Update with real probe insertion IDs when available
    probe_name_to_probe_id_dict = {
        "probe00": "placeholder_pid_probe00",
        "probe01": "placeholder_pid_probe01",
        "probe02": "placeholder_pid_probe02",
    }

    # Setup ONE for metadata access (using openalyx for subject info)
    # NOTE: Session-specific data won't be available, but subject metadata may be
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
    logger.info("IBL NEUROPIXELS 2.0 CONVERSION SCRIPT STARTED")
    logger.info("=" * 80)
    logger.info(f"EID: {target_eid}")
    logger.info(f"Session folder: {session_folder}")
    logger.info(f"Stub test mode: {STUB_TEST}")
    logger.info(f"Include LF band: {INCLUDE_LF_BAND}")
    logger.info(f"Re-decompress ephys: {REDECOMPRESS_EPHYS}")
    logger.info(f"Overwrite existing NWB: {OVERWRITE}")
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

    # Check for existing decompressed data
    scratch_ephys_folder = paths["spikeglx_source_folder"]

    # Check for existing decompressed shank data (not just NIDQ)
    # Look for probeXXY folders with .bin files inside
    existing_shank_folders = []
    if scratch_ephys_folder.exists():
        existing_shank_folders = [
            f for f in scratch_ephys_folder.iterdir()
            if f.is_dir() and f.name.startswith("probe") and len(f.name) == 8
            and list(f.glob("*.ap.bin"))  # Must have decompressed AP data
        ]
    existing_ephys_bins = len(existing_shank_folders) > 0

    # Check for NIDQ separately
    existing_nidq = any(scratch_ephys_folder.glob("*.nidq.bin")) if scratch_ephys_folder.exists() else False

    # ========================================================================
    # STEP 2: Decompress raw ephys data (if needed)
    # ========================================================================
    if INCLUDE_EPHYS or INCLUDE_NIDQ:
        logger.info("Preparing raw ephys data...")
        decompress_start = time.time()

        if scratch_ephys_folder.exists() and REDECOMPRESS_EPHYS:
            logger.info(f"REDECOMPRESS_EPHYS is True - removing existing data at {scratch_ephys_folder}")
            shutil.rmtree(scratch_ephys_folder)
            scratch_ephys_folder.mkdir(parents=True, exist_ok=True)
            existing_ephys_bins = False
            existing_nidq = False

        # Determine if we need to decompress
        need_decompress = False
        if INCLUDE_EPHYS and not existing_ephys_bins:
            need_decompress = True
            logger.info("  Need to decompress ephys data (no shank folders found)")
        if INCLUDE_NIDQ and not existing_nidq:
            need_decompress = True
            logger.info("  Need to decompress NIDQ data")

        if need_decompress:
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
    else:
        logger.info("Skipping ephys decompression (INCLUDE_EPHYS=False, INCLUDE_NIDQ=False)")

    # ========================================================================
    # STEP 3: Create NP2.0 converter (if including ephys)
    # ========================================================================
    converter = None
    if INCLUDE_EPHYS:
        logger.info("Creating IblNeuropixels2Converter...")
        converter_start = time.time()

        bands = ["ap", "lf"] if INCLUDE_LF_BAND else ["ap"]

        converter = IblNeuropixels2Converter(
            folder_path=paths["session_decompressed_ephys_folder"],
            one=one,
            eid=target_eid,
            probe_name_to_probe_id_dict=probe_name_to_probe_id_dict,
            bands=bands,
            verbose=True,
            logger=logger,
        )

        converter_time = time.time() - converter_start
        logger.info(f"Converter created in {converter_time:.2f}s")
        logger.info(f"Number of ephys interfaces: {len(converter.data_interface_objects)}")

        # Log interface details
        for key in sorted(converter.data_interface_objects.keys()):
            interface = converter.data_interface_objects[key]
            extractor = interface.recording_extractor
            n_channels = extractor.get_num_channels()
            n_samples = extractor.get_num_samples()
            fs = extractor.get_sampling_frequency()
            duration = n_samples / fs
            logger.info(f"  {key}: {n_channels} channels, {duration:.1f}s @ {fs:.0f} Hz")
    else:
        logger.info("Skipping ephys converter (INCLUDE_EPHYS=False)")

    # ========================================================================
    # STEP 4: Load local data (behavioral and pose)
    # ========================================================================
    # NOTE: The standard IBL interfaces (WheelPositionInterface, etc.) rely on the
    # ONE API having the session registered. Since NP2.0 sessions are not on openalyx,
    # we load data directly from local files and add them manually in STEP 6.
    logger.info("Loading local data files...")

    # Collect all data interfaces (starting with the NP2 converter's interfaces if present)
    data_interfaces = []
    if converter is not None:
        data_interfaces = list(converter.data_interface_objects.values())

    # --------------------------------------------------------------------------
    # NIDQ Interface (behavioral sync signals)
    # --------------------------------------------------------------------------
    if INCLUDE_NIDQ:
        try:
            nidq_interface = IblNIDQInterface(
                folder_path=str(paths["spikeglx_source_folder"]),
                one=one,
                eid=target_eid,
                verbose=False,
            )
            data_interfaces.append(nidq_interface)
            logger.info("  Added NIDQ interface (behavioral sync)")
        except Exception as e:
            logger.warning(f"  Could not create NIDQ interface: {e}")

    # --------------------------------------------------------------------------
    # Local data loading (behavioral and pose)
    # --------------------------------------------------------------------------
    # Since the session is not on openalyx, we load data from local ALF files
    alf_folder = session_folder / "alf"
    task_folder = alf_folder / "task_00"

    local_data = {}

    # Wheel position
    if INCLUDE_BEHAVIOR:
        wheel_position_file = task_folder / "_ibl_wheel.position.npy"
        wheel_timestamps_file = task_folder / "_ibl_wheel.timestamps.npy"
        if wheel_position_file.exists() and wheel_timestamps_file.exists():
            local_data["wheel_position"] = np.load(wheel_position_file)
            local_data["wheel_timestamps"] = np.load(wheel_timestamps_file)
            logger.info(f"  Loaded wheel position: {len(local_data['wheel_position'])} samples")
        else:
            logger.warning(f"  Wheel position files not found")

        # Wheel movements
        wheel_moves_file = task_folder / "_ibl_wheelMoves.intervals.npy"
        wheel_moves_amp_file = task_folder / "_ibl_wheelMoves.peakAmplitude.npy"
        if wheel_moves_file.exists():
            local_data["wheel_moves_intervals"] = np.load(wheel_moves_file)
            if wheel_moves_amp_file.exists():
                local_data["wheel_moves_amplitude"] = np.load(wheel_moves_amp_file)
            logger.info(f"  Loaded wheel movements: {len(local_data['wheel_moves_intervals'])} intervals")

        # Licks
        licks_file = alf_folder / "licks.times.npy"
        if licks_file.exists():
            local_data["licks_times"] = np.load(licks_file)
            logger.info(f"  Loaded lick times: {len(local_data['licks_times'])} licks")
        else:
            logger.warning(f"  Licks file not found")

        # Trials
        trials_file = task_folder / "_ibl_trials.table.pqt"
        if trials_file.exists():
            local_data["trials"] = pd.read_parquet(trials_file)
            logger.info(f"  Loaded trials: {len(local_data['trials'])} trials")
        else:
            logger.warning(f"  Trials file not found")

    # Pose estimation (Lightning Pose)
    if INCLUDE_POSE:
        for camera_name in ["left", "right", "body"]:
            pose_file = alf_folder / f"_ibl_{camera_name}Camera.lightningPose.pqt"
            times_file = alf_folder / f"_ibl_{camera_name}Camera.times.npy"
            if pose_file.exists() and times_file.exists():
                local_data[f"pose_{camera_name}"] = pd.read_parquet(pose_file)
                local_data[f"pose_{camera_name}_times"] = np.load(times_file)
                logger.info(f"  Loaded pose estimation ({camera_name}Camera): {len(local_data[f'pose_{camera_name}'])} frames")
            else:
                logger.warning(f"  Pose estimation files not found for {camera_name}Camera")

    # ROI motion energy
    if INCLUDE_MOTION_ENERGY:
        for camera_name in ["left", "right", "body"]:
            motion_energy_file = alf_folder / f"{camera_name}Camera.ROIMotionEnergy.npy"
            times_file = alf_folder / f"_ibl_{camera_name}Camera.times.npy"
            if motion_energy_file.exists() and times_file.exists():
                local_data[f"motion_energy_{camera_name}"] = np.load(motion_energy_file)
                # Reuse pose timestamps or load separately
                if f"pose_{camera_name}_times" not in local_data:
                    local_data[f"motion_energy_{camera_name}_times"] = np.load(times_file)
                logger.info(f"  Loaded ROI motion energy ({camera_name}Camera): {len(local_data[f'motion_energy_{camera_name}'])} samples")
            else:
                logger.warning(f"  ROI motion energy files not found for {camera_name}Camera")

    logger.info(f"Total ephys interfaces: {len(data_interfaces)}")

    # ========================================================================
    # STEP 5: Get metadata
    # ========================================================================
    logger.info("Getting metadata...")
    if converter is not None:
        metadata = converter.get_metadata()
    else:
        # Initialize empty metadata when no ephys converter
        metadata = {}

    # Add session metadata
    # NOTE: Since this session may not be on openalyx, we construct metadata manually
    nwbfile_metadata = metadata.setdefault("NWBFile", {})
    subject_metadata_block = metadata.setdefault("Subject", {})

    # Session metadata (manual for NP2.0 sessions not on openalyx)
    session_start_time = datetime(2025, 5, 19, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    nwbfile_metadata["session_start_time"] = session_start_time
    nwbfile_metadata["session_id"] = target_eid
    nwbfile_metadata["identifier"] = target_eid  # Required by NWBFile
    nwbfile_metadata["lab"] = "steinmetzlab"
    nwbfile_metadata["institution"] = "University of Washington"
    nwbfile_metadata["session_description"] = "IBL Neuropixels 2.0 recording session"

    # Subject metadata
    subject_metadata_block["subject_id"] = "KM_038"
    subject_metadata_block["species"] = "Mus musculus"
    subject_metadata_block["description"] = "IBL subject"

    # ========================================================================
    # STEP 6: Create NWBFile and add data
    # ========================================================================
    logger.info("Creating NWBFile...")
    conversion_start = time.time()

    # Create subject
    subject_metadata_for_ndx = metadata.pop("Subject")
    ibl_subject = IblSubject(**subject_metadata_for_ndx)

    # Create NWBFile
    nwbfile = NWBFile(**metadata["NWBFile"])
    nwbfile.subject = ibl_subject
    nwbfile.add_lab_meta_data(lab_meta_data=IblMetadata(revision=IblNeuropixels2Converter.REVISION))

    # Configure conversion options for ephys interfaces and add ephys data
    if converter is not None:
        conversion_options = {}
        for key in converter.data_interface_objects.keys():
            conversion_options[key] = {
                "stub_test": STUB_TEST,
                "iterator_options": {
                    "display_progress": True,
                    "progress_bar_options": {"desc": f"Writing {key}"},
                },
            }

        # Add data from NP2.0 converter (raw ephys)
        logger.info("Adding ephys data to NWBFile...")
        converter.add_to_nwbfile(
            nwbfile=nwbfile,
            metadata=metadata,
            conversion_options=conversion_options,
        )

    # Add NIDQ interface if present
    for interface in data_interfaces:
        if isinstance(interface, IblNIDQInterface):
            try:
                interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)
                logger.info("  Added NIDQ data")
            except Exception as e:
                logger.warning(f"  Failed to add NIDQ: {e}")

    # --------------------------------------------------------------------------
    # Add local data to NWB file
    # --------------------------------------------------------------------------
    logger.info("Adding behavioral and pose data to NWBFile...")
    from neuroconv.tools.nwb_helpers import get_module
    from pynwb.behavior import Position, SpatialSeries, BehavioralTimeSeries, BehavioralEpochs
    from pynwb.epoch import TimeIntervals
    from ndx_pose import PoseEstimation, PoseEstimationSeries, Skeleton, Skeletons

    # Get or create behavior processing module
    behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="Behavioral data")

    # Wheel position
    if "wheel_position" in local_data and "wheel_timestamps" in local_data:
        try:
            wheel_position_series = SpatialSeries(
                name="WheelPosition",
                description="Wheel position in radians",
                data=local_data["wheel_position"],
                timestamps=local_data["wheel_timestamps"],
                unit="radians",
                reference_frame="Wheel rotation relative to session start",
            )
            position_container = Position(name="Position", spatial_series=[wheel_position_series])
            behavior_module.add(position_container)
            logger.info("  Added wheel position")
        except Exception as e:
            logger.warning(f"  Failed to add wheel position: {e}")

    # Wheel movements
    if "wheel_moves_intervals" in local_data:
        try:
            wheel_moves = TimeIntervals(
                name="WheelMovementIntervals",
                description="Intervals of detected wheel movements",
            )
            wheel_moves.add_column(name="peak_amplitude", description="Peak amplitude of wheel movement in radians")
            intervals = local_data["wheel_moves_intervals"]
            amplitudes = local_data.get("wheel_moves_amplitude", np.zeros(len(intervals)))
            for index in range(len(intervals)):
                wheel_moves.add_interval(
                    start_time=intervals[index, 0],
                    stop_time=intervals[index, 1],
                    peak_amplitude=amplitudes[index] if index < len(amplitudes) else 0.0,
                )
            behavior_module.add(wheel_moves)
            logger.info("  Added wheel movements")
        except Exception as e:
            logger.warning(f"  Failed to add wheel movements: {e}")

    # Licks
    if "licks_times" in local_data:
        try:
            from pynwb.behavior import BehavioralEvents
            lick_times_series = BehavioralTimeSeries(
                name="LickTimes",
                time_series=[
                    SpatialSeries(
                        name="lick_times",
                        description="Times of detected licks",
                        data=np.ones(len(local_data["licks_times"])),  # Event markers
                        timestamps=local_data["licks_times"],
                        unit="n/a",
                        reference_frame="Lick detection events",
                    )
                ],
            )
            behavior_module.add(lick_times_series)
            logger.info("  Added lick times")
        except Exception as e:
            logger.warning(f"  Failed to add lick times: {e}")

    # Trials
    if "trials" in local_data:
        try:
            trials_df = local_data["trials"]

            # Determine start/stop columns
            if "intervals_0" in trials_df.columns and "intervals_1" in trials_df.columns:
                start_col, stop_col = "intervals_0", "intervals_1"
            elif "start_time" in trials_df.columns and "stop_time" in trials_df.columns:
                start_col, stop_col = "start_time", "stop_time"
            else:
                raise ValueError("Cannot find trial interval columns")

            # Add custom columns (excluding interval columns which are handled by start_time/stop_time)
            extra_columns = [col for col in trials_df.columns if col not in [start_col, stop_col]]
            for col in extra_columns:
                nwbfile.add_trial_column(name=col, description=f"Trial column: {col}")

            # Add each trial
            for _, row in trials_df.iterrows():
                trial_kwargs = {
                    "start_time": float(row[start_col]),
                    "stop_time": float(row[stop_col]),
                }
                for col in extra_columns:
                    val = row[col]
                    # Convert numpy types to Python types for NWB
                    if pd.isna(val):
                        trial_kwargs[col] = float('nan')
                    elif hasattr(val, 'item'):
                        trial_kwargs[col] = val.item()
                    else:
                        trial_kwargs[col] = val
                nwbfile.add_trial(**trial_kwargs)
            logger.info(f"  Added {len(trials_df)} trials")
        except Exception as e:
            logger.warning(f"  Failed to add trials: {e}")

    # Pose estimation (Lightning Pose)
    pose_module = get_module(nwbfile=nwbfile, name="pose_estimation", description="Pose estimation from video using Lightning Pose")
    skeletons_container = None

    for camera_name in ["left", "right", "body"]:
        pose_key = f"pose_{camera_name}"
        times_key = f"pose_{camera_name}_times"
        if pose_key in local_data and times_key in local_data:
            try:
                pose_df = local_data[pose_key]
                timestamps = local_data[times_key]

                # Extract body parts from column names
                body_parts = []
                for col in pose_df.columns:
                    if col.endswith("_x"):
                        base = col[:-2]
                        if f"{base}_y" in pose_df.columns and f"{base}_likelihood" in pose_df.columns:
                            body_parts.append(base)

                if not body_parts:
                    logger.warning(f"  No valid body parts found in {camera_name} pose data")
                    continue

                # Create pose estimation series for each body part
                pose_series_list = []
                reused_timestamps = None
                for body_part in body_parts:
                    data = np.column_stack([
                        pose_df[f"{body_part}_x"].values,
                        pose_df[f"{body_part}_y"].values,
                    ])
                    confidence = pose_df[f"{body_part}_likelihood"].values

                    series = PoseEstimationSeries(
                        name=f"PoseEstimationSeries{body_part.replace('_', ' ').title().replace(' ', '')}",
                        description=f"Position of {body_part}",
                        data=data,
                        unit="px",
                        reference_frame="(0,0) corresponds to upper left corner",
                        timestamps=reused_timestamps or timestamps,
                        confidence=confidence,
                    )
                    pose_series_list.append(series)
                    if reused_timestamps is None:
                        reused_timestamps = series  # Link timestamps

                # Create skeleton
                skeleton_name = f"{camera_name.capitalize()}Camera"
                nwb_body_part_names = [s.name for s in pose_series_list]
                skeleton = Skeleton(
                    name=skeleton_name,
                    nodes=nwb_body_part_names,
                    edges=np.empty((0, 2), dtype="uint8"),
                    subject=nwbfile.subject,
                )

                # Add to skeletons container
                if skeletons_container is None:
                    skeletons_container = Skeletons(name="Skeletons", skeletons=[skeleton])
                    pose_module.add(skeletons_container)
                else:
                    skeletons_container.add_skeletons(skeleton)

                # Create pose estimation container
                pose_estimation = PoseEstimation(
                    name=f"{camera_name.capitalize()}Camera",
                    pose_estimation_series=pose_series_list,
                    description=f"Pose estimation for {camera_name} camera using Lightning Pose",
                    source_software="Lightning Pose",
                    skeleton=skeleton,
                )
                pose_module.add(pose_estimation)
                logger.info(f"  Added pose estimation ({camera_name}Camera): {len(body_parts)} body parts")

            except Exception as e:
                logger.warning(f"  Failed to add pose estimation for {camera_name}: {e}")

    # ROI Motion Energy
    for camera_name in ["left", "right", "body"]:
        me_key = f"motion_energy_{camera_name}"
        times_key = f"pose_{camera_name}_times"  # Reuse pose timestamps
        alt_times_key = f"motion_energy_{camera_name}_times"
        if me_key in local_data:
            try:
                timestamps = local_data.get(times_key, local_data.get(alt_times_key))
                if timestamps is None:
                    logger.warning(f"  No timestamps for {camera_name} motion energy")
                    continue

                me_data = local_data[me_key]
                # Trim to match timestamps if needed
                min_len = min(len(me_data), len(timestamps))
                me_data = me_data[:min_len]
                timestamps = timestamps[:min_len]

                me_series = SpatialSeries(
                    name=f"{camera_name.capitalize()}CameraMotionEnergy",
                    description=f"ROI motion energy from {camera_name} camera",
                    data=me_data,
                    timestamps=timestamps,
                    unit="a.u.",
                    reference_frame="Motion energy in ROI",
                )

                # Add to behavior module
                if "MotionEnergy" not in [di.name for di in behavior_module.data_interfaces.values()]:
                    me_container = BehavioralTimeSeries(name="MotionEnergy", time_series=[me_series])
                    behavior_module.add(me_container)
                else:
                    behavior_module.data_interfaces["MotionEnergy"].add_timeseries(me_series)
                logger.info(f"  Added ROI motion energy ({camera_name}Camera)")

            except Exception as e:
                logger.warning(f"  Failed to add motion energy for {camera_name}: {e}")

    conversion_time = time.time() - conversion_start
    logger.info(f"Data added in {conversion_time:.2f}s")

    # ========================================================================
    # STEP 7: Write NWB file
    # ========================================================================
    logger.info("Writing NWB file...")
    write_start = time.time()

    conversion_type = "stub" if STUB_TEST else "full"
    output_dir = paths["output_folder"] / conversion_type / f"sub-KM-038"
    output_dir.mkdir(parents=True, exist_ok=True)
    nwbfile_path = output_dir / f"sub-KM-038_ses-{target_eid}_desc-raw_np2_ecephys.nwb"

    # Get backend configuration
    backend_configuration = get_default_backend_configuration(nwbfile=nwbfile, backend="hdf5")

    # Write file
    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend_configuration=backend_configuration,
    )

    write_time = time.time() - write_start
    nwb_size_bytes = nwbfile_path.stat().st_size
    nwb_size_gb = nwb_size_bytes / (1024**3)

    logger.info(f"NWB file written in {write_time:.2f}s")
    logger.info(f"NWB file size: {nwb_size_gb:.4f} GB ({nwb_size_bytes:,} bytes)")
    logger.info(f"NWB file path: {nwbfile_path}")

    # ========================================================================
    # STEP 8: Validate NWB file
    # ========================================================================
    logger.info("Validating NWB file...")
    try:
        with NWBHDF5IO(str(nwbfile_path), mode="r") as io:
            nwbfile_read = io.read()

            # Check electrode groups (may be empty if no ephys)
            if nwbfile_read.electrode_groups:
                n_groups = len(nwbfile_read.electrode_groups)
                logger.info(f"  Electrode groups: {n_groups}")
                for name, group in nwbfile_read.electrode_groups.items():
                    logger.info(f"    {name}: {group.description}")
            else:
                logger.info("  Electrode groups: 0 (no ephys data)")

            # Check electrodes (may be None if no ephys)
            if nwbfile_read.electrodes is not None:
                n_electrodes = len(nwbfile_read.electrodes)
                logger.info(f"  Electrodes: {n_electrodes}")
            else:
                logger.info("  Electrodes: None (no ephys data)")

            # Check acquisition (ElectricalSeries, NIDQ)
            n_acquisition = len(nwbfile_read.acquisition)
            logger.info(f"  Acquisition objects: {n_acquisition}")
            for name in sorted(nwbfile_read.acquisition.keys()):
                obj = nwbfile_read.acquisition[name]
                if hasattr(obj, 'data'):
                    logger.info(f"    {name}: shape={obj.data.shape}")

            # Check processing modules
            logger.info(f"  Processing modules: {list(nwbfile_read.processing.keys())}")
            for module_name, module in nwbfile_read.processing.items():
                logger.info(f"    {module_name}: {list(module.data_interfaces.keys())}")

            # Check behavior module specifically
            if "behavior" in nwbfile_read.processing:
                behavior = nwbfile_read.processing["behavior"]
                logger.info(f"  Behavior data interfaces: {len(behavior.data_interfaces)}")

            # Check pose estimation module
            if "pose_estimation" in nwbfile_read.processing:
                pose = nwbfile_read.processing["pose_estimation"]
                logger.info(f"  Pose estimation data interfaces: {len(pose.data_interfaces)}")

            # Check trials
            if nwbfile_read.trials is not None:
                logger.info(f"  Trials: {len(nwbfile_read.trials)} trials")

        logger.info("NWB validation PASSED")
    except Exception as e:
        logger.error(f"NWB validation FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # ========================================================================
    # SUMMARY
    # ========================================================================
    script_total_time = time.time() - script_start_time
    logger.info("\n" + "=" * 80)
    logger.info("CONVERSION COMPLETED")
    logger.info("=" * 80)
    logger.info(f"Total time: {script_total_time:.2f}s ({script_total_time/60:.2f} minutes)")
    logger.info(f"NWB file: {nwbfile_path}")
    logger.info(f"NWB size: {nwb_size_gb:.4f} GB")
    logger.info("=" * 80)

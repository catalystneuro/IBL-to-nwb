from __future__ import annotations

import logging
import time
import warnings
from datetime import datetime
from pathlib import Path

from zoneinfo import ZoneInfo

from neuroconv import ConverterPipe
from neuroconv.tools import configure_and_write_nwbfile
from ndx_ibl import IblMetadata, IblSubject
from one.api import ONE
from one import alf
from pynwb import NWBFile, read_nwb

from ..bwm_to_nwb import setup_paths
from ..datainterfaces import (
    IblSortingInterface,
    IblAnatomicalLocalizationInterface,
    BrainwideMapTrialsInterface,
    WheelInterface,
    SessionEpochsInterface,
    PassiveIntervalsInterface,
    PassiveReplayStimInterface,
    # PassiveRFMInterface,  # Temporarily disabled due to data quality issues
    LickInterface,
    IblPoseEstimationInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    ProbeTrajectoryInterface,
)
from ..fixtures import load_fixtures
from ..utils import add_probe_electrodes_with_localization, get_ibl_subject_metadata, sanitize_subject_id_for_dandi


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


def convert_processed_session(
    eid: str,
    one: ONE,
    stub_test: bool = False,
    base_path: Path | None = None,
    logger: logging.Logger | None = None,
    overwrite: bool = False,
) -> dict:
    """Convert IBL processed session to NWB.

    Parameters
    ----------
    eid : str
        Experiment ID (session UUID)
    one : ONE
        ONE API instance
    stub_test : bool, optional
        If True, creates minimal NWB for testing without downloading large files.
        In stub mode, spike properties (spike_amplitudes, spike_distances_from_probe_tip)
        are automatically skipped to reduce memory usage.
    base_path : Path, optional
        Base output directory for NWB files
    logger : logging.Logger, optional
        Logger instance for conversion progress
    overwrite : bool, optional
        If True, overwrite existing NWB files

    Returns
    -------
    dict
        Conversion result information including NWB file path and timing
    """

    # ========================================================================
    # SUPPRESS HARMLESS WARNINGS
    # ========================================================================
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
        logger.info(f"Starting PROCESSED conversion for session {eid}")

    # Setup paths
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
    provisional_nwbfile_path = output_dir / f"sub-{subject_id_for_filenames}_ses-{eid}_desc-processed_behavior+ecephys.nwb"

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

    # ========================================================================
    # STEP 1: Define data interfaces
    # ========================================================================
    if logger:
        logger.info("Creating data interfaces...")
    interface_creation_start = time.time()

    data_interfaces = []
    interface_kwargs = dict(one=one, session=eid)

    # Spike sorting
    sorting_interface = IblSortingInterface(**interface_kwargs)
    data_interfaces.append(sorting_interface)

    # Anatomical localization (loads probe info and histology QC internally)
    anat_interface = IblAnatomicalLocalizationInterface(one=one, eid=eid)
    if anat_interface.probe_name_to_probe_id_dict:  # Only add if has probes with good histology
        data_interfaces.append(anat_interface)

    # Behavioral data
    data_interfaces.append(BrainwideMapTrialsInterface(**interface_kwargs))
    data_interfaces.append(WheelInterface(**interface_kwargs))

    # Session epochs (high-level task vs passive phases)
    if SessionEpochsInterface.check_availability(one, eid)["available"]:
        data_interfaces.append(SessionEpochsInterface(**interface_kwargs))

    # Passive period data - add each interface if its data is available
    if PassiveIntervalsInterface.check_availability(one, eid)["available"]:
        data_interfaces.append(PassiveIntervalsInterface(**interface_kwargs))

    # NOTE: PassiveRFMInterface is temporarily disabled due to data quality issues - waiting for upstream fix
    # if PassiveRFMInterface.check_availability(one, eid)["available"]:
    #     data_interfaces.append(PassiveRFMInterface(**interface_kwargs))

    if PassiveReplayStimInterface.check_availability(one, eid)["available"]:
        data_interfaces.append(PassiveReplayStimInterface(**interface_kwargs))

    # Licks - optional interface
    if LickInterface.check_availability(one, eid)["available"]:
        data_interfaces.append(LickInterface(**interface_kwargs))

    # Camera-based interfaces (pose estimation, pupil tracking, ROI motion energy)
    # Check availability per camera since not all sessions have all cameras
    for camera_view in ["left", "right", "body"]:
        camera_name = f"{camera_view}Camera"

        # Pose estimation - check_availability handles Lightning Pose → DLC fallback
        if IblPoseEstimationInterface.check_availability(one, eid, camera_name=camera_name)["available"]:
            data_interfaces.append(
                IblPoseEstimationInterface(camera_name=camera_name, tracker="lightningPose", **interface_kwargs)
            )

        # Pupil tracking - only for left/right cameras (body camera doesn't capture eyes)
        if camera_view in ["left", "right"]:
            if PupilTrackingInterface.check_availability(one, eid, camera_name=camera_name)["available"]:
                data_interfaces.append(PupilTrackingInterface(camera_name=camera_name, **interface_kwargs))

        # ROI motion energy
        if RoiMotionEnergyInterface.check_availability(one, eid, camera_name=camera_name)["available"]:
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

    # Get subject metadata using centralized utility function
    subject_metadata_block.update(
        get_ibl_subject_metadata(one=one, session_metadata=session_metadata, tzinfo=tzinfo)
    )

    # ========================================================================
    # STEP 4: Configure conversion options
    # ========================================================================
    conversion_options = {}

    # Sorting interface options
    sorting_options = {"stub_test": stub_test}
    # In stub mode, automatically skip large spike properties to reduce memory usage
    if stub_test:
        sorting_options["skip_properties"] = ["spike_amplitudes_uV", "spike_distances_from_probe_tip_um"]
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
    nwbfile.add_lab_meta_data(lab_meta_data=IblMetadata(revision="2025-05-06"))

    for probe_name, pid in anat_interface.probe_name_to_probe_id_dict.items():
        add_probe_electrodes_with_localization(
            nwbfile=nwbfile,
            one=one,
            eid=eid,
            probe_name=probe_name,
            pid=pid,
        )

    # Add probe trajectory table (insertion geometry: angles, depth, coordinates)
    if anat_interface.probe_name_to_probe_id_dict:
        trajectory_interface = ProbeTrajectoryInterface(
            one=one,
            eid=eid,
            probe_name_to_probe_id_dict=anat_interface.probe_name_to_probe_id_dict,
        )
        trajectory_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)

    # Add data from all interfaces
    for interface_name, data_interface in converter.data_interface_objects.items():
        interface_conversion_options = conversion_options.get(interface_name, {})
        data_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, **interface_conversion_options)

    conversion_time = time.time() - conversion_start
    if logger:
        logger.info(f"In-memory NWBFile built in {conversion_time:.2f}s")

    # ========================================================================
    # STEP 6: Write NWB file
    # ========================================================================
    if logger:
        logger.info("Writing NWB file...")
    write_start = time.time()

    # Use sanitized subject ID for filename (DANDI compliance)
    subject_id_for_filename = sanitize_subject_id_for_dandi(nwbfile.subject.subject_id)
    nwbfile_path = output_dir / f"sub-{subject_id_for_filename}_ses-{eid}_desc-processed_behavior+ecephys.nwb"

    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend="hdf5",
    )

    # Set units table metadata attributes directly in HDF5
    # This is a workaround for neuroconv's configure_backend which strips these attributes
    import h5py
    with h5py.File(nwbfile_path, "a") as hf:
        if "units/waveform_mean" in hf:
            hf["units/waveform_mean"].attrs["sampling_rate"] = 30000.0  # IBL Neuropixels sampling rate in Hz
            hf["units/waveform_mean"].attrs["unit"] = "microvolts"  # Data converted from Volts to uV
        if "units/spike_times" in hf:
            hf["units/spike_times"].attrs["resolution"] = 1.0 / 30000.0  # Smallest time difference in seconds

    write_time = time.time() - write_start

    # Get NWB file size
    nwb_size_bytes = nwbfile_path.stat().st_size
    nwb_size_gb = nwb_size_bytes / (1024**3)

    if logger:
        total_time_seconds = time.time() - start_time
        total_time_hours = total_time_seconds / 3600
        logger.info(f"NWB file written in {write_time:.2f}s")
        logger.info(f"PROCESSED NWB file size: {nwb_size_gb:.2f} GB ({nwb_size_bytes:,} bytes)")
        logger.info(f"Write speed: {nwb_size_gb / (write_time / 3600):.2f} GB/hour")
        logger.info(f"PROCESSED conversion total time: {total_time_seconds:.2f}s")
        logger.info(f"PROCESSED conversion total time: {total_time_hours:.2f} hours")
        logger.info(f"PROCESSED conversion completed: {nwbfile_path}")
        logger.info(f"PROCESSED NWB saved to: {nwbfile_path}")

    return {
        "nwbfile_path": nwbfile_path,
        "nwb_size_bytes": nwb_size_bytes,
        "nwb_size_gb": nwb_size_gb,
        "write_time": write_time,
    }

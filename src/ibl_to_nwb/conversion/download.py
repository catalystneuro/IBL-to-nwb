from __future__ import annotations

import logging
import time
from pathlib import Path

from one.api import ONE

from ..bwm_to_nwb import setup_paths
from ..fixtures import load_fixtures
from ..datainterfaces import (
    IblSortingInterface,
    IblAnatomicalLocalizationInterface,
    BrainwideMapTrialsInterface,
    WheelInterface,
    PassiveIntervalsInterface,
    PassiveReplayStimInterface,
    PassiveRFMInterface,
    IblPoseEstimationInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    LickInterface,
    RawVideoInterface,
)


def download_session_data(
    eid: str,
    one: ONE,
    redownload_data: bool = False,
    stub_test: bool = False,
    base_path: Path | None = None,
    decompressed_ephys_path: Path | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    """Download all datasets for a session using interface-specific download methods."""
    if logger:
        logger.info("Downloading session data from ONE...")
    download_start = time.time()

    # Setup paths to check cache location
    paths = setup_paths(one, eid, base_path=base_path, decompressed_ephys_path=decompressed_ephys_path)

    # Check if we need to clear cached data
    if redownload_data and paths["session_folder"].exists():
        if logger:
            logger.info(f"REDOWNLOAD_DATA is True - clearing cached data for session {eid}")
        import shutil
        shutil.rmtree(paths["session_folder"])
        paths["session_folder"].mkdir(parents=True, exist_ok=True)

    # Define all interfaces to download (for both RAW and PROCESSED conversions)
    interfaces_to_download = []

    # Core behavioral/processed data interfaces
    interfaces_to_download.extend([
        ("Trials", BrainwideMapTrialsInterface, {}),
        ("Wheel", WheelInterface, {}),
        ("Licks", LickInterface, {}),
    ])

    # Passive period interfaces (check availability first - each is optional)
    if PassiveIntervalsInterface.check_availability(one, eid)["available"]:
        interfaces_to_download.append(("PassiveIntervals", PassiveIntervalsInterface, {}))

    if PassiveReplayStimInterface.check_availability(one, eid)["available"]:
        interfaces_to_download.append(("PassiveReplay", PassiveReplayStimInterface, {}))

    if PassiveRFMInterface.check_availability(one, eid)["available"]:
        interfaces_to_download.append(("PassiveRFM", PassiveRFMInterface, {}))

    # Spike sorting and anatomical localization
    # Note: Anatomical localization checks availability internally and may skip if no good histology
    interfaces_to_download.extend([
        ("SpikeSorting", IblSortingInterface, {}),
        ("AnatomicalLocalization", IblAnatomicalLocalizationInterface, {}),
    ])

    # Camera-based interfaces (videos, pose, pupil, motion energy)
    # Check availability per camera since not all sessions have all cameras
    for camera_view in ["left", "right", "body"]:
        # Note: RawVideoInterface expects camera_view ("left"), others expect camera_name ("leftCamera")
        camera_name = f"{camera_view}Camera"

        # Check and add each camera interface if available
        if RawVideoInterface.check_availability(one, eid, camera_name=camera_view)["available"]:
            interfaces_to_download.append((f"RawVideo_{camera_view}", RawVideoInterface, {"camera_name": camera_view}))

        if IblPoseEstimationInterface.check_availability(one, eid, camera_name=camera_name)["available"]:
            interfaces_to_download.append((f"PoseEstimation_{camera_view}", IblPoseEstimationInterface, {"camera_name": camera_name}))

        # Pupil tracking - only for left/right cameras (body camera doesn't capture eyes)
        if camera_view in ["left", "right"]:
            if PupilTrackingInterface.check_availability(one, eid, camera_name=camera_name)["available"]:
                interfaces_to_download.append((f"PupilTracking_{camera_view}", PupilTrackingInterface, {"camera_name": camera_name}))

        if RoiMotionEnergyInterface.check_availability(one, eid, camera_name=camera_name)["available"]:
            interfaces_to_download.append((f"RoiMotionEnergy_{camera_view}", RoiMotionEnergyInterface, {"camera_name": camera_name}))

    if logger:
        logger.info(f"Downloading data for {len(interfaces_to_download)} interface(s)...")

    # Download data for each interface
    # No try-except - let failures propagate (fail-fast principle)
    for interface_name, interface_class, kwargs in interfaces_to_download:
        # Skip heavy data in stub test mode
        if stub_test:
            # Skip raw ephys and raw videos in stub mode
            if "RawVideo" in interface_name:
                if logger:
                    logger.info(f"  [{interface_name}] Skipped (stub mode)")
                continue
            # For spike sorting, stub mode is handled within the interface

        interface_class.download_data(
            one=one,
            eid=eid,
            logger=logger,
            **kwargs
        )

    download_time = time.time() - download_start

    # Calculate total size
    total_size_bytes = 0
    if paths["session_folder"].exists():
        for file_path in paths["session_folder"].rglob("*"):
            if file_path.is_file():
                total_size_bytes += file_path.stat().st_size

    total_size_gb = total_size_bytes / (1024**3)

    if logger:
        logger.info(f"Download step completed in {download_time:.2f}s")
        logger.info(f"Total data size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return {
        "download_time": download_time,
        "num_datasets": len(interfaces_to_download),
        "total_size_bytes": total_size_bytes,
        "total_size_gb": total_size_gb,
    }

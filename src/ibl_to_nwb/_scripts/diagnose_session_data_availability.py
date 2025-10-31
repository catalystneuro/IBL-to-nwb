import logging
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
from one.api import ONE

from ibl_to_nwb.fixtures.load_fixtures import load_bwm_df, get_probe_name_to_probe_id_dict
from ibl_to_nwb.datainterfaces import (
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


# Target revision for spike sorting data (used in PROCESSED conversions)
TARGET_REVISION = "2025-05-06"

# Data source descriptions for reporting
# Note: QC filtering is handled internally by each interface's check_availability() method
# These map to the interface check_availability() methods called in check_session_data_availability()
#
# Note: Availability is now checked using interface methods, not hardcoded patterns.
# See each interface's check_availability() method for exact logic.
DATA_SOURCE_DESCRIPTIONS = {
    # Core behavioral data
    "trials": "Trials data (BrainwideMapTrialsInterface)",
    "wheel": "Wheel movement data (WheelInterface)",
    "licks": "Lick times (LickInterface)",

    # Passive period data (now separated into three interfaces)
    "passive_intervals": "Passive period timing intervals (PassiveIntervalsInterface)",
    "passive_replay": "Passive replay stimuli (PassiveReplayStimInterface)",
    "passive_rfm": "Passive receptive field mapping (PassiveRFMInterface)",

    # Probe-based data
    "spike_sorting": f"Spike sorting from revision {TARGET_REVISION} (IblSortingInterface)",
    "probe_localization": "Probe anatomical localization (IblAnatomicalLocalizationInterface)",

    # Camera-based data (per camera)
    "video_left": "Left camera video (RawVideoInterface)",
    "video_right": "Right camera video (RawVideoInterface)",
    "video_body": "Body camera video (RawVideoInterface)",
    "pose_estimation_left": "Pose estimation - left camera (IblPoseEstimationInterface)",
    "pose_estimation_right": "Pose estimation - right camera (IblPoseEstimationInterface)",
    "pose_estimation_body": "Pose estimation - body camera (IblPoseEstimationInterface)",
    "pupil_tracking_left": "Pupil tracking - left camera (PupilTrackingInterface)",
    "pupil_tracking_right": "Pupil tracking - right camera (PupilTrackingInterface)",
    "roi_motion_energy_left": "ROI motion energy - left camera (RoiMotionEnergyInterface)",
    "roi_motion_energy_right": "ROI motion energy - right camera (RoiMotionEnergyInterface)",
    "roi_motion_energy_body": "ROI motion energy - body camera (RoiMotionEnergyInterface)",
}


def check_session_data_availability(eid: str, one: ONE) -> Dict:
    """Check data availability for a single session using interface methods.

    Note: QC filtering is handled internally by each interface's check_availability() method.

    Parameters
    ----------
    eid : str
        Session ID
    one : ONE
        ONE API instance

    Returns
    -------
    Dict
        Dictionary with session info and data availability
    """
    result = {
        "eid": eid,
        "subject": None,
        "date": None,
        "lab": None,
        "num_probes": 0,
        "probe_names": [],
        "single_probe": False,
        "data_sources": {},
        "missing_sources": [],
        "errors": [],
    }

    # Get session info - let it fail if session doesn't exist
    session_info = one.alyx.rest("sessions", "read", id=eid)
    result["subject"] = session_info.get("subject")
    result["date"] = session_info.get("start_time", "").split("T")[0]
    result["lab"] = session_info.get("lab")

    # Get probe insertions from fixture (fast, no Alyx query)
    probe_name_to_probe_id_dict = get_probe_name_to_probe_id_dict(eid)
    result["num_probes"] = len(probe_name_to_probe_id_dict)
    result["probe_names"] = list(probe_name_to_probe_id_dict.keys())
    result["single_probe"] = len(probe_name_to_probe_id_dict) == 1

    # Define interfaces to check using the new interface methods
    interfaces_to_check = [
        ("trials", BrainwideMapTrialsInterface, {}),
        ("wheel", WheelInterface, {}),
        ("licks", LickInterface, {}),
        ("passive_intervals", PassiveIntervalsInterface, {}),
        ("passive_replay", PassiveReplayStimInterface, {}),
        ("passive_rfm", PassiveRFMInterface, {}),
        ("spike_sorting", IblSortingInterface, {}),
        ("probe_localization", IblAnatomicalLocalizationInterface, {}),
    ]

    # Add camera-based interfaces for each camera
    for camera_view in ["left", "right", "body"]:
        camera_name = f"{camera_view}Camera"  # e.g., "leftCamera"
        # Note: RawVideoInterface expects just "left", others expect "leftCamera"

        # All cameras have video, pose, and motion energy
        interfaces_to_check.extend([
            (f"video_{camera_view}", RawVideoInterface, {"camera_name": camera_view}),  # Just "left"
            (f"pose_estimation_{camera_view}", IblPoseEstimationInterface, {"camera_name": camera_name}),  # "leftCamera"
            (f"roi_motion_energy_{camera_view}", RoiMotionEnergyInterface, {"camera_name": camera_name}),  # "leftCamera"
        ])

        # Pupil tracking - only for left/right cameras (body camera doesn't capture eyes)
        if camera_view in ["left", "right"]:
            interfaces_to_check.append(
                (f"pupil_tracking_{camera_view}", PupilTrackingInterface, {"camera_name": camera_name})
            )

    # Check each interface using its check_availability() method
    # No need to pass revision explicitly - each interface has its own REVISION class attribute
    # This avoids slow one.list_revisions() calls
    for source_name, interface_class, kwargs in interfaces_to_check:
        availability = interface_class.check_availability(
            one=one,
            eid=eid,
            # Don't pass revision - let interface use its own REVISION class attribute
            # This prevents slow one.list_revisions() calls
            **kwargs
        )
        is_available = availability.get("available", False)
        result["data_sources"][source_name] = is_available

        if not is_available:
            result["missing_sources"].append(source_name)

    # Note: QC filtering is handled internally by each interface's check_availability() method
    # No need to add separate QC columns - availability already reflects QC status

    return result


def result_to_csv_row(result: Dict) -> Dict:
    """Convert a result dictionary to a flat CSV row.

    Parameters
    ----------
    result : Dict
        Result from check_session_data_availability()

    Returns
    -------
    Dict
        Flat dictionary suitable for CSV writing
    """
    row = {
        "eid": result["eid"],
        "subject": result["subject"],
        "date": result["date"],
        "lab": result["lab"],
        "num_probes": result["num_probes"],
        "probe_names": ", ".join(result["probe_names"]),
        "single_probe": result["single_probe"],
        "num_missing": len(result["missing_sources"]),
        "missing_sources": ", ".join(result["missing_sources"]),
    }

    # Add columns for each data source (availability only - QC is handled internally)
    for source_name in DATA_SOURCE_DESCRIPTIONS.keys():
        row[f"has_{source_name}"] = result["data_sources"].get(source_name, False)

    if result["errors"]:
        row["errors"] = "; ".join(result["errors"])

    return row


def diagnose_sessions(eids: List[str], one: ONE, output_path: Path = None) -> pd.DataFrame:
    """Diagnose multiple sessions and stream results directly to CSV file.

    This version writes results as they are processed, rather than accumulating
    them in memory. This provides:
    - Lower memory usage (only one session result in memory at a time)
    - Progress preservation (partial results saved if script crashes)
    - Ability to monitor progress by watching the output file

    Parameters
    ----------
    eids : List[str]
        List of session IDs
    one : ONE
        ONE API instance
    output_path : Path, optional
        Path to save CSV report. If None, results are not saved (only returned).

    Returns
    -------
    pd.DataFrame
        DataFrame with diagnosis results (loaded from saved CSV if output_path provided)
    """
    total = len(eids)

    print(f"Diagnosing {total} sessions...")
    if output_path:
        print(f"Streaming results to: {output_path}")
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
    print()

    # Get fieldnames from first result to set up CSV writer
    # Process first session to determine column structure
    if eids and output_path:
        first_result = check_session_data_availability(eids[0], one)
        first_row = result_to_csv_row(first_result)
        fieldnames = list(first_row.keys())

        # Open CSV file and keep it open for streaming
        csvfile = open(output_path, 'w', newline='')
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        # Write first row
        writer.writerow(first_row)

        # Print progress for first session
        print(f"[  1/{total}] ({100/total:5.1f}%) Checking {eids[0]}...", end="", flush=True)
        num_missing = len(first_result["missing_sources"])
        if num_missing == 0:
            print(" ✓ All data available")
        else:
            print(f" ⚠ {num_missing} missing")

        # Process remaining sessions
        start_idx = 1
    else:
        csvfile = None
        writer = None
        start_idx = 0

    for i, eid in enumerate(eids[start_idx:], start_idx + 1):
        # Calculate progress percentage
        progress_pct = (i / total) * 100

        # Print progress with percentage and counts
        print(f"[{i:3d}/{total}] ({progress_pct:5.1f}%) Checking {eid}...", end="", flush=True)

        result = check_session_data_availability(eid, one)

        # Convert to CSV row and write immediately if output path provided
        if writer:
            row = result_to_csv_row(result)
            writer.writerow(row)  # Write immediately to CSV (streaming!)

        # Print summary on same line
        num_missing = len(result["missing_sources"])
        if num_missing == 0:
            print(" ✓ All data available")
        else:
            print(f" ⚠ {num_missing} missing")

        # Print milestone markers every 50 sessions
        if i % 50 == 0:
            print(f"\n--- Completed {i}/{total} sessions ({progress_pct:.1f}%) ---\n")

    # Close CSV file
    if csvfile:
        csvfile.close()

    # Load and return the DataFrame from the saved CSV
    if output_path:
        print(f"\nResults saved to: {output_path}")
        df = pd.read_csv(output_path)
    else:
        # If no output path, we don't have the data anymore (streaming only)
        df = pd.DataFrame()

    return df


def print_summary(df: pd.DataFrame):
    """Print summary statistics."""
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total = len(df)
    print(f"Total sessions: {total}")
    print()

    # Probe statistics
    print("Probe Statistics:")
    single_probe = df["single_probe"].sum()
    multi_probe = total - single_probe
    print(f"  Single-probe sessions: {single_probe} ({single_probe/total*100:.1f}%)")
    print(f"  Multi-probe sessions: {multi_probe} ({multi_probe/total*100:.1f}%)")
    print()

    # Data availability
    print("Data Availability:")
    for source_name, description in DATA_SOURCE_DESCRIPTIONS.items():
        col_name = f"has_{source_name}"
        if col_name in df.columns:
            available = df[col_name].sum()
            pct = available / total * 100
            status = "✓" if pct > 90 else "⚠" if pct > 50 else "✗"
            print(f"  {status} {description:60s}: {available:3d}/{total} ({pct:5.1f}%)")

    print()

    # Missing data patterns
    if "missing_sources" in df.columns:
        missing_counts = df["missing_sources"].str.split(", ").explode().value_counts()
        if not missing_counts.empty:
            print("Most Commonly Missing:")
            for source, count in missing_counts.head(10).items():
                if source:  # Skip empty
                    pct = count / total * 100
                    print(f"  - {source:30s}: {count:3d} sessions ({pct:5.1f}%)")

    print()

    # QC vs Availability Comparison
    # Only show for data sources that have QC information
    qc_sources = [
        ("video_left", "Video Left"),
        ("video_right", "Video Right"),
        ("video_body", "Video Body"),
        ("dlc_left", "DLC Left"),
        ("dlc_right", "DLC Right"),
        ("dlc_body", "DLC Body"),
        ("lightning_pose_left", "Lightning Pose Left"),
        ("lightning_pose_right", "Lightning Pose Right"),
        ("lightning_pose_body", "Lightning Pose Body"),
        ("pose_estimation_left", "Pose Estimation Left"),
        ("pose_estimation_right", "Pose Estimation Right"),
        ("pose_estimation_body", "Pose Estimation Body"),
    ]

    print("QC vs File Availability (PASS/WARNING only):")
    for source_name, display_name in qc_sources:
        has_col = f"has_{source_name}"
        usable_col = f"usable_{source_name}"

        if has_col in df.columns and usable_col in df.columns:
            files_exist = df[has_col].sum()
            qc_usable = df[usable_col].sum()
            files_pct = files_exist / total * 100
            qc_pct = qc_usable / total * 100

            print(
                f"  {display_name:30s}: "
                f"Files {files_exist:3d} ({files_pct:5.1f}%), "
                f"QC Usable {qc_usable:3d} ({qc_pct:5.1f}%)"
            )


def main():
    """Run diagnosis on all sessions and save to repo directory."""

    # Output configuration
    repo_dir = Path("/home/heberto/development/ibl_conversion")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = repo_dir / f"session_diagnosis_report_{timestamp}.csv"

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("=" * 80)
    print("IBL SESSION DATA AVAILABILITY DIAGNOSTIC")
    print("=" * 80)
    print(f"Output will be saved to: {output_path}")
    print()

    # Initialize ONE
    print("Connecting to ONE API...")
    one = ONE(
        base_url="https://openalyx.internationalbrainlab.org",
        password="international",
        silent=True,
    )

    # Load BWM fixtures to get EID list
    print("Loading Brain-Wide Map session fixtures...")
    bwm_df = load_bwm_df()
    eids = bwm_df['eid'].unique().tolist()

    print(f"Found {len(eids)} unique BWM sessions to check")
    print()

    # Run diagnosis
    df = diagnose_sessions(eids, one, output_path=output_path)

    # Print summary
    print_summary(df)

    print()
    print("=" * 80)
    print(f"Report saved to: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()

"""
Diagnostic tool to check data availability for IBL Brain-Wide Map sessions.

This script scans the BWM fixture sessions (459 sessions) to determine:
1. Number of probes per session
2. Availability of key data sources (lightning pose, DLC, videos, etc.)
3. Missing data for conversion

The script uses the BWM fixtures (bwm_df.pqt) which contains the curated list
of sessions for the Brain-Wide Map project.

Usage:
    python diagnose_session_data_availability.py

Output:
    Saves timestamped CSV report to /home/heberto/development/ibl_conversion/
    Example: session_diagnosis_report_20251022_143015.csv
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
from one.api import ONE

# Add parent directory to path to import fixtures
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ibl_to_nwb.fixtures.load_fixtures import load_bwm_df


# Target revision for spike sorting data (used in PROCESSED conversions)
TARGET_REVISION = "2024-05-06"

# Data sources to check - organized by conversion type
# These correspond to actual data interfaces used in conversions:
#
# RAW conversion (raw.py):
#   - IblSpikeGLXConverter (raw ephys AP/LF bands)
#   - RawVideoInterface (left/right/body camera videos)
#   - IblAnatomicalLocalizationInterface (probe insertions with localization)
#
# PROCESSED conversion (processed.py):
#   - IblSortingInterface (spike times, clusters, etc. from TARGET_REVISION)
#   - BrainwideMapTrialsInterface (trials data)
#   - WheelInterface (wheel movement)
#   - PassivePeriodDataInterface (passive stimuli presentations)
#   - LickInterface (lick times)
#   - IblPoseEstimationInterface (lightning pose or DLC tracking)
#   - PupilTrackingInterface (pupil diameter/position from camera features)
#   - RoiMotionEnergyInterface (motion energy from camera ROIs)
#
# Note on revisions:
#   - Some data (like spike sorting) requires specific revision filtering
#   - Other data (like videos, pose estimation) is not versioned
#   - We check both to capture actual availability
DATA_SOURCES = {
    # ========================================================================
    # RAW CONVERSION DATA SOURCES
    # ========================================================================
    "raw_ephys_ap": {
        "description": "Raw AP band electrophysiology (IblSpikeGLXConverter)",
        "patterns": [".imec", ".ap."],  # Matches both .ap.cbin and .ap.bin
    },
    "raw_ephys_lf": {
        "description": "Raw LF band electrophysiology (IblSpikeGLXConverter)",
        "patterns": [".imec", ".lf."],  # Matches both .lf.cbin and .lf.bin
    },
    "probe_localization": {
        "description": "Probe insertions with anatomical localization (IblAnatomicalLocalizationInterface)",
        "check": "insertions",  # Special case: check via Alyx API for trajectory data
    },
    "video_left": {
        "description": "Left camera video (RawVideoInterface)",
        "patterns": ["leftCamera.raw.mp4"],
    },
    "video_right": {
        "description": "Right camera video (RawVideoInterface)",
        "patterns": ["rightCamera.raw.mp4"],
    },
    "video_body": {
        "description": "Body camera video (RawVideoInterface)",
        "patterns": ["bodyCamera.raw.mp4"],
    },

    # ========================================================================
    # PROCESSED CONVERSION DATA SOURCES
    # ========================================================================
    "spike_sorting": {
        "description": f"Spike sorting from revision {TARGET_REVISION} (IblSortingInterface)",
        "patterns": [f"#{TARGET_REVISION}#", "spikes.times"],
        "use_revision": True,  # This data MUST be from specific revision
    },
    "trials": {
        "description": "Trials data (BrainwideMapTrialsInterface)",
        "patterns": ["trials.table"],
    },
    "wheel": {
        "description": "Wheel movement data (WheelInterface)",
        "patterns": ["_ibl_wheel"],
    },
    "licks": {
        "description": "Lick times (LickInterface)",
        "patterns": ["licks.times"],
    },
    "passive_stimuli": {
        "description": "Passive period stimuli presentations (PassivePeriodDataInterface)",
        "patterns": ["_ibl_passiveGabor", "_ibl_passivePeriods"],
    },

    # ========================================================================
    # POSE ESTIMATION - Combined checks (either Lightning Pose OR DLC)
    # ========================================================================
    "pose_estimation_left": {
        "description": "Pose estimation - left camera (Lightning Pose or DLC)",
        "check": "pose_either",  # Special: check if EITHER lightning OR dlc exists
        "patterns_any": [["leftCamera.lightningPose"], ["leftCamera.dlc"]],
    },
    "pose_estimation_right": {
        "description": "Pose estimation - right camera (Lightning Pose or DLC)",
        "check": "pose_either",  # Special: check if EITHER lightning OR dlc exists
        "patterns_any": [["rightCamera.lightningPose"], ["rightCamera.dlc"]],
    },

    # Individual pose tracking methods (for detailed breakdown)
    "lightning_pose_left": {
        "description": "Lightning Pose - left camera",
        "patterns": ["leftCamera.lightningPose"],
    },
    "lightning_pose_right": {
        "description": "Lightning Pose - right camera",
        "patterns": ["rightCamera.lightningPose"],
    },
    "dlc_left": {
        "description": "DeepLabCut - left camera",
        "patterns": ["leftCamera.dlc"],
    },
    "dlc_right": {
        "description": "DeepLabCut - right camera",
        "patterns": ["rightCamera.dlc"],
    },

    # ========================================================================
    # OTHER PROCESSED DATA
    # ========================================================================
    "pupil_tracking": {
        "description": "Pupil diameter/position (PupilTrackingInterface)",
        "patterns": ["Camera.features"],
    },
    "roi_motion_energy": {
        "description": "ROI motion energy from camera (RoiMotionEnergyInterface)",
        "patterns": ["ROIMotionEnergy.npy"],
    },
}


def check_session_data_availability(eid: str, one: ONE) -> Dict:
    """Check data availability for a single session.

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

    try:
        # Get session info
        session_info = one.alyx.rest("sessions", "read", id=eid)
        result["subject"] = session_info.get("subject")
        result["date"] = session_info.get("start_time", "").split("T")[0]
        result["lab"] = session_info.get("lab")

        # Get probe insertions
        insertions = one.alyx.rest("insertions", "list", session=eid)
        result["num_probes"] = len(insertions)
        result["probe_names"] = [ins["name"] for ins in insertions]
        result["single_probe"] = len(insertions) == 1

        # Get all datasets - check both with and without revision filter
        datasets_no_rev = one.list_datasets(eid)
        dataset_strings_no_rev = [str(d) for d in datasets_no_rev]

        # Also get datasets with revision filter for revision-specific data
        datasets_with_rev = one.list_datasets(eid, revision=TARGET_REVISION)
        dataset_strings_with_rev = [str(d) for d in datasets_with_rev]

        # Check each data source
        for source_name, source_info in DATA_SOURCES.items():
            check_type = source_info.get("check")

            if check_type == "insertions":
                # Special case: probe insertions with localization from Alyx API
                result["data_sources"][source_name] = result["num_probes"] > 0

            elif check_type == "pose_either":
                # Special case: Check if ANY of the pattern groups are found
                # Used for pose estimation where either Lightning Pose OR DLC is acceptable
                patterns_any = source_info["patterns_any"]
                found = any(
                    all(
                        any(pattern in ds for ds in dataset_strings_no_rev)
                        for pattern in pattern_group
                    )
                    for pattern_group in patterns_any
                )
                result["data_sources"][source_name] = found

                if not found:
                    result["missing_sources"].append(source_name)

            else:
                # Normal pattern check
                # Use revision filter if specified, otherwise check without revision
                use_revision = source_info.get("use_revision", False)
                dataset_strings = dataset_strings_with_rev if use_revision else dataset_strings_no_rev

                patterns = source_info["patterns"]
                found = all(
                    any(pattern in ds for ds in dataset_strings)
                    for pattern in patterns
                )
                result["data_sources"][source_name] = found

                if not found:
                    result["missing_sources"].append(source_name)

    except Exception as e:
        result["errors"].append(str(e))

    return result


def diagnose_sessions(eids: List[str], one: ONE, output_path: Path = None) -> pd.DataFrame:
    """Diagnose multiple sessions and create a report.

    Parameters
    ----------
    eids : List[str]
        List of session IDs
    one : ONE
        ONE API instance
    output_path : Path, optional
        Path to save CSV report

    Returns
    -------
    pd.DataFrame
        DataFrame with diagnosis results
    """
    results = []
    total = len(eids)

    print(f"Diagnosing {total} sessions...")
    print()

    for i, eid in enumerate(eids, 1):
        # Calculate progress percentage
        progress_pct = (i / total) * 100

        # Print progress with percentage and counts
        print(f"[{i:3d}/{total}] ({progress_pct:5.1f}%) Checking {eid}...", end="", flush=True)

        result = check_session_data_availability(eid, one)
        results.append(result)

        # Print summary on same line
        num_missing = len(result["missing_sources"])
        if num_missing == 0:
            print(" ✓ All data available")
        else:
            print(f" ⚠ {num_missing} missing")

        # Print milestone markers every 50 sessions
        if i % 50 == 0:
            print(f"\n--- Completed {i}/{total} sessions ({progress_pct:.1f}%) ---\n")

    # Convert to DataFrame
    rows = []
    for result in results:
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

        # Add columns for each data source
        for source_name in DATA_SOURCES.keys():
            row[f"has_{source_name}"] = result["data_sources"].get(source_name, False)

        if result["errors"]:
            row["errors"] = "; ".join(result["errors"])

        rows.append(row)

    df = pd.DataFrame(rows)

    # Save to CSV if requested
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"\nReport saved to: {output_path}")

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
    for source_name, source_info in DATA_SOURCES.items():
        col_name = f"has_{source_name}"
        if col_name in df.columns:
            available = df[col_name].sum()
            pct = available / total * 100
            status = "✓" if pct > 90 else "⚠" if pct > 50 else "✗"
            print(f"  {status} {source_info['description']:60s}: {available:3d}/{total} ({pct:5.1f}%)")

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

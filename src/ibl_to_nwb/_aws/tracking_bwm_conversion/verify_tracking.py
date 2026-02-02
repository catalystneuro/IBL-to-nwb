#!/usr/bin/env python3
"""Verify DANDI upload status and update tracking.json in place.

This script:
  1. Creates tracking.json from bwm_df.pqt if it doesn't exist
  2. Queries DANDI API to get list of uploaded files
  3. Updates tracking.json in place with verification status
  4. Provides query modes for different use cases

Terminology:
  "Incomplete" = a session where at least one file (raw or processed) is missing from DANDI

Usage:
    # Verify and update tracking.json (creates it if needed)
    python verify_tracking.py

    # Show summary only (no DANDI query, reads tracking.json)
    python verify_tracking.py --summary

    # Get incomplete session ranges for re-launch (e.g., "3-4 28-30")
    python verify_tracking.py --incomplete-ranges

    # Get incomplete session EIDs (one per line)
    python verify_tracking.py --incomplete-eids
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dandi.dandiapi import DandiAPIClient

from ibl_to_nwb.utils.subject_handling import sanitize_subject_id_for_dandi

# =============================================================================
# CONFIGURATION - Edit these values to change the target dandiset
# =============================================================================
DANDISET_ID = "000409"
DANDI_INSTANCE = "dandi"  # "dandi" for production, "dandi-sandbox" for testing
# =============================================================================


def init_tracking(output_dir: Path) -> dict:
    """Initialize tracking.json from bwm_df.pqt fixture.

    Called automatically if tracking.json doesn't exist.

    Returns
    -------
    dict
        The created tracking data.
    """
    bwm_df_path = output_dir.parent.parent / "fixtures" / "bwm_df.pqt"

    if not bwm_df_path.exists():
        raise FileNotFoundError(f"BWM fixture not found: {bwm_df_path}")

    print(f"Initializing tracking from: {bwm_df_path}")
    df = pd.read_parquet(bwm_df_path)
    print(f"  Total rows: {len(df)}, Unique EIDs: {df['eid'].nunique()}")

    # Deduplicate by EID
    df_dedup = df.drop_duplicates(subset=["eid"], keep="first")
    eid_to_subject = df_dedup.set_index("eid")["subject"].to_dict()

    # Generate session entries
    sessions = []
    unique_eids = []

    for index, eid in enumerate(df_dedup["eid"].tolist()):
        subject = eid_to_subject[eid]
        subject_sanitized = sanitize_subject_id_for_dandi(subject)

        raw_path = f"sub-{subject_sanitized}/sub-{subject_sanitized}_ses-{eid}_desc-raw_ecephys.nwb"
        processed_path = f"sub-{subject_sanitized}/sub-{subject_sanitized}_ses-{eid}_desc-processed_behavior+ecephys.nwb"

        sessions.append({
            "index": index,
            "eid": eid,
            "subject": subject,
            "subject_sanitized": subject_sanitized,
            "raw_path": raw_path,
            "raw_verified": False,
            "processed_path": processed_path,
            "processed_verified": False,
        })
        unique_eids.append(eid)

    # Create tracking data
    tracking_data = {
        "metadata": {
            "created": datetime.now(timezone.utc).isoformat(),
            "last_verified": None,
            "dandiset_id": DANDISET_ID,
            "dandi_instance": DANDI_INSTANCE,
            "source_fixture": bwm_df_path.name,
        },
        "summary": {
            "total_sessions": len(sessions),
            "complete": 0,
            "incomplete": len(sessions),
            "raw_verified": 0,
            "processed_verified": 0,
        },
        "sessions": sessions,
    }

    # Write tracking.json
    output_dir.mkdir(parents=True, exist_ok=True)
    tracking_path = output_dir / "tracking.json"
    with open(tracking_path, "w") as f:
        json.dump(tracking_data, f, indent=2)

    # Write bwm_session_eids.json (for launch script)
    eids_path = output_dir / "bwm_session_eids.json"
    with open(eids_path, "w") as f:
        json.dump({"total": len(unique_eids), "eids": unique_eids}, f, indent=2)

    print(f"  Created tracking.json with {len(sessions)} sessions")
    return tracking_data


def query_dandi_files() -> list[str]:
    """Query DANDI API for list of uploaded NWB files."""
    print(f"Querying DANDI {DANDI_INSTANCE} for dandiset {DANDISET_ID}...")

    if DANDI_INSTANCE == "dandi-sandbox":
        api_url = "https://api-staging.dandiarchive.org/api"
    else:
        api_url = "https://api.dandiarchive.org/api"

    client = DandiAPIClient(api_url=api_url)
    dandiset = client.get_dandiset(DANDISET_ID, "draft")

    file_paths = [asset.path for asset in dandiset.get_assets() if asset.path.endswith(".nwb")]
    print(f"Found {len(file_paths)} NWB files on DANDI")
    return file_paths


def load_tracking(tracking_path: Path) -> dict:
    """Load tracking.json, creating it if it doesn't exist."""
    if not tracking_path.exists():
        return init_tracking(tracking_path.parent)

    with open(tracking_path, "r") as f:
        return json.load(f)


def save_tracking(tracking_path: Path, tracking_data: dict) -> None:
    """Save tracking.json."""
    with open(tracking_path, "w") as f:
        json.dump(tracking_data, f, indent=2)


def verify_and_update(tracking_path: Path, dandi_files: list[str]) -> dict:
    """Verify uploads and update tracking.json in place."""
    tracking_data = load_tracking(tracking_path)
    sessions = tracking_data["sessions"]

    # Verify each session
    dandi_files_set = set(dandi_files)
    raw_verified_count = 0
    processed_verified_count = 0
    complete_count = 0

    for session in sessions:
        raw_exists = session["raw_path"] in dandi_files_set
        processed_exists = session["processed_path"] in dandi_files_set

        session["raw_verified"] = raw_exists
        session["processed_verified"] = processed_exists

        if raw_exists:
            raw_verified_count += 1
        if processed_exists:
            processed_verified_count += 1
        if raw_exists and processed_exists:
            complete_count += 1

    # Update summary and metadata
    total = len(sessions)
    tracking_data["summary"] = {
        "total_sessions": total,
        "complete": complete_count,
        "incomplete": total - complete_count,
        "raw_verified": raw_verified_count,
        "processed_verified": processed_verified_count,
    }
    tracking_data["metadata"]["last_verified"] = datetime.now(timezone.utc).isoformat()
    tracking_data["metadata"]["dandiset_id"] = DANDISET_ID
    tracking_data["metadata"]["dandi_instance"] = DANDI_INSTANCE

    save_tracking(tracking_path, tracking_data)
    print(f"Updated tracking.json")
    return tracking_data


def print_summary(tracking_data: dict) -> None:
    """Print verification summary."""
    summary = tracking_data["summary"]
    metadata = tracking_data["metadata"]

    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    print(f"Dandiset: {metadata.get('dandiset_id', 'N/A')} ({metadata.get('dandi_instance', 'N/A')})")
    print(f"Last verified: {metadata.get('last_verified', 'Never')}")
    print("-" * 70)
    print(f"Total sessions:    {summary['total_sessions']}")
    print(f"Complete:          {summary['complete']} ({100*summary['complete']/summary['total_sessions']:.1f}%)")
    print(f"Incomplete:        {summary['incomplete']}")
    print("-" * 70)
    print(f"RAW verified:      {summary['raw_verified']}/{summary['total_sessions']}")
    print(f"PROCESSED verified:{summary['processed_verified']}/{summary['total_sessions']}")
    print("=" * 70)


def get_incomplete_ranges(tracking_data: dict) -> list[str]:
    """Get incomplete session indices as ranges for launch script.

    "Incomplete" means at least one file (raw or processed) is missing from DANDI.

    Returns ranges in Python-style slicing (end exclusive), e.g., ["3-4", "28-30"].
    Consecutive indices are grouped into single ranges.
    """
    incomplete_indices = [
        s["index"] for s in tracking_data["sessions"]
        if not (s["raw_verified"] and s["processed_verified"])
    ]

    if not incomplete_indices:
        return []

    # Group consecutive indices into ranges
    ranges = []
    start = incomplete_indices[0]
    end = start + 1

    for index in incomplete_indices[1:]:
        if index == end:
            end = index + 1
        else:
            ranges.append(f"{start}-{end}")
            start = index
            end = index + 1

    ranges.append(f"{start}-{end}")
    return ranges


def get_incomplete_eids(tracking_data: dict) -> list[str]:
    """Get EIDs of incomplete sessions.

    "Incomplete" means at least one file (raw or processed) is missing from DANDI.
    """
    return [
        s["eid"] for s in tracking_data["sessions"]
        if not (s["raw_verified"] and s["processed_verified"])
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify DANDI upload status")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--summary",
        action="store_true",
        help="Print verification summary from tracking.json (no DANDI query). Shows total/complete/incomplete counts.",
    )
    mode_group.add_argument(
        "--incomplete-ranges",
        action="store_true",
        help="Print indices of incomplete sessions (missing raw OR processed file on DANDI) as ranges, "
             "space-separated (e.g., '3-4 28-30 45-47'). "
             "Use with launch script: --range $(python verify_tracking.py --incomplete-ranges)",
    )
    mode_group.add_argument(
        "--incomplete-eids",
        action="store_true",
        help="Print EIDs of incomplete sessions (missing raw OR processed file on DANDI), one per line.",
    )

    args = parser.parse_args()

    # Paths
    script_dir = Path(__file__).parent
    tracking_path = script_dir / "tracking.json"

    # Query-only modes (no DANDI query needed, read from tracking.json)
    if args.summary:
        print_summary(load_tracking(tracking_path))
        return

    if args.incomplete_ranges:
        ranges = get_incomplete_ranges(load_tracking(tracking_path))
        if ranges:
            print(" ".join(ranges))
        return

    if args.incomplete_eids:
        for eid in get_incomplete_eids(load_tracking(tracking_path)):
            print(eid)
        return

    # Full verification - query DANDI and update tracking.json
    dandi_files = query_dandi_files()
    tracking_data = verify_and_update(tracking_path, dandi_files)

    print_summary(tracking_data)

    if tracking_data["summary"]["incomplete"] > 0:
        print(f"\nTo re-launch incomplete sessions:")
        print(f"  python verify_tracking.py --incomplete-ranges")
        print(f"  python ../launch_ec2_instances.py --profile ibl --range <RANGE>")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify DANDI upload status for BWM sessions.

This script:
  1. Builds a blank tracking dict from bwm_df.pqt (expected sessions + DANDI paths)
  2. Queries the DANDI API for currently uploaded NWB files
  3. Fills in verification status and saves tracking.json
  4. Outputs results based on the requested mode

Every invocation queries DANDI for the current state.

Terminology:
  "Incomplete" = a session where at least one file (raw or processed) is missing from DANDI

Usage:
    # Full verification with summary (default)
    python verify_tracking.py

    # Summary output only
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
from typing import NamedTuple

import pandas as pd
from dandi.dandiapi import DandiAPIClient

from ibl_to_nwb.utils.subject_handling import sanitize_subject_id_for_dandi

# =============================================================================
# CONFIGURATION
# =============================================================================


class DandiTarget(NamedTuple):
    dandiset_id: str
    api_url: str


DANDI_PRODUCTION = DandiTarget("000409", "https://api.dandiarchive.org/api")
DANDI_SANDBOX = DandiTarget("000409", "https://api-staging.dandiarchive.org/api")

TARGET = DANDI_PRODUCTION

SCRIPT_DIR = Path(__file__).parent
TRACKING_PATH = SCRIPT_DIR / "tracking.json"
BWM_FIXTURE_PATH = SCRIPT_DIR.parent.parent / "fixtures" / "bwm_df.pqt"

# =============================================================================


def build_tracking_dict() -> dict:
    """Build a blank tracking dictionary from the bwm_df.pqt fixture.

    Reads the parquet fixture, deduplicates by EID, and produces a tracking dict
    with the expected DANDI file paths for each session. All verification fields
    are initialized to False.

    The returned dict has the following structure::

        {
            "metadata": {
                "created": <ISO timestamp>,
                "last_verified": None,
                "dandiset_id": <str>,
                "source_fixture": <str>,
            },
            "summary": {
                "total_sessions": <int>,
                "complete": 0,
                "incomplete": <int>,
                "raw_verified": 0,
                "processed_verified": 0,
            },
            "sessions": [
                {
                    "index": <int>,
                    "eid": <str>,
                    "subject": <str>,
                    "subject_sanitized": <str>,
                    "raw_path": <str>,
                    "raw_verified": False,
                    "processed_path": <str>,
                    "processed_verified": False,
                },
                ...
            ],
        }

    Also writes bwm_session_eids.json alongside the script for use by the launch script.
    """
    if not BWM_FIXTURE_PATH.exists():
        raise FileNotFoundError(f"BWM fixture not found: {BWM_FIXTURE_PATH}")

    print(f"Building tracking from: {BWM_FIXTURE_PATH}")
    df = pd.read_parquet(BWM_FIXTURE_PATH)
    print(f"  Total rows: {len(df)}, Unique EIDs: {df['eid'].nunique()}")

    df_dedup = df.drop_duplicates(subset=["eid"], keep="first")
    eid_to_subject = df_dedup.set_index("eid")["subject"].to_dict()

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

    dandi_upload_state = {
        "metadata": {
            "created": datetime.now(timezone.utc).isoformat(),
            "last_verified": None,
            "dandiset_id": TARGET.dandiset_id,
            "source_fixture": BWM_FIXTURE_PATH.name,
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

    # Write bwm_session_eids.json (for launch script)
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    eids_path = SCRIPT_DIR / "bwm_session_eids.json"
    with open(eids_path, "w") as f:
        json.dump({"total": len(unique_eids), "eids": unique_eids}, f, indent=2)

    print(f"  Built tracking for {len(sessions)} sessions")
    return dandi_upload_state


def fill_upload_status(dandi_upload_state: dict, dandi_files: list[str]) -> dict:
    """Fill in the verification status of each session by comparing against DANDI.

    Mutates and returns the tracking dict with updated ``raw_verified``,
    ``processed_verified``, and summary counts.
    """
    sessions = dandi_upload_state["sessions"]
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

    total = len(sessions)
    dandi_upload_state["summary"] = {
        "total_sessions": total,
        "complete": complete_count,
        "incomplete": total - complete_count,
        "raw_verified": raw_verified_count,
        "processed_verified": processed_verified_count,
    }
    dandi_upload_state["metadata"]["last_verified"] = datetime.now(timezone.utc).isoformat()

    return dandi_upload_state


def print_summary(dandi_upload_state: dict) -> None:
    """Print verification summary."""
    summary = dandi_upload_state["summary"]
    metadata = dandi_upload_state["metadata"]

    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    print(f"Dandiset: {metadata.get('dandiset_id', 'N/A')}")
    print(f"Last verified: {metadata.get('last_verified', 'Never')}")
    print("-" * 70)
    print(f"Total sessions:    {summary['total_sessions']}")
    print(f"Complete:          {summary['complete']} ({100*summary['complete']/summary['total_sessions']:.1f}%)")
    print(f"Incomplete:        {summary['incomplete']}")
    print("-" * 70)
    print(f"RAW verified:      {summary['raw_verified']}/{summary['total_sessions']}")
    print(f"PROCESSED verified:{summary['processed_verified']}/{summary['total_sessions']}")
    print("=" * 70)


def get_incomplete_ranges(dandi_upload_state: dict) -> list[str]:
    """Get incomplete session indices as ranges for launch script.

    "Incomplete" means at least one file (raw or processed) is missing from DANDI.

    Returns ranges in Python-style slicing (end exclusive), e.g., ["3-4", "28-30"].
    Consecutive indices are grouped into single ranges.
    """
    incomplete_indices = [
        s["index"] for s in dandi_upload_state["sessions"]
        if not (s["raw_verified"] and s["processed_verified"])
    ]

    if not incomplete_indices:
        return []

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


def get_incomplete_eids(dandi_upload_state: dict) -> list[str]:
    """Get EIDs of incomplete sessions.

    "Incomplete" means at least one file (raw or processed) is missing from DANDI.
    """
    return [
        s["eid"] for s in dandi_upload_state["sessions"]
        if not (s["raw_verified"] and s["processed_verified"])
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify DANDI upload status")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--summary",
        action="store_true",
        help="Print verification summary. Shows total/complete/incomplete counts.",
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

    # Build blank tracking from fixture
    dandi_upload_state = build_tracking_dict()

    # Query DANDI and fill verification status
    print(f"Querying DANDI for dandiset {TARGET.dandiset_id}...")
    client = DandiAPIClient(api_url=TARGET.api_url)
    dandiset = client.get_dandiset(TARGET.dandiset_id, "draft")
    dandi_files = [asset.path for asset in dandiset.get_assets() if asset.path.endswith(".nwb")]
    print(f"Found {len(dandi_files)} NWB files on DANDI")

    dandi_upload_state = fill_upload_status(dandi_upload_state, dandi_files)

    # Save tracking.json
    with open(TRACKING_PATH, "w") as f:
        json.dump(dandi_upload_state, f, indent=2)
    print(f"Updated {TRACKING_PATH.name}")

    # Output based on requested mode
    if args.summary:
        print_summary(dandi_upload_state)
    elif args.incomplete_ranges:
        ranges = get_incomplete_ranges(dandi_upload_state)
        if ranges:
            print(" ".join(ranges))
    elif args.incomplete_eids:
        for eid in get_incomplete_eids(dandi_upload_state):
            print(eid)
    else:
        print_summary(dandi_upload_state)
        if dandi_upload_state["summary"]["incomplete"] > 0:
            print(f"\nTo re-launch incomplete sessions:")
            print(f"  python verify_tracking.py --incomplete-ranges")
            print(f"  python ../launch_ec2_instances.py --profile ibl --range <RANGE>")


if __name__ == "__main__":
    main()

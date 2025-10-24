"""Verify DANDI upload status and generate list of failed/missing sessions.

This script:
  1. Loads tracking.json with expected DANDI paths
  2. Queries DANDI API to get list of uploaded files
  3. Compares expected vs actual uploads
  4. Updates tracking.json with verification status
  5. Generates filtered JSON files for re-upload

Output files:
  - tracking_verified.json: Full tracking JSON with verification status
  - failed_sessions.json: Sessions with missing files (for re-upload)
  - failed_eids.json: List of EIDs in bwm_session_eids.json format

Usage:
    # Verify uploads on DANDI sandbox
    python verify_dandi_uploads.py --dandiset-id 217706 --dandi-instance dandi-sandbox

    # Verify uploads on DANDI production
    python verify_dandi_uploads.py --dandiset-id 000123 --dandi-instance dandi

    # Use existing DANDI file list (skip API query)
    python verify_dandi_uploads.py --dandiset-id 217706 --dandi-files-json dandi_files.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def query_dandi_files(dandiset_id: str, dandi_instance: str) -> list[str]:
    """Query DANDI API for list of uploaded files.

    Args:
        dandiset_id: DANDI dandiset ID (e.g., "217706")
        dandi_instance: DANDI instance ("dandi" or "dandi-sandbox")

    Returns:
        List of file paths relative to dandiset root
    """
    print(f"Querying DANDI {dandi_instance} for dandiset {dandiset_id}...")

    # Construct DANDI URL
    if dandi_instance == "dandi-sandbox":
        dandi_url = f"https://sandbox.dandiarchive.org/dandiset/{dandiset_id}/draft"
    else:
        dandi_url = f"https://dandiarchive.org/dandiset/{dandiset_id}/draft"

    # Run dandi ls with JSON output
    cmd = ["dandi", "ls", "--format", "json", dandi_url]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"dandi ls failed: {e.stderr}") from e

    # Parse JSON output (each line is a JSON object)
    file_paths = []
    for line in output.strip().split("\n"):
        if not line:
            continue

        try:
            file_info = json.loads(line)
            # Extract path relative to dandiset root
            # Format: {"path": "sub-NYU-11/sub-NYU-11_ses-..._desc-raw_ecephys.nwb", ...}
            path = file_info.get("path", "")
            if path and path.endswith(".nwb"):
                file_paths.append(path)
        except json.JSONDecodeError:
            print(f"WARNING: Failed to parse JSON line: {line}")
            continue

    print(f"Found {len(file_paths)} NWB files on DANDI")

    return file_paths


def verify_uploads(
    tracking_json_path: Path,
    dandi_files: list[str],
    output_dir: Path,
) -> None:
    """Verify uploads and generate filtered lists.

    Args:
        tracking_json_path: Path to tracking.json
        dandi_files: List of file paths on DANDI
        output_dir: Directory to write output files
    """
    # Load tracking JSON
    with open(tracking_json_path, "r") as f:
        tracking_data = json.load(f)

    sessions = tracking_data["sessions"]
    total_sessions = len(sessions)

    print(f"\nLoaded tracking data for {total_sessions} sessions")

    # Convert DANDI file list to set for fast lookup
    dandi_files_set = set(dandi_files)

    # Verify each session
    verified_sessions = []
    failed_sessions = []

    raw_success = 0
    processed_success = 0

    for session in sessions:
        eid = session["eid"]
        raw_path = session["raw_uploaded"]
        processed_path = session["processed_uploaded"]

        # Check if files exist on DANDI
        raw_exists = raw_path in dandi_files_set
        processed_exists = processed_path in dandi_files_set

        # Update verification status
        session_verified = session.copy()
        session_verified["raw_verified"] = raw_exists
        session_verified["processed_verified"] = processed_exists
        session_verified["complete"] = raw_exists and processed_exists

        verified_sessions.append(session_verified)

        # Track failures
        if not (raw_exists and processed_exists):
            failed_sessions.append(session_verified)

        # Update counters
        if raw_exists:
            raw_success += 1
        if processed_exists:
            processed_success += 1

    # Generate summary statistics
    complete_sessions = sum(1 for s in verified_sessions if s["complete"])
    failed_count = len(failed_sessions)

    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"Total sessions: {total_sessions}")
    print(f"Complete sessions (RAW + PROCESSED): {complete_sessions}")
    print(f"Incomplete sessions: {failed_count}")
    print(f"\nFile breakdown:")
    print(f"  RAW files uploaded: {raw_success}/{total_sessions}")
    print(f"  PROCESSED files uploaded: {processed_success}/{total_sessions}")
    print(f"  TOTAL files uploaded: {raw_success + processed_success}/{total_sessions * 2}")
    print("=" * 80)

    # Write verified tracking JSON
    tracking_verified = {
        "total": total_sessions,
        "complete": complete_sessions,
        "incomplete": failed_count,
        "sessions": verified_sessions,
    }

    output_dir.mkdir(parents=True, exist_ok=True)

    verified_path = output_dir / "tracking_verified.json"
    with open(verified_path, "w") as f:
        json.dump(tracking_verified, f, indent=2)
    print(f"\nWrote verified tracking to: {verified_path}")

    # Write failed sessions JSON (full details)
    if failed_sessions:
        failed_path = output_dir / "failed_sessions.json"
        failed_data = {
            "total": len(failed_sessions),
            "sessions": failed_sessions,
        }
        with open(failed_path, "w") as f:
            json.dump(failed_data, f, indent=2)
        print(f"Wrote failed sessions to: {failed_path}")

        # Write failed EIDs in bwm_session_eids.json format (for re-sharding)
        failed_eids = [s["eid"] for s in failed_sessions]
        failed_eids_data = {
            "total": len(failed_eids),
            "eids": failed_eids,
        }
        failed_eids_path = output_dir / "failed_eids.json"
        with open(failed_eids_path, "w") as f:
            json.dump(failed_eids_data, f, indent=2)
        print(f"Wrote failed EIDs to: {failed_eids_path}")
        print(f"\nTo re-run only failed sessions, use: --eids-json {failed_eids_path}")
    else:
        print("\n✓ All sessions successfully uploaded!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify DANDI upload status and generate failed sessions list."
    )
    parser.add_argument(
        "--dandiset-id",
        type=str,
        required=True,
        help="DANDI dandiset ID (e.g., 217706)",
    )
    parser.add_argument(
        "--dandi-instance",
        type=str,
        choices=["dandi", "dandi-sandbox"],
        default="dandi-sandbox",
        help="DANDI instance to query (default: dandi-sandbox)",
    )
    parser.add_argument(
        "--tracking-json",
        type=Path,
        default=None,
        help="Path to tracking.json (default: ./tracking.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for verified files (default: same as tracking.json)",
    )
    parser.add_argument(
        "--dandi-files-json",
        type=Path,
        default=None,
        help="Optional: Use existing DANDI file list instead of querying API",
    )

    args = parser.parse_args()

    # Default paths
    script_dir = Path(__file__).parent
    tracking_json_path = args.tracking_json or script_dir / "tracking.json"
    output_dir = args.output_dir or tracking_json_path.parent

    # Validate tracking.json exists
    if not tracking_json_path.exists():
        raise FileNotFoundError(
            f"Tracking JSON not found: {tracking_json_path}\n"
            f"Run generate_tracking_json.py first to create it."
        )

    # Get DANDI file list
    if args.dandi_files_json:
        print(f"Loading DANDI file list from: {args.dandi_files_json}")
        with open(args.dandi_files_json, "r") as f:
            dandi_files = json.load(f)
    else:
        dandi_files = query_dandi_files(args.dandiset_id, args.dandi_instance)

        # Optionally cache the file list
        cache_path = output_dir / "dandi_files_cache.json"
        with open(cache_path, "w") as f:
            json.dump(dandi_files, f, indent=2)
        print(f"Cached DANDI file list to: {cache_path}")

    # Verify uploads
    verify_uploads(
        tracking_json_path=tracking_json_path,
        dandi_files=dandi_files,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()

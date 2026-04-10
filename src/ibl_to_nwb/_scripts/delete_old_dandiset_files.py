#!/usr/bin/env python
"""
Delete old IBL NWB files from dandiset 000409 for a specific session (eid).

This script checks if an eid exists in the old dandiset and deletes all associated
NWB files (both raw and processed) to prepare for uploading new versions.

Usage:
    python delete_old_dandiset_files.py <eid> [--dry-run] [--token TOKEN]

Examples:
    # Dry run - just show what would be deleted
    python delete_old_dandiset_files.py a9138924-4395-4981-83d1-530f6ff7c8fc --dry-run

    # Actually delete
    python delete_old_dandiset_files.py a9138924-4395-4981-83d1-530f6ff7c8fc --token YOUR_DANDI_TOKEN
"""

import argparse
import os
import sys

from dandi.dandiapi import DandiAPIClient

DANDISET_ID = "000409"


def get_assets_for_eid(dandiset, eid: str) -> list:
    """
    Find all NWB assets in the dandiset that match the given eid.

    The old dandiset has files with patterns like:
    - sub-{subject}/sub-{subject}_ses-{eid}_behavior+ecephys+image.nwb
    - sub-{subject}/sub-{subject}_ses-{eid}_behavior+ecephys.nwb
    - sub-{subject}/sub-{subject}_ses-{eid}-processed-only_behavior.nwb
    - sub-{subject}/sub-{subject}_ses-{eid}-raw-only_ecephys+image.nwb
    """
    matching_assets = []

    for asset in dandiset.get_assets():
        if not asset.path.endswith(".nwb"):
            continue
        # Check if the eid appears in the file path
        if eid in asset.path:
            matching_assets.append(asset)

    return matching_assets


def delete_assets_for_eid(
    eid: str,
    token: str | None = None,
    dry_run: bool = True,
) -> dict:
    """
    Delete all NWB files for a given eid from dandiset 000409.

    Parameters
    ----------
    eid : str
        The IBL session UUID (e.g., 'a9138924-4395-4981-83d1-530f6ff7c8fc')
    token : str, optional
        DANDI API token. If not provided, will try to use DANDI_API_KEY env var.
    dry_run : bool, default True
        If True, only show what would be deleted without actually deleting.

    Returns
    -------
    dict
        Summary of the operation with keys: 'eid', 'found', 'deleted', 'files'
    """
    # Get token from parameter or environment
    if token is None:
        token = os.environ.get("DANDI_API_KEY")

    if token is None and not dry_run:
        raise ValueError(
            "DANDI API token is required for deletion. " "Provide --token or set DANDI_API_KEY environment variable."
        )

    # Connect to DANDI
    if token:
        client = DandiAPIClient(token=token)
    else:
        client = DandiAPIClient()

    dandiset = client.get_dandiset(DANDISET_ID, "draft")

    # Find matching assets
    matching_assets = get_assets_for_eid(dandiset, eid)

    result = {
        "eid": eid,
        "dandiset": DANDISET_ID,
        "found": len(matching_assets),
        "deleted": 0,
        "files": [],
        "dry_run": dry_run,
    }

    if not matching_assets:
        print(f"No files found for eid '{eid}' in dandiset {DANDISET_ID}")
        return result

    print(f"Found {len(matching_assets)} file(s) for eid '{eid}':")
    for asset in matching_assets:
        print(f"  - {asset.path}")
        result["files"].append(asset.path)

    if dry_run:
        print("\n[DRY RUN] No files were deleted. Use without --dry-run to delete.")
        return result

    # Confirm deletion
    print(f"\nDeleting {len(matching_assets)} file(s)...")

    for asset in matching_assets:
        try:
            asset.delete()
            result["deleted"] += 1
            print(f"  Deleted: {asset.path}")
        except Exception as e:
            print(f"  ERROR deleting {asset.path}: {e}")

    print(f"\nDeleted {result['deleted']}/{result['found']} files.")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Delete old IBL NWB files from dandiset 000409 for a specific eid.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "eid",
        help="IBL session UUID (e.g., 'a9138924-4395-4981-83d1-530f6ff7c8fc')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--token",
        help="DANDI API token (or set DANDI_API_KEY env var)",
    )

    args = parser.parse_args()

    # Validate eid format (basic UUID check)
    eid = args.eid.strip()
    if len(eid) != 36 or eid.count("-") != 4:
        print(f"Warning: '{eid}' doesn't look like a valid UUID format", file=sys.stderr)

    result = delete_assets_for_eid(
        eid=eid,
        token=args.token,
        dry_run=args.dry_run,
    )

    # Exit with appropriate code
    if result["found"] == 0:
        sys.exit(0)  # No files found - not an error
    elif result["dry_run"]:
        sys.exit(0)  # Dry run successful
    elif result["deleted"] == result["found"]:
        sys.exit(0)  # All files deleted
    else:
        sys.exit(1)  # Some files failed to delete


if __name__ == "__main__":
    main()

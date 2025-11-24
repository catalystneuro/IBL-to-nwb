#!/usr/bin/env python3
"""Generate a JSON file with unique session EIDs from bwm_df.pqt fixture.

The bwm_df.pqt fixture contains 699 rows but only 459 unique session EIDs
due to duplicates (e.g., multiple probes per session). This script extracts
the unique EIDs and saves them to bwm_session_eids.json for use in AWS runs.

This ensures each EC2 instance processes unique sessions without duplicates.

Usage:
    python generate_unique_eids.py

Output:
    bwm_session_eids.json - JSON file with format:
    {
        "total": 459,
        "eids": ["eid1", "eid2", ...]
    }
"""

import json
from pathlib import Path

import pandas as pd


def main():
    # Paths
    script_dir = Path(__file__).parent
    fixture_path = script_dir.parent / "fixtures" / "bwm_df.pqt"
    output_path = script_dir / "bwm_session_eids.json"

    # Load fixture
    print(f"Loading fixture from: {fixture_path}")
    df = pd.read_parquet(fixture_path)
    print(f"  Total rows: {len(df)}")
    print(f"  Unique EIDs: {df['eid'].nunique()}")
    print(f"  Duplicates: {len(df) - df['eid'].nunique()}")

    # Deduplicate by EID, keeping first occurrence
    df_dedup = df.drop_duplicates(subset=["eid"], keep="first")
    print(f"\nAfter deduplication: {len(df_dedup)} rows")

    # Extract unique EIDs as list
    unique_eids = df_dedup["eid"].tolist()

    # Save as JSON
    data = {"total": len(unique_eids), "eids": unique_eids}

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to: {output_path}")
    print(f"  Total unique EIDs: {len(unique_eids)}")
    print(f"  First 5 EIDs:")
    for i, eid in enumerate(unique_eids[:5]):
        print(f"    {i}: {eid}")

    # Verify
    with open(output_path, "r") as f:
        verify_data = json.load(f)
        assert verify_data["total"] == len(unique_eids), "Total mismatch"
        assert len(verify_data["eids"]) == len(unique_eids), "EID count mismatch"

    print("\n✓ Verification passed")


if __name__ == "__main__":
    main()

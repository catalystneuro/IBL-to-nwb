"""Generate tracking JSON for monitoring DANDI upload status.

This script extends bwm_session_eids.json with expected DANDI paths for each session.
The output JSON can be used to:
  1. Verify which files were successfully uploaded to DANDI
  2. Filter which sessions need re-upload after failures

Output format:
{
  "total": 459,
  "sessions": [
    {
      "eid": "6713a4a7-faed-4df2-acab-ee4e63326f8d",
      "subject": "NYU-11",
      "subject_sanitized": "NYU-11",
      "raw_uploaded": "sub-NYU-11/sub-NYU-11_ses-6713a4a7-faed-4df2-acab-ee4e63326f8d_desc-raw_ecephys.nwb",
      "raw_verified": false,
      "processed_uploaded": "sub-NYU-11/sub-NYU-11_ses-6713a4a7-faed-4df2-acab-ee4e63326f8d_desc-processed_behavior+ecephys.nwb",
      "processed_verified": false
    },
    ...
  ]
}

Notes:
- subject_sanitized replaces underscores with hyphens for DANDI compliance (e.g., "DY_013" -> "DY-013")
- raw_verified and processed_verified are initially false; verify_dandi_uploads.py will update them

Usage:
    python generate_tracking_json.py

Output:
    - tracking.json (in current directory)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ibl_to_nwb.utils.subject_handling import sanitize_subject_id_for_dandi


def generate_tracking_json(
    eids_json_path: Path,
    bwm_df_path: Path,
    output_path: Path,
) -> None:
    """Generate tracking JSON with expected DANDI paths.

    Args:
        eids_json_path: Path to bwm_session_eids.json
        bwm_df_path: Path to bwm_df.pqt (for EID → subject mapping)
        output_path: Path to write tracking.json
    """
    # Load unique session EIDs
    with open(eids_json_path, "r") as f:
        eids_data = json.load(f)

    all_eids = eids_data["eids"]
    total_sessions = len(all_eids)

    print(f"Loaded {total_sessions} unique session EIDs from {eids_json_path.name}")

    # Load BWM dataframe for EID → subject mapping
    df = pd.read_parquet(bwm_df_path)
    eid_to_subject = df[["eid", "subject"]].drop_duplicates().set_index("eid")["subject"].to_dict()

    print(f"Loaded EID → subject mapping from {bwm_df_path.name}")

    # Generate tracking entries
    sessions = []

    for eid in all_eids:
        subject = eid_to_subject.get(eid)

        if subject is None:
            print(f"WARNING: No subject found for EID {eid}, skipping...")
            continue

        # Sanitize subject ID for DANDI compliance (replace underscores with hyphens)
        subject_sanitized = sanitize_subject_id_for_dandi(subject)

        # Generate expected DANDI paths using BIDS naming convention
        # Format: sub-{subject}/sub-{subject}_ses-{eid}_desc-{raw|processed}_{modality}.nwb
        raw_path = f"sub-{subject_sanitized}/sub-{subject_sanitized}_ses-{eid}_desc-raw_ecephys.nwb"
        processed_path = f"sub-{subject_sanitized}/sub-{subject_sanitized}_ses-{eid}_desc-processed_behavior+ecephys.nwb"

        sessions.append({
            "eid": eid,
            "subject": subject,  # Keep original subject ID for reference
            "subject_sanitized": subject_sanitized,  # DANDI-compliant version
            "raw_uploaded": raw_path,
            "raw_verified": False,  # Will be updated by verify_dandi_uploads.py
            "processed_uploaded": processed_path,
            "processed_verified": False,  # Will be updated by verify_dandi_uploads.py
        })

    # Create output JSON
    tracking_data = {
        "total": len(sessions),
        "sessions": sessions,
    }

    # Write to file
    with open(output_path, "w") as f:
        json.dump(tracking_data, f, indent=2)

    print(f"\nGenerated tracking JSON with {len(sessions)} sessions")
    print(f"Output written to: {output_path}")
    print(f"\nExpected files on DANDI:")
    print(f"  - RAW files: {len(sessions)}")
    print(f"  - PROCESSED files: {len(sessions)}")
    print(f"  - TOTAL: {len(sessions) * 2} NWB files")


def main() -> None:
    # Paths relative to script location
    script_dir = Path(__file__).parent

    eids_json_path = script_dir / "bwm_session_eids.json"
    bwm_df_path = script_dir.parent / "fixtures" / "bwm_df.pqt"
    output_path = script_dir / "tracking.json"

    # Validate inputs
    if not eids_json_path.exists():
        raise FileNotFoundError(f"Missing {eids_json_path}")
    if not bwm_df_path.exists():
        raise FileNotFoundError(f"Missing {bwm_df_path}")

    generate_tracking_json(
        eids_json_path=eids_json_path,
        bwm_df_path=bwm_df_path,
        output_path=output_path,
    )


if __name__ == "__main__":
    main()

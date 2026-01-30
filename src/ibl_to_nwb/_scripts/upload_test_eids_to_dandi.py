#!/usr/bin/env python3
"""Reupload specific sessions to DANDI by EID.

This script launches EC2 instances for specific sessions identified by their EIDs.
Edit the configuration below and run the script.

Usage:
    uv run python src/ibl_to_nwb/_scripts/upload_eids.py
"""

import subprocess
import sys
from pathlib import Path

from ibl_to_nwb._aws.eid_utils import eids_to_ranges
# =============================================================================
# CONFIGURATION - Edit these values
# =============================================================================

SESSIONS_TO_REUPLOAD = [
    # Angelaki lab
    "8c33abef-3d3e-4d42-9f27-445e9def08f9",  # NYU-21, 2020-08-13, 2 probes
    "6ed57216-498d-48a6-b48b-a243a34710ea",  # NYU-39, 2021-05-10, 2 probes
    "35ed605c-1a1a-47b1-86ff-2b56144f55af",  # NYU-39, 2021-05-11, 2 probes
    "64e3fb86-928c-4079-865c-b364205b502e",  # NYU-46, 2021-06-25, 1 probe
    "f88d4dd4-ccd7-400e-9035-fa00be3bcfa8",  # NYU-37, 2021-01-26, 2 probes
    # Churchland lab
    "d2f5a130-b981-4546-8858-c94ae1da75ff",  # CSHL059, 2020-03-03, 2 probes
    "6f36868f-5cc1-450c-82fa-6b9829ce0cfe",  # UCLA035, 2022-02-18, 2 probes (churchlandlab_ucla)
]

PROFILE = "catalyst_neuro"
PROFILE = "ibl"
DANDI_INSTANCE = "dandi"
DANDISET_ID = "000409"
STUB_TEST = False
PROCESSED_ONLY = True
RAW_ONLY = False

# =============================================================================

# Convert EIDs to ranges
ranges = eids_to_ranges(SESSIONS_TO_REUPLOAD)

print(f"Sessions to reupload: {len(SESSIONS_TO_REUPLOAD)}")
for eid in SESSIONS_TO_REUPLOAD:
    print(f"  {eid}")
print(f"\nConverted to ranges: {ranges}")
print(f"\nConfiguration:")
print(f"  Profile: {PROFILE}")
print(f"  DANDI instance: {DANDI_INSTANCE}")
print(f"  Dandiset ID: {DANDISET_ID}")
print(f"  Stub test: {STUB_TEST}")
print(f"  Processed only: {PROCESSED_ONLY}")
print(f"  Raw only: {RAW_ONLY}")
print()

# Build the launch script path
launch_script = Path(__file__).parent.parent / "_aws" / "launch_ec2_instances.py"

# Launch each range
for range_str in ranges:
    cmd = [
        sys.executable,
        str(launch_script),
        "--profile", PROFILE,
        "--range", range_str,
        "--dandi-instance", DANDI_INSTANCE,
        "--dandiset-id", DANDISET_ID,
    ]

    if STUB_TEST:
        cmd.append("--stub-test")
    if PROCESSED_ONLY and not RAW_ONLY:
        cmd.append("--processed-only")
    elif RAW_ONLY:
        cmd.append("--raw-only")

    print(f"Launching range {range_str}...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"Failed to launch range {range_str}")
        sys.exit(result.returncode)

print("\nAll instances launched!")
print("\nMonitor with:")
print("  uv run python src/ibl_to_nwb/_aws/monitor.py --interval 30 --show-logs 10")

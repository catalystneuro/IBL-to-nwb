"""Generate all plots from the notebook scripts.

This script runs all individual plot scripts to regenerate all figures.
Figures are saved to the output_images/ directory.

Usage:
    uv run python generate_all_plots.py [--processed PATH] [--raw PATH]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from _common import get_default_processed_path, get_default_raw_path, get_output_dir

# Scripts that use processed NWB files
PROCESSED_SCRIPTS = [
    "plot_spike_raster_by_depth.py",
    "plot_units_scatter.py",
    "plot_waveform_visualization.py",
    "plot_trials_overview.py",
    "plot_psychometric_curves.py",
    "plot_reaction_time_contrast.py",
    "plot_trial_aligned_paw_speed.py",
    "plot_trial_aligned_pupil.py",
    "plot_trial_aligned_wheel.py",
    "plot_trial_aligned_licks.py",
]

# Scripts that use raw NWB files
RAW_SCRIPTS = [
    "plot_probe_anatomy_cosmos.py",
    "plot_probe_trajectories_ccf.py",
]


def run_script(script_name: str, nwbfile_path: str) -> bool:
    """Run a single plot script.

    Parameters
    ----------
    script_name : str
        Name of the script to run.
    nwbfile_path : str
        Path to the NWB file.

    Returns
    -------
    bool
        True if script succeeded, False otherwise.
    """
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name

    print(f"\n{'='*60}")
    print(f"Running: {script_name}")
    print(f"{'='*60}")

    result = subprocess.run(
        [sys.executable, str(script_path), nwbfile_path],
        cwd=script_dir,
    )

    if result.returncode != 0:
        print(f"FAILED: {script_name}")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Generate all plots from notebook scripts")
    parser.add_argument(
        "--processed",
        type=str,
        default=str(get_default_processed_path()),
        help="Path to processed NWB file",
    )
    parser.add_argument(
        "--raw",
        type=str,
        default=str(get_default_raw_path()),
        help="Path to raw NWB file",
    )
    parser.add_argument(
        "--skip-raw",
        action="store_true",
        help="Skip scripts that require raw NWB files",
    )
    parser.add_argument(
        "--skip-processed",
        action="store_true",
        help="Skip scripts that require processed NWB files",
    )
    args = parser.parse_args()

    print("Generating all plots")
    print(f"Processed NWB: {args.processed}")
    print(f"Raw NWB: {args.raw}")
    print(f"Output directory: {get_output_dir()}")

    results = {"success": [], "failed": []}

    # Run processed scripts
    if not args.skip_processed:
        print("\n" + "=" * 60)
        print("PROCESSED NWB SCRIPTS")
        print("=" * 60)
        for script in PROCESSED_SCRIPTS:
            if run_script(script, args.processed):
                results["success"].append(script)
            else:
                results["failed"].append(script)

    # Run raw scripts
    if not args.skip_raw:
        print("\n" + "=" * 60)
        print("RAW NWB SCRIPTS")
        print("=" * 60)
        for script in RAW_SCRIPTS:
            if run_script(script, args.raw):
                results["success"].append(script)
            else:
                results["failed"].append(script)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Successful: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")

    if results["failed"]:
        print("\nFailed scripts:")
        for script in results["failed"]:
            print(f"  - {script}")
        return 1

    print(f"\nAll figures saved to: {get_output_dir()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Execute stub conversions for a small batch of sessions on a single machine.

Each EC2 instance receives one JSON file that lists the session EIDs it owns.
This script opens the file, loops through its sessions sequentially, and
invokes the existing conversion helpers from the project.

Example usage (inside the `ibl_conversion` conda environment):

    python run_stub_assignment.py \
        --assignment-file /ebs/chunk-042.json \
        --base-folder /ebs \
        --revision 2024-05-06
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable

from one.api import ONE

from ibl_to_nwb._scripts.heberto_conversion_script import setup_logger
from ibl_to_nwb.conversion import (
    convert_processed_session,
    convert_raw_session,
    download_session_data,
)
from ibl_to_nwb.conversion.one_patches import apply_one_patches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run stub conversions for a single assignment file."
    )
    parser.add_argument(
        "--assignment-file",
        type=Path,
        required=True,
        help="Path to JSON file containing a list of session EIDs.",
    )
    parser.add_argument(
        "--base-folder",
        type=Path,
        default=Path("/ebs"),
        help="Root directory containing ibl_data, temporary_files, and nwbfiles.",
    )
    parser.add_argument(
        "--scratch-subdir",
        default="temporary_files",
        help="Subdirectory name under base-folder used for logs and scratch data.",
    )
    parser.add_argument(
        "--cache-subdir",
        default="ibl_data",
        help="Subdirectory name under base-folder used for ONE cache.",
    )
    parser.add_argument(
        "--nwb-subdir",
        default="nwbfiles",
        help="Subdirectory name under base-folder where NWB outputs are stored.",
    )
    parser.add_argument(
        "--revision",
        default="2024-05-06",
        help="ONE dataset revision to request (default mirrors local runs).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging verbosity for the wrapper script itself.",
    )
    return parser.parse_args()


def load_assignment(path: Path) -> list[str]:
    """Return the list of session EIDs from the JSON assignment file."""

    try:
        text = path.read_text()
    except FileNotFoundError as exc:
        raise SystemExit(f"Assignment file not found: {path}") from exc

    eids = json.loads(text)
    if not isinstance(eids, list):
        raise SystemExit(f"Assignment file is not a JSON list: {path}")
    if not eids:
        raise SystemExit(f"Assignment file is empty: {path}")
    return [str(eid) for eid in eids]


def configure_one(base_folder: Path) -> ONE:
    """Instantiate ONE SDK with patches and the desired cache directory."""

    one = ONE(
        base_url="https://openalyx.internationalbrainlab.org",
        cache_dir=base_folder / "ibl_data",
        silent=True,
    )
    apply_one_patches(one, logger=None)
    return one


def convert_session(
    eid: str,
    *,
    one: ONE,
    base_folder: Path,
    scratch_folder: Path,
    revision: str,
) -> None:
    """Run the full stub conversion (download + raw + processed) for one session."""

    log_file = scratch_folder / f"conversion_log_{eid}.log"
    logger = setup_logger(log_file)

    logger.info("Starting stub conversion for session %s", eid)

    download_session_data(
        eid=eid,
        one=one,
        redownload_data=False,
        stub_test=True,
        revision=revision,
        base_path=base_folder,
        scratch_path=scratch_folder,
        logger=logger,
    )

    convert_raw_session(
        eid=eid,
        one=one,
        stub_test=True,
        revision=revision,
        base_path=base_folder,
        scratch_path=scratch_folder,
        logger=logger,
        overwrite=False,
        redecompress_ephys=False,
    )

    convert_processed_session(
        eid=eid,
        one=one,
        stub_test=True,
        revision=revision,
        base_path=base_folder,
        scratch_path=scratch_folder,
        logger=logger,
        overwrite=False,
    )

    logger.info("Finished stub conversion for session %s", eid)


def ensure_directories(base: Path, subdirs: Iterable[str]) -> None:
    """Make sure the expected directory tree exists."""

    for name in subdirs:
        path = base / name
        path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
    )

    eids = load_assignment(args.assignment_file)
    logging.info("Loaded %d sessions from %s", len(eids), args.assignment_file)

    ensure_directories(
        args.base_folder,
        [args.scratch_subdir, args.cache_subdir, args.nwb_subdir],
    )

    one = configure_one(args.base_folder)

    scratch_folder = args.base_folder / args.scratch_subdir

    for index, eid in enumerate(eids, start=1):
        logging.info("Processing session %d/%d: %s", index, len(eids), eid)
        try:
            convert_session(
                eid,
                one=one,
                base_folder=args.base_folder,
                scratch_folder=scratch_folder,
                revision=args.revision,
            )
        except Exception:  # noqa: BLE001 - we want to log and continue
            logging.exception("Session %s failed", eid)
        else:
            logging.info("Session %s complete", eid)

    logging.info("All assignments processed.")


if __name__ == "__main__":
    sys.exit(main())

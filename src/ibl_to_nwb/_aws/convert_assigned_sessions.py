"""Convert assigned IBL session to NWB format.

This script is designed for distributed execution on EC2 instances. Each instance:
  1. Reads its SessionEID tag from IMDSv2
  2. Downloads source data from ONE API
  3. Converts to NWB (both raw and processed)
  4. Writes NWB files to /ebs/nwbfiles/full/sub-*/

Upload is handled separately by ec2_userdata_production.sh after conversion completes.

ONE SESSION PER INSTANCE - This script processes a single session only.

Example usage (on EC2):

    python convert_assigned_sessions.py

    # Or with stub test:
    python convert_assigned_sessions.py --stub-test

    # Or locally with explicit EID (for testing):
    python convert_assigned_sessions.py --session-eid abc123... --stub-test
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from one.api import ONE

from ibl_to_nwb._scripts.heberto_conversion_script import setup_logger
from ibl_to_nwb.conversion import (
    convert_processed_session,
    convert_raw_session,
    download_session_data,
)
from ibl_to_nwb.conversion.one_patches import apply_one_patches


def get_imdsv2_tag(tag_name: str) -> str:
    """Read instance tag from IMDSv2 metadata service.

    Args:
        tag_name: Name of the tag to read (e.g., "SessionEID")

    Returns:
        Tag value as string
    """
    # Get IMDSv2 token
    token_cmd = [
        "curl",
        "-X",
        "PUT",
        "-fsS",
        "http://169.254.169.254/latest/api/token",
        "-H",
        "X-aws-ec2-metadata-token-ttl-seconds: 21600",
    ]
    token = subprocess.run(token_cmd, capture_output=True, text=True, check=True).stdout.strip()

    # Get tag value
    tag_cmd = [
        "curl",
        "-fsS",
        f"http://169.254.169.254/latest/meta-data/tags/instance/{tag_name}",
        "-H",
        f"X-aws-ec2-metadata-token: {token}",
    ]
    tag_value = subprocess.run(tag_cmd, capture_output=True, text=True, check=True).stdout.strip()

    return tag_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run conversion for assigned session (reads SessionEID from IMDSv2 or CLI)."
    )
    parser.add_argument(
        "--stub-test",
        action="store_true",
        help="Run in stub mode for testing (lightweight data).",
    )
    parser.add_argument(
        "--session-eid",
        type=str,
        help='Override session EID (for local testing). If not provided, reads from IMDSv2 SessionEID tag.',
    )
    return parser.parse_args()


def convert_session(
    eid: str,
    *,
    one: ONE,
    base_folder: Path,
    logs_folder: Path,
    decompressed_ephys_folder: Path,
    nwb_folder: Path,
    stub_test: bool,
    convert_raw: bool,
    convert_processed: bool,
) -> dict:
    """Convert one IBL session to NWB format.

    Downloads data from ONE API, converts to raw and processed NWB files,
    and writes them to disk. Upload is handled separately.

    Returns a dict with conversion statistics.
    """

    log_file = logs_folder / f"conversion_log_{eid}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    logger = setup_logger(log_file)

    logger.info("=" * 80)
    logger.info(f"Starting conversion for session: {eid}")
    logger.info(f"Stub test mode: {stub_test}")
    logger.info(f"Convert RAW: {convert_raw}")
    logger.info(f"Convert PROCESSED: {convert_processed}")
    logger.info("=" * 80)

    session_start = time.time()

    # Download session data
    logger.info("\n" + "=" * 80)
    logger.info("DOWNLOADING SESSION DATA")
    logger.info("=" * 80)
    download_info = download_session_data(
        eid=eid,
        one=one,
        redownload_data=False,
        stub_test=stub_test,
        base_path=base_folder,
        decompressed_ephys_path=decompressed_ephys_folder,
        logger=logger,
    )

    results = {
        "eid": eid,
        "download_size_gb": download_info["total_size_gb"],
        "raw_converted": False,
        "processed_converted": False,
        "success": False,
    }

    # Convert RAW
    if convert_raw:
        logger.info("\n" + "=" * 80)
        logger.info("CONVERTING RAW EPHYS")
        logger.info("=" * 80)

        raw_info = convert_raw_session(
            eid=eid,
            one=one,
            stub_test=stub_test,
            base_path=base_folder,
            decompressed_ephys_path=decompressed_ephys_folder,
            logger=logger,
            overwrite=False,
            redecompress_ephys=False,
        )

        if raw_info and not raw_info.get("skipped"):
            raw_nwb_path = raw_info["nwbfile_path"]
            results["raw_nwb_path"] = str(raw_nwb_path)
            results["raw_size_gb"] = raw_info["nwb_size_gb"]
            results["raw_converted"] = True
            logger.info(f"RAW file written to: {raw_nwb_path}")

    # Convert PROCESSED
    if convert_processed:
        logger.info("\n" + "=" * 80)
        logger.info("CONVERTING PROCESSED/BEHAVIOR")
        logger.info("=" * 80)

        processed_info = convert_processed_session(
            eid=eid,
            one=one,
            stub_test=stub_test,
            base_path=base_folder,
            decompressed_ephys_path=decompressed_ephys_folder,
            logger=logger,
            overwrite=False,
        )

        if processed_info and not processed_info.get("skipped"):
            processed_nwb_path = processed_info["nwbfile_path"]
            results["processed_nwb_path"] = str(processed_nwb_path)
            results["processed_size_gb"] = processed_info["nwb_size_gb"]
            results["processed_converted"] = True
            logger.info(f"PROCESSED file written to: {processed_nwb_path}")

    session_time = time.time() - session_start
    results["total_time_seconds"] = session_time
    results["success"] = True

    logger.info("\n" + "=" * 80)
    logger.info("SESSION COMPLETED")
    logger.info(f"Total time: {session_time:.2f}s ({session_time/60:.2f} minutes)")
    logger.info(f"RAW converted: {results['raw_converted']}")
    logger.info(f"PROCESSED converted: {results['processed_converted']}")
    logger.info("=" * 80)

    return results


def main() -> None:
    args = parse_args()

    # Hardcoded configuration
    BASE_FOLDER = Path("/ebs")
    LOGS_SUBDIR = "conversion_logs"
    DECOMPRESSED_EPHYS_SUBDIR = "decompressed_ephys"
    CACHE_SUBDIR = "ibl_cache"
    NWB_SUBDIR = "nwbfiles"
    CONVERT_RAW = True
    CONVERT_PROCESSED = True

    # DANDI_API_KEY is set by ec2_userdata_production.sh via 'export DANDI_API_KEY=...'
    # No need to load from .env file

    # Hardcoded log level: INFO for main script
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Get session EID from CLI argument or IMDSv2 tag
    if args.session_eid:
        eid = args.session_eid
        logging.info(f"Using session EID from CLI: {eid}")
    else:
        try:
            eid = get_imdsv2_tag("SessionEID")
            logging.info(f"Read session EID from IMDSv2: {eid}")
        except Exception as e:
            raise SystemExit(f"Failed to read SessionEID tag from IMDSv2: {e}") from e

    # Also read SessionIndex for logging (optional)
    try:
        session_index = get_imdsv2_tag("SessionIndex")
        logging.info(f"Session index: {session_index}")
    except Exception:
        session_index = "unknown"

    # Create directory structure
    for subdir in [LOGS_SUBDIR, DECOMPRESSED_EPHYS_SUBDIR, CACHE_SUBDIR, NWB_SUBDIR]:
        (BASE_FOLDER / subdir).mkdir(parents=True, exist_ok=True)

    cache_dir = BASE_FOLDER / CACHE_SUBDIR
    logs_folder = BASE_FOLDER / LOGS_SUBDIR
    decompressed_ephys_folder = BASE_FOLDER / DECOMPRESSED_EPHYS_SUBDIR
    nwb_folder = BASE_FOLDER / NWB_SUBDIR

    # Configure ONE with public IBL data access
    one = ONE(
        base_url="https://openalyx.internationalbrainlab.org",
        password="international",  # Public access password for IBL data
        cache_dir=cache_dir,
        silent=True,
    )
    apply_one_patches(one, logger=None)

    # Convert single session
    logging.info("\n" + "=" * 100)
    logging.info(f"PROCESSING SESSION: {eid} (index: {session_index})")
    logging.info("=" * 100)

    batch_start = time.time()

    try:
        result = convert_session(
            eid,
            one=one,
            base_folder=BASE_FOLDER,
            logs_folder=logs_folder,
            decompressed_ephys_folder=decompressed_ephys_folder,
            nwb_folder=nwb_folder,
            stub_test=args.stub_test,
            convert_raw=CONVERT_RAW,
            convert_processed=CONVERT_PROCESSED,
        )
        logging.info(f"Session {eid} completed successfully")
        success = True
    except Exception:
        logging.exception(f"Session {eid} FAILED")
        result = None
        success = False

    batch_time = time.time() - batch_start

    # Write summary
    logging.info("\n" + "=" * 100)
    logging.info("CONVERSION COMPLETED")
    logging.info("=" * 100)
    logging.info(f"Session EID: {eid}")
    logging.info(f"Session Index: {session_index}")
    logging.info(f"Success: {success}")
    logging.info(f"Total time: {batch_time:.2f}s ({batch_time/3600:.2f} hours)")
    logging.info("=" * 100)

    # Save results summary
    summary_file = logs_folder / f"conversion_summary_{eid}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    summary = {
        "eid": eid,
        "session_index": session_index,
        "success": success,
        "conversion_time_seconds": batch_time,
        "stub_test": args.stub_test,
        "result": result,
    }
    summary_file.write_text(json.dumps(summary, indent=2))
    logging.info(f"Summary written to: {summary_file}")

    # Exit with error code if conversion failed
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())

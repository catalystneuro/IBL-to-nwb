"""Convert assigned IBL session to NWB format.

This script runs ON EC2 INSTANCES (called by boot.sh). Each instance:
  1. Reads its SessionEID tag from IMDSv2
  2. Downloads source data from ONE API
  3. Converts to NWB (both raw and processed)
  4. Writes NWB files to /ebs/nwbfiles/full/sub-*/

Upload to DANDI is handled by boot.sh after this script completes.

ONE SESSION PER INSTANCE - This script processes a single session only.

Example usage (on EC2):

    python convert_and_upload.py

    # Or with stub test:
    python convert_and_upload.py --stub-test

    # Or locally with explicit EID (for testing):
    python convert_and_upload.py --session-eid abc123... --stub-test
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

from one.api import ONE

from ibl_to_nwb._scripts.convert_bwm_to_nwb import setup_logger
from ibl_to_nwb.conversion import (
    convert_processed_session,
    convert_raw_session,
    download_session_data,
)
from ibl_to_nwb.conversion.one_patches import apply_one_patches
from ibl_to_nwb.utils.ephys_decompression import decompress_ephys_cbins
from ibl_to_nwb.utils.paths import setup_paths


# Phase timeouts in seconds
PHASE_TIMEOUTS = {
    "download": 3600,           # 1 hour
    "decompress": 5400,         # 1.5 hours
    "raw_conversion": 10800,    # 3 hours
    "processed_conversion": 1800,  # 30 min
}


class PhaseTimeout:
    """Context manager for phase timeouts with SIGALRM.

    Raises TimeoutError if the phase exceeds the specified timeout.
    Only works on Unix systems (Linux/macOS) that support SIGALRM.
    """

    def __init__(self, seconds: int, phase_name: str):
        self.seconds = seconds
        self.phase_name = phase_name
        self._old_handler = None

    def __enter__(self):
        self._old_handler = signal.signal(signal.SIGALRM, self._handler)
        signal.alarm(self.seconds)
        return self

    def __exit__(self, *args):
        signal.alarm(0)  # Cancel alarm
        if self._old_handler is not None:
            signal.signal(signal.SIGALRM, self._old_handler)

    def _handler(self, signum, frame):
        raise TimeoutError(f"Phase '{self.phase_name}' exceeded {self.seconds}s timeout")


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
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Convert only raw electrophysiology data (skip processed).",
    )
    parser.add_argument(
        "--processed-only",
        action="store_true",
        help="Convert only processed behavior+ecephys data (skip raw). Saves ~100 GB download per session.",
    )
    return parser.parse_args()


def convert_session(
    eid: str,
    *,
    one: ONE,
    base_folder: Path,
    logs_folder: Path,
    nwb_folder: Path,
    stub_test: bool,
    convert_raw: bool,
    convert_processed: bool,
) -> dict:
    """Convert one IBL session to NWB format.

    Downloads data from ONE API, converts to raw and processed NWB files,
    and writes them to disk. Upload is handled separately.

    Each phase has its own timeout to catch stuck phases early:
    - download: 1 hour
    - decompress: 1.5 hours
    - raw_conversion: 3 hours
    - processed_conversion: 30 minutes

    Returns a dict with conversion statistics.

    Raises
    ------
    TimeoutError
        If any phase exceeds its timeout limit.
    """

    log_file = logs_folder / f"conversion_log_{eid}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    logger = setup_logger(log_file)

    logger.info("=" * 80)
    logger.info(f"Starting conversion for session: {eid}")
    logger.info(f"Stub test mode: {stub_test}")
    logger.info(f"Convert RAW: {convert_raw}")
    logger.info(f"Convert PROCESSED: {convert_processed}")
    logger.info("Phase timeouts (seconds): %s", PHASE_TIMEOUTS)
    logger.info("=" * 80)

    session_start = time.time()

    # Download session data with timeout
    # Skip raw ephys download if not converting raw (saves ~100 GB per session)
    logger.info("\n" + "=" * 80)
    logger.info("DOWNLOADING SESSION DATA")
    logger.info(f"Timeout: {PHASE_TIMEOUTS['download']}s ({PHASE_TIMEOUTS['download']/3600:.1f} hours)")
    logger.info("=" * 80)
    download_start = time.time()

    with PhaseTimeout(PHASE_TIMEOUTS["download"], "download"):
        download_info = download_session_data(
            eid=eid,
            one=one,
            redownload_data=False,
            stub_test=stub_test,
            download_raw=convert_raw,
            download_processed=convert_processed,
            base_path=base_folder,
            logger=logger,
        )

    download_duration = time.time() - download_start
    logger.info(f"=== PHASE: download | duration_seconds={download_duration:.0f} | size_gb={download_info['total_size_gb']:.2f} ===")

    results = {
        "eid": eid,
        "download_size_gb": download_info["total_size_gb"],
        "download_duration_seconds": download_duration,
        "raw_converted": False,
        "processed_converted": False,
        "success": False,
    }

    # Convert RAW (with separate decompress and conversion timeouts)
    if convert_raw:
        # Setup paths for decompression
        paths = setup_paths(one, eid, base_path=base_folder)
        scratch_ephys_folder = paths["session_decompressed_ephys_folder"] / "raw_ephys_data"
        existing_bins = (
            scratch_ephys_folder.exists() and next(scratch_ephys_folder.rglob("*.bin"), None) is not None
        )

        # In stub mode: skip decompression if no existing bins (they won't be downloaded)
        # In full mode: always decompress if not already done
        should_decompress = convert_raw and not stub_test and not existing_bins

        if should_decompress:
            logger.info("\n" + "=" * 80)
            logger.info("DECOMPRESSING RAW EPHYS")
            logger.info(f"Timeout: {PHASE_TIMEOUTS['decompress']}s ({PHASE_TIMEOUTS['decompress']/3600:.1f} hours)")
            logger.info("=" * 80)

            decompress_start = time.time()

            with PhaseTimeout(PHASE_TIMEOUTS["decompress"], "decompress"):
                decompress_ephys_cbins(
                    source_folder=paths["session_folder"],
                    target_folder=paths["session_decompressed_ephys_folder"],
                )

            decompress_duration = time.time() - decompress_start
            logger.info(f"=== PHASE: decompress | duration_seconds={decompress_duration:.0f} ===")
            results["decompress_duration_seconds"] = decompress_duration

            # Delete compressed .cbin files after decompression to free disk space
            cbin_files = list(paths["session_folder"].rglob("*.cbin"))
            if cbin_files:
                cbin_size_bytes = sum(f.stat().st_size for f in cbin_files)
                cbin_size_gb = cbin_size_bytes / (1024**3)
                for cbin_file in cbin_files:
                    cbin_file.unlink()
                logger.info(f"Deleted {len(cbin_files)} .cbin files ({cbin_size_gb:.1f} GB) to free disk space")

        logger.info("\n" + "=" * 80)
        logger.info("CONVERTING RAW EPHYS")
        logger.info(f"Timeout: {PHASE_TIMEOUTS['raw_conversion']}s ({PHASE_TIMEOUTS['raw_conversion']/3600:.1f} hours)")
        logger.info("=" * 80)

        raw_start = time.time()

        with PhaseTimeout(PHASE_TIMEOUTS["raw_conversion"], "raw_conversion"):
            raw_info = convert_raw_session(
                eid=eid,
                one=one,
                stub_test=stub_test,
                base_path=base_folder,
                logger=logger,
                overwrite=False,
            )

        raw_duration = time.time() - raw_start

        if raw_info and not raw_info.get("skipped"):
            raw_nwb_path = raw_info["nwbfile_path"]
            results["raw_nwb_path"] = str(raw_nwb_path)
            results["raw_size_gb"] = raw_info["nwb_size_gb"]
            results["raw_duration_seconds"] = raw_duration
            results["raw_converted"] = True
            logger.info(f"RAW file written to: {raw_nwb_path}")
            logger.info(f"=== PHASE: raw_conversion | duration_seconds={raw_duration:.0f} | size_gb={raw_info['nwb_size_gb']:.2f} ===")

    # Convert PROCESSED with timeout
    if convert_processed:
        logger.info("\n" + "=" * 80)
        logger.info("CONVERTING PROCESSED/BEHAVIOR")
        logger.info(f"Timeout: {PHASE_TIMEOUTS['processed_conversion']}s ({PHASE_TIMEOUTS['processed_conversion']/60:.0f} minutes)")
        logger.info("=" * 80)

        processed_start = time.time()

        with PhaseTimeout(PHASE_TIMEOUTS["processed_conversion"], "processed_conversion"):
            processed_info = convert_processed_session(
                eid=eid,
                one=one,
                stub_test=stub_test,
                base_path=base_folder,
                logger=logger,
                overwrite=False,
            )

        processed_duration = time.time() - processed_start

        if processed_info and not processed_info.get("skipped"):
            processed_nwb_path = processed_info["nwbfile_path"]
            results["processed_nwb_path"] = str(processed_nwb_path)
            results["processed_size_gb"] = processed_info["nwb_size_gb"]
            results["processed_duration_seconds"] = processed_duration
            results["processed_converted"] = True
            logger.info(f"PROCESSED file written to: {processed_nwb_path}")
            logger.info(f"=== PHASE: processed_conversion | duration_seconds={processed_duration:.0f} | size_gb={processed_info['nwb_size_gb']:.2f} ===")

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
    CACHE_SUBDIR = "ibl_cache"
    NWB_SUBDIR = "nwbfiles"

    # Determine what to convert from CLI arguments
    if args.raw_only and args.processed_only:
        raise SystemExit("Cannot specify both --raw-only and --processed-only")

    if args.raw_only:
        CONVERT_RAW = True
        CONVERT_PROCESSED = False
    elif args.processed_only:
        CONVERT_RAW = False
        CONVERT_PROCESSED = True
    else:
        # Default: convert both
        CONVERT_RAW = True
        CONVERT_PROCESSED = True

    # DANDI_API_KEY is set by boot.sh via 'export DANDI_API_KEY=...'
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
    for subdir in [LOGS_SUBDIR, CACHE_SUBDIR, NWB_SUBDIR]:
        (BASE_FOLDER / subdir).mkdir(parents=True, exist_ok=True)

    cache_dir = BASE_FOLDER / CACHE_SUBDIR
    logs_folder = BASE_FOLDER / LOGS_SUBDIR
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
            nwb_folder=nwb_folder,
            stub_test=args.stub_test,
            convert_raw=CONVERT_RAW,
            convert_processed=CONVERT_PROCESSED,
        )
        logging.info(f"Session {eid} completed successfully")
        success = True
    except TimeoutError as e:
        # Phase-specific timeout - log and exit with code 124 (same as bash timeout)
        logging.error(f"=== RESULT: TIMEOUT | eid={eid} | {e} ===")
        logging.exception(f"Session {eid} FAILED due to timeout")
        result = None
        success = False
        # Exit immediately with timeout exit code (124 matches bash timeout)
        sys.exit(124)
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

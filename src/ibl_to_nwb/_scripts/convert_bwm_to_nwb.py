"""Standalone script to convert IBL sessions to NWB files."""

from __future__ import annotations

import logging
import platform
import random
import sys
import time
from pathlib import Path

from one.api import ONE

from ibl_to_nwb.conversion.session import convert_session
from ibl_to_nwb.conversion.one_patches import apply_one_patches
from ibl_to_nwb.fixtures import load_fixtures
from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency


def setup_logger(log_file_path: Path) -> logging.Logger:
    """Configure a logger that writes to disk and stdout."""

    logger = logging.getLogger("IBL_Conversion")
    logger.setLevel(logging.INFO)
    logger.handlers = []

    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file_path, mode="a")
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    file_handler.stream.reconfigure(line_buffering=True)

    # Capture Python warnings in the logging system
    # This ensures warnings.warn() calls appear in the log file
    logging.captureWarnings(True)
    warnings_logger = logging.getLogger('py.warnings')
    warnings_logger.addHandler(file_handler)
    warnings_logger.addHandler(console_handler)

    return logger


if __name__ == "__main__":
    # ========================================================================
    # MAIN CONFIGURATION
    # ========================================================================

    CONVERT_RAW = False             # Write raw-ephys NWBs
    CONVERT_PROCESSED = True       # Write processed/behavior NWBs
    STUB_TEST = False               # Work on lightweight subsets of data (auto-includes cached videos & decompressed ephys)
    OVERWRITE = True              # Regenerate NWBs even if existing files validate
    RUN_CONSISTENCY_CHECKS = False  # Validate NWB files against ONE data (slow but thorough)
    VERBOSE = False                 # Enable verbose output from neuroconv interfaces
    DISPLAY_PROGRESS_BAR = True     # Show progress bars (local runs)

    if platform.system() == "Darwin":  # macOS
        base_folder = Path("/Volumes/Expansion")
    else:  # Linux
        base_folder = Path("/media/heberto/Expansion")
    cache_dir = base_folder / "ibl_cache"
    base_path = base_folder
    logs_path = base_path / "conversion_logs"

    session_identifier = "all"

    one = ONE(base_url="https://openalyx.internationalbrainlab.org", cache_dir=cache_dir, password='international', silent=True)

    # Apply ONE API patches to fix cache validation issues
    print("Applying ONE API patches for cache validation...")
    one = apply_one_patches(one, logger=None)
    print("ONE API patches applied successfully\n")

    bwm_df = load_fixtures.load_bwm_df()
    unique_sessions = bwm_df.drop_duplicates("eid").reset_index(drop=True)
    all_eids = unique_sessions["eid"].tolist()
    random.shuffle(all_eids)

    print(f"Total sessions to process: {len(all_eids)}")

    for session_index, eid in enumerate(all_eids, start=1):
        print(f"\nProcessing session {session_index}/{len(all_eids)}: {eid}")

        script_start_time = time.time()

        # Run conversion through shared pipeline (same code path as AWS)
        results = convert_session(
            eid,
            one=one,
            base_folder=base_path,
            logs_folder=logs_path,
            stub_test=STUB_TEST,
            convert_raw=CONVERT_RAW,
            convert_processed=CONVERT_PROCESSED,
            overwrite=OVERWRITE,
            verbose=VERBOSE,
            display_progress_bar=DISPLAY_PROGRESS_BAR,
        )

        # Post-processing: consistency checks (local-only, not needed in the AWS pipeline)

        logger = logging.getLogger("IBL_Conversion")

        if CONVERT_RAW and results.get("raw_converted"):
            raw_nwb_path = Path(results["raw_nwb_path"])

            # Run consistency checks if enabled
            if RUN_CONSISTENCY_CHECKS:
                try:
                    check_start = time.time()
                    check_nwbfile_for_consistency(one=one, nwbfile_path=raw_nwb_path)
                    check_time = time.time() - check_start
                    logger.info(f"RAW validation passed ({check_time:.1f}s)")
                except AssertionError as e:
                    logger.error(f"RAW validation FAILED: {e}")
                except Exception as e:
                    logger.error(f"RAW validation error: {e}")

        if CONVERT_PROCESSED and results.get("processed_converted"):
            processed_nwb_path = Path(results["processed_nwb_path"])

            # Run consistency checks if enabled
            if RUN_CONSISTENCY_CHECKS:
                try:
                    check_start = time.time()
                    check_nwbfile_for_consistency(one=one, nwbfile_path=processed_nwb_path)
                    check_time = time.time() - check_start
                    logger.info(f"PROCESSED validation passed ({check_time:.1f}s)")
                except AssertionError as e:
                    logger.error(f"PROCESSED validation FAILED: {e}")
                except Exception as e:
                    logger.error(f"PROCESSED validation error: {e}")

        # Compression summary
        download_info = results.get("download_info", {})
        logger.info("\n" + "=" * 80)
        logger.info("COMPRESSION SUMMARY")
        logger.info("=" * 80)
        if download_info:
            logger.info(
                f"Source data size: {download_info.get('total_size_gb', 0):.2f} GB "
                f"({download_info.get('total_size_bytes', 0):,} bytes)"
            )

        if results.get("raw_converted"):
            raw_size_gb = results.get("raw_size_gb", 0)
            raw_size_bytes = results.get("raw_size_bytes", 0)
            ratio = (
                download_info.get("total_size_gb", 0) / raw_size_gb
                if raw_size_gb > 0
                else 0
            )
            logger.info(f"RAW NWB size: {raw_size_gb:.2f} GB ({raw_size_bytes:,} bytes)")
            logger.info(f"RAW compression ratio: {ratio:.2f}x (source/output)")
        elif results.get("raw_skipped"):
            logger.info("RAW conversion skipped (existing NWB).")

        if results.get("processed_converted"):
            processed_size_gb = results.get("processed_size_gb", 0)
            processed_size_bytes = results.get("processed_size_bytes", 0)
            ratio = (
                download_info.get("total_size_gb", 0) / processed_size_gb
                if processed_size_gb > 0
                else 0
            )
            logger.info(f"PROCESSED NWB size: {processed_size_gb:.2f} GB ({processed_size_bytes:,} bytes)")
            logger.info(f"PROCESSED compression ratio: {ratio:.2f}x (source/output)")
        elif results.get("processed_skipped"):
            logger.info("Processed conversion skipped (existing NWB).")

        if results.get("raw_converted") and results.get("processed_converted"):
            total_nwb_size_gb = results["raw_size_gb"] + results["processed_size_gb"]
            total_nwb_size_bytes = results["raw_size_bytes"] + results["processed_size_bytes"]
            overall_compression = (
                download_info.get("total_size_gb", 0) / total_nwb_size_gb if total_nwb_size_gb > 0 else 0
            )
            logger.info(f"Total NWB output: {total_nwb_size_gb:.2f} GB ({total_nwb_size_bytes:,} bytes)")
            logger.info(f"Overall compression ratio: {overall_compression:.2f}x (source/combined output)")

        script_total_time = time.time() - script_start_time
        logger.info("\n" + "=" * 80)
        logger.info("CONVERSION COMPLETED")
        logger.info(f"Total script execution time: {script_total_time:.2f}s ({script_total_time/60:.2f} minutes)")
        logger.info("=" * 80)

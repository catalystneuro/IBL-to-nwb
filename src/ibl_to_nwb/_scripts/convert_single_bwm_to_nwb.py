"""Standalone script to convert a single IBL session to an NWB file."""

from __future__ import annotations

import logging
import platform
import sys
import time
from pathlib import Path

from one.api import ONE

from ibl_to_nwb.conversion.session import convert_session
from ibl_to_nwb.conversion.one_patches import apply_one_patches
from ibl_to_nwb.testing._consistency_checks import check_nwbfile_for_consistency


def setup_logger(log_file_path: Path) -> logging.Logger:
    """Configure a logger that writes to disk and stdout."""

    logger = logging.getLogger("IBL_Conversion_Single_EID")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    logger.propagate = False  # Prevent duplicate logs from root logger

    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file_path, mode="a")
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

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

    CONVERT_RAW = False              # Write raw-ephys NWBs
    CONVERT_PROCESSED = True        # Write processed/behavior NWBs
    STUB_TEST = False                # Work on lightweight subsets of data (auto-includes cached videos & decompressed ephys)
    REDOWNLOAD_DATA = False         # Clear cached data and re-download from ONE
    OVERWRITE = True                # Regenerate NWBs even if existing files validate
    RUN_CONSISTENCY_CHECKS = False   # Validate NWB files against ONE data (slow but thorough)
    VERBOSE = False                 # Enable verbose output from neuroconv interfaces
    DISPLAY_PROGRESS_BAR = True     # Show progress bars (local runs)

    if platform.system() == "Darwin":  # macOS
        base_folder = Path("/Volumes/Expansion")
    else:  # Linux
        base_folder = Path("/media/heberto/Expansion")
    cache_dir = base_folder / "ibl_cache"
    base_path = base_folder

    TARGET_EID = "bd456d8f-d36e-434a-8051-ff3997253802"  # This one has full raw data
    TARGET_EID = "dc21e80d-97d7-44ca-a729-a8e3f9b14305" # has mismatch in timestamps between pupil and data
    TARGET_EID = "1f095590-6669-46c9-986b-ccaf0620c5e9"  # UCLA012 - Testing: previously missing videos in raw NWB
    TARGET_EID = "28741f91-c837-4147-939e-918d38d849f2"  # Signal already in info dict
    TARGET_EID = "d2918f52-8280-43c0-924b-029b2317e62c"  # Testing if meta is downloaded
    TARGET_EID = "72cb5550-43b4-4ef0-add5-e4adfdfb5e02"  # Testing: stream matching
    TARGET_EID = "d839491f-55d8-4cbe-a298-7839208ba12b" # No nidq file
    TARGET_EID = "29a6def1-fc5c-4eea-ac48-47e9b053dcb5" # Time alignment issue
    TARGET_EID = "032452e9-1886-449d-9c13-0f192572e19f" # Corrupted meta file issue
    TARGET_EID = "283ecb4c-e529-409c-9f0a-8ea5191dcf50"  # Mac os hidden files issue
    TARGET_EID = "6668c4a0-70a4-4012-a7da-709660971d7a"  # Testing: mac os hidden files
    TARGET_EID = "f99ac31f-171b-4208-a55d-5644c0ad51c3"  # ADC null property issue (two probes)
    TARGET_EID = "72cb5550-43b4-4ef0-add5-e4adfdfb5e02"  # nidq missing in stream error
    TARGET_EID = "90e74228-fd1a-482f-bd56-05dbad132861"  # Memory error
    TARGET_EID = "6ed57216-498d-48a6-b48b-a243a34710ea"  # Full processed file
    TARGET_EID = "35ed605c-1a1a-47b1-86ff-2b56144f55af"  # Another full file
    TARGET_EID = "fa1f26a1-eb49-4b24-917e-19f02a18ac61"  # Yet another full file
    TARGET_EID = "8c025071-c4f3-426c-9aed-f149e8f75b7b"  # Large memory consumption (~36 GB virtual, ~29.5 GB RSS), OOM on 32 GB instances during processed conversion (2 probes)
    # TARGET_EID = "ebe090af-5922-4fcd-8fc6-17b8ba7bad6d"  # Witten lab - missing firstSample in meta
    # TARGET_EID = "de905562-31c6-4c31-9ece-3ee87b97eab4"  # steinmetzlab NR_0029 (2023-08-31) - corrupted meta (probe00b)
    # TARGET_EID = "d85c454e-8737-4cba-b6ad-b2339429d99b"  # steinmetzlab NR_0029 (2023-08-29) - corrupted meta (probe00a)
    # TARGET_EID = "eacc49a9-f3a1-49f1-b87f-0972f90ee837"  # OOM during processed NWB write (2 probes, 2.19 GB source)
    # TARGET_EID = "3a3ea015-b5f4-4e8b-b189-9364d1fc7435"  # steinmetzlab NR_0029 (2023-09-05) - corrupted meta (probe00a)
    # TARGET_EID = "4e560423-5caf-4cda-8511-d1ab4cd2bf7d"  # steinmetzlab NR_0029 (2023-09-07) - corrupted meta (probe00a)
    target_eid = (sys.argv[1] if len(sys.argv) > 1 else TARGET_EID).strip()

    if target_eid == "INSERT_EID_HERE":
        raise SystemExit("Please provide an EID either by editing TARGET_EID or passing it as a command-line argument.")

    one = ONE(base_url="https://openalyx.internationalbrainlab.org", cache_dir=cache_dir, password='international', silent=True)

    # Logs are derived from base_path
    logs_path = base_path / "conversion_logs"
    logs_path.mkdir(exist_ok=True, parents=True)

    # Apply ONE API patches to fix cache validation issues
    one = apply_one_patches(one, logger=None)

    logger = logging.getLogger("IBL_Conversion_Single_EID")
    logger.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(console)

    logger.info("=" * 80)
    logger.info("IBL SINGLE-EID CONVERSION SCRIPT STARTED")
    logger.info(f"EID: {target_eid}")
    logger.info(f"Convert RAW: {CONVERT_RAW}")
    logger.info(f"Convert PROCESSED: {CONVERT_PROCESSED}")
    logger.info(f"Stub test mode: {STUB_TEST}")
    logger.info(f"Overwrite existing NWB: {OVERWRITE}")
    logger.info(f"Run consistency checks: {RUN_CONSISTENCY_CHECKS}")
    if RUN_CONSISTENCY_CHECKS:
        logger.info("  (Validates NWB data against ONE - adds time but ensures correctness)")
    logger.info("=" * 80)

    script_start_time = time.time()

    # Run conversion through shared pipeline (same code path as AWS)
    results = convert_session(
        target_eid,
        one=one,
        base_folder=base_path,
        logs_folder=logs_path,
        stub_test=STUB_TEST,
        convert_raw=CONVERT_RAW,
        convert_processed=CONVERT_PROCESSED,
        overwrite=OVERWRITE,
        redownload_data=REDOWNLOAD_DATA,
        verbose=VERBOSE,
        display_progress_bar=DISPLAY_PROGRESS_BAR,
    )

    # Post-processing: consistency checks (local-only, not needed in the AWS pipeline)

    if CONVERT_RAW and results.get("raw_converted"):
        raw_nwb_path = Path(results["raw_nwb_path"])

        # Run consistency checks if enabled
        if RUN_CONSISTENCY_CHECKS:
            logger.info("\n" + "=" * 80)
            logger.info(f"VALIDATING RAW NWB FILE (EID: {target_eid})")
            logger.info("=" * 80)
            try:
                check_start = time.time()
                check_nwbfile_for_consistency(one=one, nwbfile_path=raw_nwb_path)
                check_time = time.time() - check_start
                logger.info(f"RAW NWB validation passed in {check_time:.2f}s")
                logger.info("  All data matches ONE API source")
            except AssertionError as e:
                logger.error(f"RAW NWB validation FAILED: {e}")
                logger.error("  Data mismatch detected - check conversion logic")
            except Exception as e:
                logger.error(f"RAW NWB validation error: {e}")
                logger.error("  Unexpected error during validation")

    if CONVERT_PROCESSED and results.get("processed_converted"):
        processed_nwb_path = Path(results["processed_nwb_path"])

        # Run consistency checks if enabled
        if RUN_CONSISTENCY_CHECKS:
            logger.info("\n" + "=" * 80)
            logger.info(f"VALIDATING PROCESSED NWB FILE (EID: {target_eid})")
            logger.info("=" * 80)
            try:
                check_start = time.time()
                check_nwbfile_for_consistency(one=one, nwbfile_path=processed_nwb_path)
                check_time = time.time() - check_start
                logger.info(f"PROCESSED NWB validation passed in {check_time:.2f}s")
                logger.info("  All data matches ONE API source")
            except AssertionError as e:
                logger.error(f"PROCESSED NWB validation FAILED: {e}")
                logger.error("  Data mismatch detected - check conversion logic")
            except Exception as e:
                logger.error(f"PROCESSED NWB validation error: {e}")
                logger.error("  Unexpected error during validation")

    # Compression summary
    download_info = results.get("download_info", {})
    logger.info("\n" + "=" * 80)
    logger.info(f"COMPRESSION SUMMARY (EID: {target_eid})")
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
    logger.info(f"CONVERSION COMPLETED (EID: {target_eid})")
    logger.info(f"Total script execution time: {script_total_time:.2f}s ({script_total_time/60:.2f} minutes)")
    logger.info("=" * 80)

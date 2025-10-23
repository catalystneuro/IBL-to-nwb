"""Standalone script to convert IBL sessions to NWB files."""

from __future__ import annotations

import logging
import random
import sys
import time
from pathlib import Path

from one.api import ONE

from ibl_to_nwb.conversion import (
    download_session_data,
    convert_raw_session,
    convert_processed_session,
)
from ibl_to_nwb.conversion.one_patches import apply_one_patches
from ibl_to_nwb.fixtures import load_fixtures


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

    try:
        file_handler.stream.reconfigure(line_buffering=True)
    except AttributeError:
        pass

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

    CONVERT_RAW = True             # Write raw-ephys NWBs
    CONVERT_PROCESSED = True       # Write processed/behavior NWBs
    STUB_TEST = False               # Work on lightweight subsets of data (auto-includes cached videos & decompressed ephys)
    REDOWNLOAD_DATA = False        # Force re-download even if cached
    REDECOMPRESS_EPHYS = False     # Force regeneration of decompressed SpikeGLX binaries
    OVERWRITE = True              # Regenerate NWBs even if existing files validate

    base_folder = Path("/media/heberto/Expansion")
    cache_dir = base_folder / "ibl_data"
    base_path = base_folder
    scratch_path = base_folder / "temporary_files"

    session_identifier = "all"
    revision = "2024-05-06"

    one = ONE(base_url="https://openalyx.internationalbrainlab.org", cache_dir=cache_dir, silent=True)

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

        log_file_path = scratch_path / f"conversion_log_{eid}_{time.strftime('%Y%m%d_%H%M%S')}.log"
        logger = setup_logger(log_file_path)
        logger.info("=" * 80)
        logger.info("IBL CONVERSION SCRIPT STARTED")
        logger.info(f"Session {session_index}/{len(all_eids)}")
        logger.info(f"Session ID: {eid}")
        logger.info(f"EID: {eid}")
        logger.info(f"Revision: {revision}")
        logger.info(f"Convert RAW: {CONVERT_RAW}")
        logger.info(f"Convert PROCESSED: {CONVERT_PROCESSED}")
        logger.info(f"Stub test mode: {STUB_TEST}")
        if STUB_TEST:
            logger.info("  (Stub mode auto-includes cached videos & decompressed ephys)")
        logger.info(f"Re-download data: {REDOWNLOAD_DATA}")
        logger.info(f"Re-decompress ephys: {REDECOMPRESS_EPHYS}")
        logger.info(f"Overwrite existing NWB: {OVERWRITE}")
        logger.info(f"Log file: {log_file_path}")
        logger.info("=" * 80)

        script_start_time = time.time()

        logger.info("\n" + "=" * 80)
        logger.info("DOWNLOADING SESSION DATA")
        logger.info("=" * 80)
        download_info = download_session_data(
            eid=eid,
            one=one,
            redownload_data=REDOWNLOAD_DATA,
            stub_test=STUB_TEST,
            revision=revision,
            base_path=base_path,
            scratch_path=scratch_path,
            logger=logger,
        )

        raw_info = None
        processed_info = None

        if CONVERT_RAW:
            logger.info("\n" + "=" * 80)
            logger.info("STARTING RAW CONVERSION")
            logger.info("=" * 80)
            raw_info = convert_raw_session(
                eid=eid,
                one=one,
                stub_test=STUB_TEST,
                revision=revision,
                base_path=base_path,
                scratch_path=scratch_path,
                logger=logger,
                overwrite=OVERWRITE,
                redecompress_ephys=REDECOMPRESS_EPHYS,
            )

        if CONVERT_PROCESSED:
            logger.info("\n" + "=" * 80)
            logger.info("STARTING PROCESSED CONVERSION")
            logger.info("=" * 80)
            processed_info = convert_processed_session(
                eid=eid,
                one=one,
                stub_test=STUB_TEST,
                revision=revision,
                base_path=base_path,
                scratch_path=scratch_path,
                skip_spike_properties=["spike_amplitudes", "spike_relative_depths"],
                logger=logger,
                overwrite=OVERWRITE,
            )

        logger.info("\n" + "=" * 80)
        logger.info("COMPRESSION SUMMARY")
        logger.info("=" * 80)
        logger.info(
            f"Source data size: {download_info['total_size_gb']:.2f} GB "
            f"({download_info['total_size_bytes']:,} bytes)"
        )

        if raw_info:
            if raw_info.get("skipped"):
                logger.info("RAW conversion skipped (existing NWB).")
            else:
                ratio = (
                    download_info["total_size_gb"] / raw_info["nwb_size_gb"]
                    if raw_info["nwb_size_gb"] > 0
                    else 0
                )
                logger.info(
                    f"RAW NWB size: {raw_info['nwb_size_gb']:.2f} GB ({raw_info['nwb_size_bytes']:,} bytes)"
                )
                logger.info(f"RAW compression ratio: {ratio:.2f}x (source/output)")

        if processed_info:
            if processed_info.get("skipped"):
                logger.info("Processed conversion skipped (existing NWB).")
            else:
                ratio = (
                    download_info["total_size_gb"] / processed_info["nwb_size_gb"]
                    if processed_info["nwb_size_gb"] > 0
                    else 0
                )
                logger.info(
                    "PROCESSED NWB size: "
                    f"{processed_info['nwb_size_gb']:.2f} GB ({processed_info['nwb_size_bytes']:,} bytes)"
                )
                logger.info(f"PROCESSED compression ratio: {ratio:.2f}x (source/output)")

        if raw_info and processed_info and not raw_info.get("skipped") and not processed_info.get("skipped"):
            total_nwb_size_gb = raw_info['nwb_size_gb'] + processed_info['nwb_size_gb']
            total_nwb_size_bytes = raw_info['nwb_size_bytes'] + processed_info['nwb_size_bytes']
            overall_compression = (
                download_info['total_size_gb'] / total_nwb_size_gb if total_nwb_size_gb > 0 else 0
            )
            logger.info(f"Total NWB output: {total_nwb_size_gb:.2f} GB ({total_nwb_size_bytes:,} bytes)")
            logger.info(f"Overall compression ratio: {overall_compression:.2f}x (source/combined output)")

        script_total_time = time.time() - script_start_time
        logger.info("\n" + "=" * 80)
        logger.info("CONVERSION COMPLETED")
        logger.info(f"Total script execution time: {script_total_time:.2f}s ({script_total_time/60:.2f} minutes)")
        logger.info("=" * 80)

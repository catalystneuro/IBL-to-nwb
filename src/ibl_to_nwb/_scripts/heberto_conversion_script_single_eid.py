"""Standalone script to convert a single IBL session to an NWB file."""

from __future__ import annotations

import logging
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

# TODO: 2025-10-17 21:53:06 WARNING  spikeglx.py:699  Meta data doesn't have geometry (snsShankMap/snsGeomMap field), returning defaults
# What outputs this warning?


def setup_logger(log_file_path: Path) -> logging.Logger:
    """Configure a logger that writes to disk and stdout."""

    logger = logging.getLogger("IBL_Conversion_Single_EID")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []

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

    CONVERT_RAW = True              # Write raw-ephys NWBs
    CONVERT_PROCESSED = True        # Write processed/behavior NWBs
    STUB_TEST = True               # Work on lightweight subsets of data
    STUB_INCLUDE_EPHYS = True      # When stub-testing, write a short SpikeGLX excerpt if data is already decompressed
    REDOWNLOAD_DATA = False         # Force re-download even if cached
    REDECOMPRESS_EPHYS = False      # Force regeneration of decompressed SpikeGLX binaries
    OVERWRITE = True                # Regenerate NWBs even if existing files validate

    base_folder = Path("/media/heberto/Expansion")
    cache_dir = base_folder / "ibl_data"
    base_path = base_folder
    scratch_path = base_folder / "temporary_files"

    TARGET_EID = "bd456d8f-d36e-434a-8051-ff3997253802"  # This one has full raw data
    TARGET_EID = "dc21e80d-97d7-44ca-a729-a8e3f9b14305" # has mismatch in timestamps between pupil and data
    target_eid = (sys.argv[1] if len(sys.argv) > 1 else TARGET_EID).strip()

    if target_eid == "INSERT_EID_HERE":
        raise SystemExit("Please provide an EID either by editing TARGET_EID or passing it as a command-line argument.")

    revision = "2024-05-06"
    one = ONE(base_url="https://openalyx.internationalbrainlab.org", cache_dir=cache_dir, silent=True)

    log_file_path = scratch_path / f"conversion_log_{target_eid}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    logger = setup_logger(log_file_path)

    # Apply ONE API patches to fix cache validation issues
    one = apply_one_patches(one, logger=logger)

    logger.info("=" * 80)
    logger.info("IBL SINGLE-EID CONVERSION SCRIPT STARTED")
    logger.info(f"EID: {target_eid}")
    logger.info(f"Revision: {revision}")
    logger.info(f"Convert RAW: {CONVERT_RAW}")
    logger.info(f"Convert PROCESSED: {CONVERT_PROCESSED}")
    logger.info(f"Stub test mode: {STUB_TEST}")
    logger.info(f"Stub includes ephys: {STUB_INCLUDE_EPHYS}")
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
        eid=target_eid,
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
            eid=target_eid,
            one=one,
            stub_test=STUB_TEST,
            stub_include_ecephys=STUB_INCLUDE_EPHYS,
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
            eid=target_eid,
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

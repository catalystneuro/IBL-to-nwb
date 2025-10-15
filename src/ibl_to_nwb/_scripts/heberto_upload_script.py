"""Script to upload NWB files to DANDI staging archive.

This script finds all NWB files in the specified directory and uploads them to DANDI.
It automatically validates files using NWBInspector during upload.

Usage:
    python heberto_upload_script.py
"""

from pathlib import Path
from datetime import datetime
import subprocess
import logging
import time
import sys
from dotenv import load_dotenv


def setup_logger(log_file_path: Path):
    """Setup logger that writes to file in real-time.

    Parameters
    ----------
    log_file_path : Path
        Path to the log file

    Returns
    -------
    logging.Logger
        Configured logger instance
    """
    logger = logging.getLogger("IBL_Upload")
    logger.setLevel(logging.INFO)

    # Remove any existing handlers
    logger.handlers = []

    # Create file handler with unbuffered writing
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_handler.setLevel(logging.INFO)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Ensure unbuffered output
    file_handler.stream.reconfigure(line_buffering=True)

    return logger


if __name__ == "__main__":
    # Load environment variables from .env file
    # Place your .env file in the same directory as this script with:
    # DANDI_API_KEY=your_dandi_staging_api_key_here
    load_dotenv()

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    # Paths
    base_folder = Path("/media/heberto/Expansion")
    nwb_files_folder = base_folder / "nwbfiles" / "216650"  # Inside dandiset folder
    log_folder = base_folder / "temporary_files"

    # DANDI settings
    DANDISET_ID = "216650"        # DANDI dataset ID on sandbox.dandiarchive.org

    # Upload filters (optional)
    UPLOAD_RAW = True             # Upload raw electrophysiology files
    UPLOAD_PROCESSED = True       # Upload processed behavior+ecephys files

    # ========================================================================
    # SETUP LOGGING
    # ========================================================================

    log_file_path = log_folder / f"upload_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logger = setup_logger(log_file_path)

    logger.info("="*80)
    logger.info("IBL DANDI UPLOAD SCRIPT STARTED")
    logger.info(f"DANDI Dataset: {DANDISET_ID} (staging)")
    logger.info(f"NWB files folder: {nwb_files_folder}")
    logger.info(f"Log file: {log_file_path}")
    logger.info("="*80)

    # ========================================================================
    # FIND NWB FILES
    # ========================================================================

    logger.info("\nSearching for NWB files...")
    all_nwb_files = list(nwb_files_folder.rglob("*.nwb"))

    # Filter by type if needed
    files_to_upload = []
    for nwb_file in all_nwb_files:
        if UPLOAD_RAW and "desc-raw" in nwb_file.name:
            files_to_upload.append(nwb_file)
        elif UPLOAD_PROCESSED and "desc-processed" in nwb_file.name:
            files_to_upload.append(nwb_file)

    # Calculate total size of files to upload
    total_size_bytes = sum(f.stat().st_size for f in files_to_upload)
    total_size_gb = total_size_bytes / (1024**3)
    total_size_tb = total_size_gb / 1024

    logger.info(f"Found {len(all_nwb_files)} total NWB files")
    logger.info(f"Files to upload: {len(files_to_upload)}")
    logger.info(f"Total data size to upload: {total_size_gb:.2f} GB ({total_size_tb:.2f} TB)")

    if len(files_to_upload) == 0:
        logger.info("No files to upload. Exiting.")
        sys.exit(0)

    # ========================================================================
    # UPLOAD FILES
    # ========================================================================

    script_start_time = time.time()
    successful_uploads = 0
    failed_uploads = 0

    # Track upload speeds for averaging
    upload_speeds = []  # GB/hour
    uploaded_bytes = 0

    for idx, nwb_file in enumerate(files_to_upload, 1):
        logger.info("\n" + "="*80)
        logger.info(f"UPLOADING FILE {idx}/{len(files_to_upload)}")
        logger.info("="*80)

        file_size_bytes = nwb_file.stat().st_size
        file_size_gb = file_size_bytes / (1024**3)

        logger.info(f"File: {nwb_file.name}")
        logger.info(f"Size: {file_size_gb:.2f} GB ({file_size_bytes:,} bytes)")

        upload_start = time.time()

        # Use dandi upload command with validation
        # Change to the nwbfiles directory so dandi can find dandiset.yaml
        result = subprocess.run(
            [
                "dandi", "upload",
                "-i", "dandi-staging",
                str(nwb_file)
            ],
            capture_output=True,
            text=True,
            cwd=str(nwb_files_folder),
        )

        upload_time = time.time() - upload_start

        # Check if upload failed
        if result.returncode != 0:
            logger.info(f"Upload FAILED with exit code {result.returncode}")
            logger.info(f"Error output: {result.stderr}")
            logger.info(f"Standard output: {result.stdout}")
            failed_uploads += 1
            continue
        upload_speed_gb_per_hour = file_size_gb / (upload_time / 3600) if upload_time > 0 else 0
        upload_speeds.append(upload_speed_gb_per_hour)
        uploaded_bytes += file_size_bytes

        # Calculate running statistics
        avg_speed_gb_per_hour = sum(upload_speeds) / len(upload_speeds)
        remaining_bytes = total_size_bytes - uploaded_bytes
        remaining_gb = remaining_bytes / (1024**3)

        # Estimate time remaining based on average speed
        if avg_speed_gb_per_hour > 0:
            estimated_hours_remaining = remaining_gb / avg_speed_gb_per_hour
            estimated_days_remaining = estimated_hours_remaining / 24
        else:
            estimated_hours_remaining = 0
            estimated_days_remaining = 0

        logger.info(f"Upload completed in {upload_time:.2f}s ({upload_time/60:.2f} min)")
        logger.info(f"Upload speed: {upload_speed_gb_per_hour:.2f} GB/hour")
        logger.info(f"Average upload speed (all files): {avg_speed_gb_per_hour:.2f} GB/hour")
        logger.info(f"Progress: {uploaded_bytes / total_size_bytes * 100:.1f}% ({uploaded_bytes / (1024**3):.2f} GB / {total_size_gb:.2f} GB)")
        logger.info(f"Remaining: {remaining_gb:.2f} GB")
        logger.info(f"Estimated time remaining: {estimated_hours_remaining:.1f} hours ({estimated_days_remaining:.1f} days)")

        if result.stdout:
            logger.info(f"Upload output: {result.stdout}")
        if result.stderr:
            logger.info(f"Upload stderr: {result.stderr}")

        successful_uploads += 1

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================

    script_total_time = time.time() - script_start_time
    script_total_hours = script_total_time / 3600
    script_total_days = script_total_hours / 24

    # Calculate overall statistics
    if upload_speeds:
        avg_speed_gb_per_hour = sum(upload_speeds) / len(upload_speeds)
        min_speed_gb_per_hour = min(upload_speeds)
        max_speed_gb_per_hour = max(upload_speeds)
    else:
        avg_speed_gb_per_hour = 0
        min_speed_gb_per_hour = 0
        max_speed_gb_per_hour = 0

    overall_speed_gb_per_hour = total_size_gb / script_total_hours if script_total_hours > 0 else 0

    logger.info("\n" + "="*80)
    logger.info("UPLOAD COMPLETED")
    logger.info("="*80)
    logger.info(f"Total files processed: {len(files_to_upload)}")
    logger.info(f"Successful uploads: {successful_uploads}")
    logger.info(f"Failed uploads: {failed_uploads}")
    logger.info(f"Total data uploaded: {total_size_gb:.2f} GB ({total_size_tb:.2f} TB)")
    logger.info(f"Total execution time: {script_total_time:.2f}s ({script_total_hours:.2f} hours / {script_total_days:.2f} days)")
    logger.info("")
    logger.info("UPLOAD SPEED STATISTICS:")
    logger.info(f"Average upload speed: {avg_speed_gb_per_hour:.2f} GB/hour")
    logger.info(f"Overall upload speed: {overall_speed_gb_per_hour:.2f} GB/hour")
    logger.info(f"Fastest upload: {max_speed_gb_per_hour:.2f} GB/hour")
    logger.info(f"Slowest upload: {min_speed_gb_per_hour:.2f} GB/hour")
    logger.info("")
    logger.info("PROJECTION FOR FULL 459 SESSIONS:")
    logger.info("Assuming each session has ~100-150 GB total (raw + processed):")

    # Conservative estimates for 459 sessions
    estimated_total_size_low_tb = 459 * 100 / 1024  # 100 GB per session in TB
    estimated_total_size_high_tb = 459 * 150 / 1024  # 150 GB per session in TB

    if avg_speed_gb_per_hour > 0:
        estimated_days_low = (estimated_total_size_low_tb * 1024) / avg_speed_gb_per_hour / 24
        estimated_days_high = (estimated_total_size_high_tb * 1024) / avg_speed_gb_per_hour / 24
        logger.info(f"Estimated total data: {estimated_total_size_low_tb:.2f} - {estimated_total_size_high_tb:.2f} TB")
        logger.info(f"Estimated upload time at {avg_speed_gb_per_hour:.2f} GB/hour:")
        logger.info(f"  Low estimate (100 GB/session): {estimated_days_low:.1f} days")
        logger.info(f"  High estimate (150 GB/session): {estimated_days_high:.1f} days")

    logger.info("="*80)

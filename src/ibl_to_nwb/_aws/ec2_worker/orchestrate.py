"""EC2 orchestrator: conversion + DANDI upload.

Called by boot.sh after system bootstrapping is complete.
Reads configuration from IBL_* environment variables set by boot.sh.

This script handles the full pipeline after the Python environment is ready:
  1. Downloads + converts the session (via convert_session from conversion.session)
  2. Prepares the DANDI folder structure (downloads dandiset.yaml, moves NWB files)
  3. Uploads to DANDI archive
  4. Emits machine-parseable log markers for monitor.py compatibility

Exit codes:
    0   = success
    1   = failure (conversion or upload)
    124 = timeout (phase-level, from SIGALRM)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Configuration read from IBL_* environment variables set by boot.sh."""

    session_eid: str
    session_index: str
    stub_test: bool
    instance_id: str
    instance_type: str
    region: str
    dandiset_id: str
    dandi_instance: str  # "dandi" or "dandi-sandbox"
    conversion_mode: str  # "", "--raw-only", or "--processed-only"
    verbose: bool
    display_progress_bar: bool
    mount_point: Path

    @classmethod
    def from_env(cls) -> Config:
        """Read all IBL_* environment variables. Raises SystemExit on missing required vars."""

        def _require(var: str) -> str:
            value = os.environ.get(var)
            if not value:
                raise SystemExit(f"Missing required environment variable: {var}")
            return value

        return cls(
            session_eid=_require("IBL_SESSION_EID"),
            session_index=os.environ.get("IBL_SESSION_INDEX", "unknown"),
            stub_test=os.environ.get("IBL_STUB_TEST", "false") == "true",
            instance_id=os.environ.get("IBL_INSTANCE_ID", "unknown"),
            instance_type=os.environ.get("IBL_INSTANCE_TYPE", "unknown"),
            region=os.environ.get("IBL_REGION", "unknown"),
            dandiset_id=_require("IBL_DANDISET_ID"),
            dandi_instance=_require("IBL_DANDI_INSTANCE"),
            conversion_mode=os.environ.get("IBL_CONVERSION_MODE", ""),
            verbose=os.environ.get("IBL_VERBOSE", "false") == "true",
            display_progress_bar=os.environ.get("IBL_DISPLAY_PROGRESS_BAR", "false") == "true",
            mount_point=Path(os.environ.get("IBL_MOUNT_POINT", "/ebs")),
        )

    @property
    def convert_raw(self) -> bool:
        return self.conversion_mode != "--processed-only"

    @property
    def convert_processed(self) -> bool:
        return self.conversion_mode != "--raw-only"


# ---------------------------------------------------------------------------
# Machine-parseable log markers (must match monitor.py expectations)
# ---------------------------------------------------------------------------


def log_phase_start(phase: str) -> None:
    print(f"=== PHASE: {phase} | START | {datetime.now(timezone.utc).isoformat()} ===", flush=True)


def log_phase_end(phase: str, start_time: float) -> None:
    duration = int(time.time() - start_time)
    print(
        f"=== PHASE: {phase} | END | {datetime.now(timezone.utc).isoformat()} | duration_seconds={duration} ===",
        flush=True,
    )


def log_disk_usage(label: str) -> None:
    print(f"=== DISK: {label} ===", flush=True)
    subprocess.run(["df", "-h", "/ebs"], check=False)
    print("=== END DISK ===", flush=True)


def emit_instance_metadata(config: Config) -> None:
    """Print instance metadata block for monitor.py and debugging."""
    print()
    print("=== INSTANCE_METADATA: START ===", flush=True)
    print(f"instance_id={config.instance_id}")
    print(f"instance_type={config.instance_type}")
    print(f"region={config.region}")
    print(f"session_eid={config.session_eid}")
    print(f"session_index={config.session_index}")
    print(f"stub_test={str(config.stub_test).lower()}")
    print(f"dandi_instance={config.dandi_instance}")
    print(f"dandiset_id={config.dandiset_id}")
    print(f"conversion_mode={config.conversion_mode or 'both'}")
    print(f"start_time={datetime.now(timezone.utc).isoformat()}")
    print("=== INSTANCE_METADATA: END ===", flush=True)
    print()


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def run_conversion(config: Config) -> dict:
    """Run the conversion phase by importing and calling convert_session() directly.

    Returns the conversion results dict from convert_session().

    Raises
    ------
    TimeoutError
        If any conversion phase exceeds its timeout.
    Exception
        If conversion fails for any other reason.
    """
    from ibl_to_nwb.conversion.session import convert_session, disable_tqdm_globally, PHASE_TIMEOUTS

    from one.api import ONE

    # Disable tqdm progress bars unless explicitly requested
    if not config.display_progress_bar:
        disable_tqdm_globally()

    from ibl_to_nwb.conversion.one_patches import apply_one_patches

    base_folder = config.mount_point
    logs_folder = base_folder / "conversion_logs"
    cache_dir = base_folder / "ibl_cache"
    nwb_folder = base_folder / "nwbfiles"

    # Create directory structure
    for folder in [logs_folder, cache_dir, nwb_folder]:
        folder.mkdir(parents=True, exist_ok=True)

    # Log mode for monitor.py text matching
    if config.stub_test:
        print("Running in STUB TEST mode (only metadata, no raw data)", flush=True)
    else:
        print("Running in PRODUCTION mode (full data conversion)", flush=True)

    if config.conversion_mode:
        print(f"Conversion mode: {config.conversion_mode}", flush=True)
    else:
        print("Conversion mode: both (raw + processed)", flush=True)

    if config.verbose:
        print("Verbose output: enabled", flush=True)
    if config.display_progress_bar:
        print("Progress bars: enabled", flush=True)

    # Initialize ONE API
    one = ONE(
        base_url="https://openalyx.internationalbrainlab.org",
        password="international",
        cache_dir=cache_dir,
        silent=True,
    )
    # Patch ONE's _check_filesystem to use hash-based validation before re-downloading.
    # Within a single download_session_data() call, some files (e.g. .ap.meta) are downloaded
    # by IblAnatomicalLocalizationInterface and then encountered again by IblSpikeGlxConverter.
    # Without the patch, ONE would re-download them if the Alyx database has stale size metadata.
    apply_one_patches(one, logger=None)

    # Log session info (monitor.py matches "PROCESSING SESSION")
    logging.info("\n" + "=" * 100)
    logging.info(f"PROCESSING SESSION: {config.session_eid} (index: {config.session_index})")
    logging.info("=" * 100)

    # Run conversion (with phase timeouts for AWS enforcement)
    result = convert_session(
        config.session_eid,
        one=one,
        base_folder=base_folder,
        logs_folder=logs_folder,
        stub_test=config.stub_test,
        convert_raw=config.convert_raw,
        convert_processed=config.convert_processed,
        verbose=config.verbose,
        display_progress_bar=config.display_progress_bar,
        phase_timeouts=PHASE_TIMEOUTS,
    )

    logging.info(f"Session {config.session_eid} completed successfully")

    # Save conversion summary
    summary_file = logs_folder / f"conversion_summary_{config.session_eid}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    summary = {
        "eid": config.session_eid,
        "session_index": config.session_index,
        "success": True,
        "conversion_time_seconds": result.get("total_time_seconds", 0),
        "stub_test": config.stub_test,
        "result": result,
    }
    summary_file.write_text(json.dumps(summary, indent=2, default=str))
    logging.info(f"Summary written to: {summary_file}")

    return result


# ---------------------------------------------------------------------------
# DANDI operations
# ---------------------------------------------------------------------------


def prepare_dandiset_folder(config: Config, nwb_folder: Path) -> Path:
    """Download dandiset.yaml and move NWB files into dandiset structure.

    Returns the dandiset folder path.
    """
    if config.dandi_instance == "dandi":
        dandi_url = f"https://dandiarchive.org/dandiset/{config.dandiset_id}"
    else:
        dandi_url = f"https://sandbox.dandiarchive.org/dandiset/{config.dandiset_id}"

    print(f"Downloading dandiset.yaml for dandiset {config.dandiset_id} from {config.dandi_instance}...", flush=True)
    subprocess.run(
        ["dandi", "download", "--download", "dandiset.yaml", dandi_url],
        cwd=str(nwb_folder),
        check=True,
    )

    dandiset_folder = nwb_folder / config.dandiset_id

    # Move converted NWB files from full/ or stub/ into dandiset folder
    print("Moving NWB files and videos into dandiset folder...", flush=True)
    for conversion_type in ("full", "stub"):
        conversion_output = nwb_folder / conversion_type
        if conversion_output.is_dir() and any(conversion_output.iterdir()):
            print(f"Moving files from {conversion_type}/ to dandiset folder...", flush=True)
            for subject_dir in sorted(conversion_output.glob("sub-*")):
                target = dandiset_folder / subject_dir.name
                if target.exists():
                    # Merge into existing directory
                    for item in subject_dir.iterdir():
                        shutil.move(str(item), str(target / item.name))
                    subject_dir.rmdir()
                else:
                    shutil.move(str(subject_dir), str(dandiset_folder))

    print("Files moved to dandiset folder", flush=True)
    return dandiset_folder


def collect_file_inventory(dandiset_folder: Path) -> dict:
    """Count NWB files and total size. Emit FILE_INVENTORY markers.

    Returns dict with nwb_count, nwb_total_bytes, nwb_total_gb.
    """
    nwb_files = list(dandiset_folder.rglob("*.nwb"))
    nwb_count = len(nwb_files)
    nwb_total_bytes = sum(f.stat().st_size for f in nwb_files) if nwb_files else 0
    nwb_total_gb = nwb_total_bytes / (1024**3)

    print("=== FILE_INVENTORY: START ===", flush=True)
    print(f"nwb_file_count={nwb_count}")
    print(f"nwb_total_bytes={nwb_total_bytes}")
    print(f"nwb_total_gb={nwb_total_gb:.2f}")
    print("=== FILE_INVENTORY: END ===", flush=True)

    # Debug: directory listing
    print()
    print("=== Contents of dandiset folder ===", flush=True)
    for item in sorted(dandiset_folder.iterdir()):
        size = item.stat().st_size
        print(f"  {item.name}  ({size} bytes)")
    print()
    print("=== Subject directories ===", flush=True)
    subject_dirs = sorted(dandiset_folder.glob("sub-*/"))
    if subject_dirs:
        for subject_dir in subject_dirs:
            print(f"  {subject_dir.name}/")
    else:
        print("No subject directories found")
    print()
    print("=== NWB files with sizes ===", flush=True)
    for nwb_file in nwb_files:
        size_gb = nwb_file.stat().st_size / (1024**3)
        print(f"  {nwb_file.relative_to(dandiset_folder)}  ({size_gb:.2f} GB)")
    print(flush=True)

    return {"nwb_count": nwb_count, "nwb_total_bytes": nwb_total_bytes, "nwb_total_gb": nwb_total_gb}


def upload_to_dandi(config: Config, dandiset_folder: Path, inventory: dict) -> dict:
    """Upload NWB files to DANDI with timeout.

    Uses dandi CLI via subprocess (proven to work, same output for monitor.py).
    Wrapped in PhaseTimeout for 3-hour SIGALRM timeout.

    Returns dict with upload_duration and upload_speed.
    """
    from ibl_to_nwb.conversion.session import PhaseTimeout

    upload_timeout = 10800  # 3 hours

    # Debug: Check if DANDI API keys are set
    print(f"DEBUG: DANDI_API_KEY is set: {'YES' if os.environ.get('DANDI_API_KEY') else 'NO'}")
    print(f"DEBUG: DANDI_SANDBOX_API_KEY is set: {'YES' if os.environ.get('DANDI_SANDBOX_API_KEY') else 'NO'}")
    print(f"DEBUG: Uploading to DANDI instance: {config.dandi_instance}")

    upload_cmd_start = time.time()
    print(f"=== DANDI_UPLOAD: START | {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S%z')} ===", flush=True)

    # Run dandi upload with timeout
    print("Uploading to DANDI...", flush=True)  # monitor.py key text
    with PhaseTimeout(upload_timeout, "dandi_upload"):
        subprocess.run(
            ["dandi", "upload", "-i", config.dandi_instance, "."],
            cwd=str(dandiset_folder),
            check=True,
        )

    upload_cmd_end = time.time()
    upload_duration = int(upload_cmd_end - upload_cmd_start)

    # Calculate upload speed
    nwb_total_gb = inventory.get("nwb_total_gb", 0)
    if nwb_total_gb > 0 and upload_duration > 0:
        upload_speed_mbps = round(nwb_total_gb * 1024 / upload_duration, 1)
    else:
        upload_speed_mbps = "unknown"

    print(
        f"=== DANDI_UPLOAD: END | duration_seconds={upload_duration}"
        f" | size_gb={nwb_total_gb:.2f}"
        f" | speed_mbps={upload_speed_mbps} ===",
        flush=True,
    )

    return {"upload_duration": upload_duration, "upload_speed_mbps": upload_speed_mbps}


def print_dandi_log() -> None:
    """Print the dandi-cli log file contents for debugging."""
    print()
    print("=== DANDI CLI Log ===", flush=True)
    dandi_log_dir = Path("/root/.local/state/dandi-cli/log")
    if dandi_log_dir.is_dir():
        log_files = sorted(dandi_log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        if log_files:
            dandi_log = log_files[0]
            print(f"Log file: {dandi_log}")
            print("--- Log contents ---")
            print(dandi_log.read_text())
            print("--- End of log ---")
        else:
            print(f"No DANDI log files found in {dandi_log_dir}")
    else:
        print(f"DANDI log directory not found: {dandi_log_dir}")
    print(flush=True)


def emit_final_summary(config: Config, inventory: dict, script_start: float) -> None:
    """Emit FINAL_SUMMARY and RESULT: SUCCESS markers."""
    total_duration = int(time.time() - script_start)
    total_minutes = total_duration // 60
    total_hours = round(total_duration / 3600, 2)

    print()
    print("=== FINAL_SUMMARY: START ===", flush=True)
    print(f"eid={config.session_eid}")
    print(f"session_index={config.session_index}")
    print(f"instance_id={config.instance_id}")
    print(f"stub_test={str(config.stub_test).lower()}")
    print(f"conversion_mode={config.conversion_mode or 'both'}")
    print(f"dandi_instance={config.dandi_instance}")
    print(f"dandiset_id={config.dandiset_id}")
    print(f"nwb_file_count={inventory.get('nwb_count', 0)}")
    print(f"nwb_total_gb={inventory.get('nwb_total_gb', 0):.2f}")
    print(f"total_duration_seconds={total_duration}")
    print(f"total_duration_minutes={total_minutes}")
    print(f"total_duration_hours={total_hours}")
    print("=== FINAL_SUMMARY: END ===", flush=True)
    print()
    print(f"=== RESULT: SUCCESS | eid={config.session_eid} | total_minutes={total_minutes} ===", flush=True)
    print("Upload complete.", flush=True)  # monitor.py key text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Main entry point. Returns exit code (0=success, 1=failure, 124=timeout)."""

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    config = Config.from_env()
    script_start = time.time()

    logging.info(f"Orchestrator started for session {config.session_eid} (index {config.session_index})")

    # --- Phase 1: Conversion ---
    log_phase_start("conversion")
    conversion_start = time.time()
    print("Starting conversion process...", flush=True)  # monitor.py key text

    try:
        result = run_conversion(config)
    except TimeoutError as exc:
        print(f"=== RESULT: TIMEOUT | eid={config.session_eid} | phase=conversion | {exc} ===", flush=True)
        logging.exception(f"Session {config.session_eid} FAILED due to timeout")
        return 124
    except Exception:
        logging.exception(f"Session {config.session_eid} FAILED")
        print(
            f"=== RESULT: FAILED | eid={config.session_eid} | phase=conversion | exit_code=1 ===",
            flush=True,
        )
        return 1

    log_phase_end("conversion", conversion_start)
    log_disk_usage("after_conversion")

    # --- Phase 2: Prepare DANDI folder ---
    nwb_folder = config.mount_point / "nwbfiles"

    try:
        dandiset_folder = prepare_dandiset_folder(config, nwb_folder)
    except Exception:
        logging.exception(f"DANDI folder preparation failed for {config.session_eid}")
        print(
            f"=== RESULT: FAILED | eid={config.session_eid} | phase=dandi_prep | exit_code=1 ===",
            flush=True,
        )
        return 1

    # --- Phase 3: Upload to DANDI ---
    log_phase_start("dandi_upload")
    upload_start = time.time()
    inventory = collect_file_inventory(dandiset_folder)

    try:
        upload_to_dandi(config, dandiset_folder, inventory)
    except TimeoutError:
        print(
            f"=== RESULT: TIMEOUT | eid={config.session_eid} | phase=dandi_upload | timeout_seconds=10800 ===",
            flush=True,
        )
        logging.error("DANDI upload exceeded 3-hour timeout")
        print_dandi_log()
        return 1
    except subprocess.CalledProcessError as exc:
        logging.exception(f"DANDI upload failed for {config.session_eid}")
        print(
            f"=== RESULT: FAILED | eid={config.session_eid} | phase=dandi_upload | exit_code={exc.returncode} ===",
            flush=True,
        )
        print_dandi_log()
        return 1
    except Exception:
        logging.exception(f"DANDI upload failed for {config.session_eid}")
        print(
            f"=== RESULT: FAILED | eid={config.session_eid} | phase=dandi_upload | exit_code=1 ===",
            flush=True,
        )
        print_dandi_log()
        return 1

    print_dandi_log()
    log_phase_end("dandi_upload", upload_start)

    # --- Phase 4: Final summary ---
    emit_final_summary(config, inventory, script_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())

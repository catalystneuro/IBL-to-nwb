"""Shared session conversion pipeline.

This module provides the single convert_session() function that all entry points
(local scripts and AWS pipeline) use to convert an IBL session to NWB format.

The pipeline:
  1. Download session data from ONE API
  2. Decompress raw ephys .cbin files (if converting raw, auto-detected)
  3. Convert raw ephys to NWB
  4. Convert processed/behavior to NWB

Phase timeouts are opt-in: pass phase_timeouts=PHASE_TIMEOUTS for AWS enforcement,
or omit for local runs (no SIGALRM, runs until done or Ctrl+C).
"""

from __future__ import annotations

import contextlib
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

from one.api import ONE

from ibl_to_nwb.conversion.download import download_session_data
from ibl_to_nwb.conversion.processed import convert_processed_session
from ibl_to_nwb.conversion.raw import convert_raw_session


def _setup_session_logger(log_file_path: Path) -> logging.Logger:
    """Configure a per-session logger that writes to disk and stdout."""

    logger = logging.getLogger(f"IBL_Conversion_{log_file_path.stem}")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    logger.propagate = False

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

    logging.captureWarnings(True)
    warnings_logger = logging.getLogger('py.warnings')
    warnings_logger.addHandler(file_handler)
    warnings_logger.addHandler(console_handler)

    return logger


# Re-export for backwards compatibility (callers may import from here)
from ibl_to_nwb.tqdm_utils import disable_tqdm_globally



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


def _phase_ctx(phase_key: str, phase_timeouts: dict | None):
    """Return a PhaseTimeout context manager if timeouts are configured, else nullcontext."""
    if phase_timeouts is not None and phase_key in phase_timeouts:
        return PhaseTimeout(phase_timeouts[phase_key], phase_key)
    return contextlib.nullcontext()


def _log_disk_usage(label: str, base_folder: Path) -> None:
    """Log disk usage of the base folder for tracking space consumption per phase."""
    print(f"=== DISK: {label} ===", flush=True)
    subprocess.run(["df", "-h", str(base_folder)], check=False)
    print("=== END DISK ===", flush=True)


def convert_session(
    eid: str,
    *,
    one: ONE,
    base_folder: Path,
    logs_folder: Path,
    stub_test: bool,
    convert_raw: bool,
    convert_processed: bool,
    overwrite: bool = False,
    redownload_data: bool = False,
    delete_cbins_after_decompression: bool = False,
    verbose: bool = False,
    display_progress_bar: bool = False,
    phase_timeouts: dict | None = None,
) -> dict:
    """Convert one IBL session to NWB format.

    Downloads data from ONE API, decompresses raw ephys if needed, converts to
    raw and processed NWB files, and writes them to disk.

    Parameters
    ----------
    eid : str
        Session EID.
    one : ONE
        Configured ONE API client.
    base_folder : Path
        Root folder for all data (cache, NWB output, etc.).
    logs_folder : Path
        Folder for per-session log files.
    stub_test : bool
        If True, use lightweight stub data.
    convert_raw : bool
        Whether to convert raw ephys data.
    convert_processed : bool
        Whether to convert processed/behavior data.
    overwrite : bool
        If True, overwrite existing NWB files. Default False.
    verbose : bool
        Enable verbose output from neuroconv interfaces.
    display_progress_bar : bool
        Show tqdm progress bars.
    phase_timeouts : dict or None
        Optional dict mapping phase names to timeout seconds. When None (default),
        no timeouts are applied. Pass PHASE_TIMEOUTS for AWS enforcement.

    Returns
    -------
    dict
        Conversion statistics including paths, sizes, timings, and success flag.

    Raises
    ------
    TimeoutError
        If any phase exceeds its timeout limit (only when phase_timeouts is set).
    """

    log_file = logs_folder / f"{time.strftime('%Y%m%d_%H%M%S')}_conversion_log_{eid}.log"
    logger = _setup_session_logger(log_file)

    logger.info("=" * 80)
    logger.info(f"Starting conversion for session: {eid}")
    logger.info(f"Stub test mode: {stub_test}")
    logger.info(f"Convert RAW: {convert_raw}")
    logger.info(f"Convert PROCESSED: {convert_processed}")
    logger.info(f"Overwrite: {overwrite}")
    logger.info(f"Verbose: {verbose}")
    logger.info(f"Display progress bar: {display_progress_bar}")
    if phase_timeouts:
        logger.info("Phase timeouts (seconds): %s", phase_timeouts)
    else:
        logger.info("Phase timeouts: disabled")
    logger.info("=" * 80)

    session_start = time.time()

    # Download session data
    # Skip raw ephys download if not converting raw (saves ~100 GB per session)
    logger.info("\n" + "=" * 80)
    logger.info("DOWNLOADING SESSION DATA")
    if phase_timeouts and "download" in phase_timeouts:
        logger.info(f"Timeout: {phase_timeouts['download']}s ({phase_timeouts['download']/3600:.1f} hours)")
    logger.info("=" * 80)
    download_start = time.time()

    with _phase_ctx("download", phase_timeouts):
        download_info = download_session_data(
            eid=eid,
            one=one,
            redownload_data=redownload_data,
            stub_test=stub_test,
            download_raw=convert_raw,
            download_processed=convert_processed,
            base_path=base_folder,
            logger=logger,
        )

    download_duration = time.time() - download_start
    logger.info(f"=== PHASE: download | duration_seconds={download_duration:.0f} | size_gb={download_info['total_size_gb']:.2f} ===")
    _log_disk_usage("after_download", base_folder)

    results = {
        "eid": eid,
        "download_size_gb": download_info["total_size_gb"],
        "download_duration_seconds": download_duration,
        "raw_converted": False,
        "processed_converted": False,
        "success": False,
    }

    # Convert RAW (with separate decompress and conversion phases)
    if convert_raw:
        # Lazy imports to avoid triggering spikeglx -> mtscomp -> tqdm chain
        # before disable_tqdm_globally() has a chance to patch tqdm
        from ibl_to_nwb.utils.ephys_decompression import decompress_ephys_cbins
        from ibl_to_nwb.utils.paths import setup_paths

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
            if phase_timeouts and "decompress" in phase_timeouts:
                logger.info(f"Timeout: {phase_timeouts['decompress']}s ({phase_timeouts['decompress']/3600:.1f} hours)")
            logger.info("=" * 80)

            decompress_start = time.time()

            with _phase_ctx("decompress", phase_timeouts):
                decompress_ephys_cbins(
                    source_folder=paths["session_folder"],
                    target_folder=paths["session_decompressed_ephys_folder"],
                )

            decompress_duration = time.time() - decompress_start
            logger.info(f"=== PHASE: decompress | duration_seconds={decompress_duration:.0f} ===")
            results["decompress_duration_seconds"] = decompress_duration

            # Optionally delete compressed .cbin files after decompression to free disk space.
            # Enabled on AWS (tight disk); disabled locally (avoids re-downloading).
            if delete_cbins_after_decompression:
                cbin_files = list(paths["session_folder"].rglob("*.cbin"))
                if cbin_files:
                    cbin_size_bytes = sum(f.stat().st_size for f in cbin_files)
                    cbin_size_gb = cbin_size_bytes / (1024**3)
                    for cbin_file in cbin_files:
                        cbin_file.unlink()
                    logger.info(f"Deleted {len(cbin_files)} .cbin files ({cbin_size_gb:.1f} GB) to free disk space")

            _log_disk_usage("after_decompress", base_folder)

        logger.info("\n" + "=" * 80)
        logger.info("CONVERTING RAW EPHYS")
        if phase_timeouts and "raw_conversion" in phase_timeouts:
            logger.info(f"Timeout: {phase_timeouts['raw_conversion']}s ({phase_timeouts['raw_conversion']/3600:.1f} hours)")
        logger.info("=" * 80)

        raw_start = time.time()

        with _phase_ctx("raw_conversion", phase_timeouts):
            raw_info = convert_raw_session(
                eid=eid,
                one=one,
                stub_test=stub_test,
                base_path=base_folder,
                logger=logger,
                overwrite=overwrite,
                verbose=verbose,
                display_progress_bar=display_progress_bar,
            )

        raw_duration = time.time() - raw_start

        if raw_info and not raw_info.get("skipped"):
            raw_nwb_path = raw_info["nwbfile_path"]
            results["raw_nwb_path"] = str(raw_nwb_path)
            results["raw_size_gb"] = raw_info["nwb_size_gb"]
            results["raw_size_bytes"] = raw_info["nwb_size_bytes"]
            results["raw_duration_seconds"] = raw_duration
            results["raw_converted"] = True
            logger.info(f"RAW file written to: {raw_nwb_path}")
            logger.info(f"=== PHASE: raw_conversion | duration_seconds={raw_duration:.0f} | size_gb={raw_info['nwb_size_gb']:.2f} ===")
            _log_disk_usage("after_raw_conversion", base_folder)
        elif raw_info and raw_info.get("skipped"):
            results["raw_skipped"] = True

    # Convert PROCESSED
    if convert_processed:
        logger.info("\n" + "=" * 80)
        logger.info("CONVERTING PROCESSED/BEHAVIOR")
        if phase_timeouts and "processed_conversion" in phase_timeouts:
            logger.info(f"Timeout: {phase_timeouts['processed_conversion']}s ({phase_timeouts['processed_conversion']/60:.0f} minutes)")
        logger.info("=" * 80)

        processed_start = time.time()

        with _phase_ctx("processed_conversion", phase_timeouts):
            processed_info = convert_processed_session(
                eid=eid,
                one=one,
                stub_test=stub_test,
                base_path=base_folder,
                logger=logger,
                overwrite=overwrite,
                verbose=verbose,
                display_progress_bar=display_progress_bar,
            )

        processed_duration = time.time() - processed_start

        if processed_info and not processed_info.get("skipped"):
            processed_nwb_path = processed_info["nwbfile_path"]
            results["processed_nwb_path"] = str(processed_nwb_path)
            results["processed_size_gb"] = processed_info["nwb_size_gb"]
            results["processed_size_bytes"] = processed_info["nwb_size_bytes"]
            results["processed_duration_seconds"] = processed_duration
            results["processed_converted"] = True
            logger.info(f"PROCESSED file written to: {processed_nwb_path}")
            logger.info(f"=== PHASE: processed_conversion | duration_seconds={processed_duration:.0f} | size_gb={processed_info['nwb_size_gb']:.2f} ===")
            _log_disk_usage("after_processed_conversion", base_folder)
        elif processed_info and processed_info.get("skipped"):
            results["processed_skipped"] = True

    session_time = time.time() - session_start
    results["total_time_seconds"] = session_time
    results["download_info"] = download_info
    results["success"] = True

    logger.info("\n" + "=" * 80)
    logger.info("SESSION COMPLETED")
    logger.info(f"Total time: {session_time:.2f}s ({session_time/60:.2f} minutes)")
    logger.info(f"RAW converted: {results['raw_converted']}")
    logger.info(f"PROCESSED converted: {results['processed_converted']}")
    logger.info("=" * 80)

    return results

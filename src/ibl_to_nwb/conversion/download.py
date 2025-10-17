from __future__ import annotations

import logging
import time
from pathlib import Path

from one.api import ONE

from ..bwm_to_nwb import setup_paths


def download_session_data(
    eid: str,
    one: ONE,
    redownload_data: bool = False,
    stub_test: bool = False,
    revision: str | None = None,
    base_path: Path | None = None,
    scratch_path: Path | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    """Download all datasets for a session from ONE API."""
    if logger:
        logger.info(
            "Downloading session data from ONE%s..."
            % (f" (revision {revision})" if revision else "")
        )
    download_start = time.time()

    # Setup paths to check cache location
    paths = setup_paths(one, eid, base_path=base_path, scratch_path=scratch_path)

    # Check if we need to clear cached data
    if redownload_data and paths["session_folder"].exists():
        if logger:
            logger.info(f"REDOWNLOAD_DATA is True - clearing cached data for session {eid}")
        # Remove cached files for this session
        import shutil

        shutil.rmtree(paths["session_folder"])
        paths["session_folder"].mkdir(parents=True, exist_ok=True)

    # Download all datasets for this session
    datasets = one.list_datasets(eid, revision=revision) if revision else one.list_datasets(eid)
    skipped_datasets = []
    if stub_test:
        skip_patterns = (
            "raw_ephys_data",
            "raw_video_data",
            "spikes.amps",
            "spikes.depths",
            "spikes.waveforms",
            "spikes.samples",
            "spikes.templates",
            "templates.waveforms",
            "templates.amps",
            "clusters.waveforms",
            "waveforms.",
        )
        filtered_datasets = []
        for dataset in datasets:
            if any(pattern in dataset for pattern in skip_patterns):
                skipped_datasets.append(dataset)
                continue
            filtered_datasets.append(dataset)
        if logger and skipped_datasets:
            logger.info(
                "Stub mode active: skipping download of %d heavy datasets"
                % len(skipped_datasets)
            )
        datasets = filtered_datasets

    if logger:
        logger.info(f"Found {len(datasets)} datasets to download")

    # Check if data is already cached
    cached_files = list(paths["session_folder"].rglob("*")) if paths["session_folder"].exists() else []
    if cached_files and not redownload_data:
        if logger:
            logger.info(f"Using cached data from {paths['session_folder']} ({len(cached_files)} files)")
    else:
        if logger:
            logger.info("Downloading data from ONE API...")

    for dataset in datasets:
        one.load_dataset(eid, dataset)

    download_time = time.time() - download_start

    # Calculate total size of downloaded data
    total_size_bytes = 0
    if paths["session_folder"].exists():
        for file_path in paths["session_folder"].rglob("*"):
            if file_path.is_file():
                total_size_bytes += file_path.stat().st_size

    total_size_gb = total_size_bytes / (1024**3)

    if logger:
        logger.info(f"Download step completed in {download_time:.2f}s")
        logger.info(f"Total downloaded data size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")
        logger.info(f"Download rate: {total_size_gb / (download_time / 3600):.2f} GB/hour")

    return {
        "download_time": download_time,
        "num_datasets": len(datasets),
        "total_size_bytes": total_size_bytes,
        "total_size_gb": total_size_gb,
    }

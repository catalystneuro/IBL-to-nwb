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
    base_datasets = set(one.list_datasets(eid))

    revision_datasets: set[str] = set()
    if revision:
        revision_datasets = set(one.list_datasets(eid, revision=revision))
        revision_datasets.discard("default_revision")

        revision_folder = f"/#{revision}#/"
        revision_bases = {
            dataset.replace(revision_folder, "/")
            for dataset in revision_datasets
            if revision_folder in dataset
        }
        base_datasets -= revision_bases

    datasets = sorted(base_datasets | revision_datasets)
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
    has_cached_data = len(cached_files) > 0 and not redownload_data

    if has_cached_data:
        if logger:
            logger.info(f"Found {len(cached_files)} cached files in {paths['session_folder']}")
            logger.info("Verifying cached data (ONE will download any missing/corrupted files)...")
    else:
        if logger:
            if redownload_data:
                logger.info("Redownload flag set: downloading all data from ONE API...")
            else:
                logger.info("No cached data found: downloading from ONE API...")

    # Track which files were actually downloaded (new files)
    files_before = set(paths["session_folder"].rglob("*")) if paths["session_folder"].exists() else set()

    for dataset in datasets:
        if dataset == "default_revision":
            continue

        # If the dataset path already contains an explicit revision collection,
        # request it directly without passing the revision argument.
        if revision and dataset in revision_datasets and f"/#{revision}#/" not in dataset:
            one.load_dataset(eid, dataset, revision=revision)
        else:
            one.load_dataset(eid, dataset)

    download_time = time.time() - download_start

    # Calculate total size and track what was actually downloaded
    files_after = set(paths["session_folder"].rglob("*")) if paths["session_folder"].exists() else set()
    newly_downloaded_files = files_after - files_before
    num_new_files = len([f for f in newly_downloaded_files if f.is_file()])

    total_size_bytes = 0
    if paths["session_folder"].exists():
        for file_path in paths["session_folder"].rglob("*"):
            if file_path.is_file():
                total_size_bytes += file_path.stat().st_size

    total_size_gb = total_size_bytes / (1024**3)

    if logger:
        logger.info(f"Download step completed in {download_time:.2f}s")

        if num_new_files > 0:
            # Some files were actually downloaded
            logger.info(f"Downloaded {num_new_files} new/updated files")
            logger.info(f"Total data after download: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")
            if download_time > 0:
                download_rate = total_size_gb / (download_time / 3600)
                logger.info(f"Download rate: {download_rate:.2f} GB/hour")
        elif has_cached_data:
            # All data was cached, nothing new downloaded
            logger.info(f"All data was already cached - no new downloads needed")
            logger.info(f"Total cached data size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")
        else:
            # No files at all (shouldn't happen)
            logger.info(f"Total data size: {total_size_gb:.2f} GB ({total_size_bytes:,} bytes)")

    return {
        "download_time": download_time,
        "num_datasets": len(datasets),
        "total_size_bytes": total_size_bytes,
        "total_size_gb": total_size_gb,
    }

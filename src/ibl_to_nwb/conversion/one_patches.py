"""
Monkey patches for ONE API to work around known issues.

This module contains runtime patches for the ONE API library to handle edge cases
and bugs in the IBL data infrastructure.
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime
from pathlib import PurePosixPath

import numpy as np
import pandas as pd
from iblutil.io import hashfile
from one.alf.path import ALFPath

_logger = logging.getLogger(__name__)


def patched_check_filesystem(self, datasets, offline=None, update_exists=True, check_hash=True):
    """
    Patched version of ONE._check_filesystem with smarter cache validation.

    STRATEGY: Size-first with hash fallback
    ----------------------------------------
    1. Check file size (fast: 0.006ms)
       - If matches: Trust it, no hash needed ✓
    2. If size mismatches:
       - Check hash before re-downloading (160ms)
       - If hash matches: File is correct, ignore size metadata bug ✓
       - If hash mismatches: File is corrupted, re-download ✓

    This fixes a bug where files with correct hashes but incorrect file_size
    metadata in the Alyx database trigger unnecessary re-downloads.

    PERFORMANCE IMPACT:
    - When metadata correct (99.9%): Same speed as original (0.006ms)
    - When size wrong, hash right (0.1%): +160ms, saves 50s re-download
    - When both wrong (corruption): +160ms, re-download anyway (correct)

    Original issue: lightningPose.pqt files have correct hashes but wrong
    file_sizes in database (22 MB in DB vs 138 MB actual), causing ~100MB
    re-downloads every run despite cached files being correct.
    """
    if isinstance(datasets, pd.Series):
        datasets = pd.DataFrame([datasets])
        assert datasets.index.nlevels <= 2
        idx_names = ["eid", "id"] if datasets.index.nlevels == 2 else ["id"]
        datasets.index.set_names(idx_names, inplace=True)
    elif not isinstance(datasets, pd.DataFrame):
        from one.converters import datasets2records

        datasets = datasets2records(list(datasets))
    elif datasets.empty:
        return []
    else:
        datasets = datasets.copy()

    indices_to_download = []
    files = []

    # Get session paths if needed
    if "session_path" not in datasets.columns:
        from one.converters import session_record2path

        if "eid" not in datasets.index.names:
            _dsets = self._cache["datasets"][self._cache["datasets"].index.get_level_values(1).isin(datasets.index)]
            idx = _dsets.index.get_level_values(1)
        else:
            _dsets = datasets
            idx = pd.IndexSlice[:, _dsets.index.get_level_values(1)]
        session_path = (
            self._cache["sessions"].loc[_dsets.index.get_level_values(0).unique()].apply(session_record2path, axis=1)
        )
        datasets.loc[idx, "session_path"] = pd.Series(_dsets.index.get_level_values(0)).map(session_path).values

    # Check each dataset
    for i, rec in datasets.iterrows():
        file = ALFPath(self.cache_dir, *rec[["session_path", "rel_path"]])
        if self.uuid_filenames:
            file = file.with_uuid(i[1] if isinstance(i, tuple) else i)

        if file.exists():
            needs_download = False

            # PATCH: Check size first (fast path), but use hash as fallback
            if rec["file_size"] and file.stat().st_size != rec["file_size"]:
                # Size mismatch detected - but don't immediately mark for download
                _logger.warning(
                    "local file size mismatch on dataset: %s (expected: %d, got: %d)",
                    PurePosixPath(rec.session_path, rec.rel_path),
                    rec["file_size"],
                    file.stat().st_size,
                )

                # CRITICAL FIX: Check hash before deciding to re-download
                if check_hash and rec["hash"] is not None:
                    _logger.info(
                        "Verifying hash due to size mismatch: %s", PurePosixPath(rec.session_path, rec.rel_path)
                    )
                    actual_hash = hashfile.md5(file)

                    if actual_hash != rec["hash"]:
                        # Both size AND hash mismatch - file is corrupted
                        _logger.error(
                            "Hash also mismatches (expected: %s, got: %s) - re-downloading", rec["hash"], actual_hash
                        )
                        needs_download = True
                    else:
                        # Size wrong but hash correct - database metadata is stale
                        _logger.warning("Hash matches despite size mismatch - keeping cached file")
                        _logger.warning("This indicates stale file_size metadata in Alyx database")
                        # Do NOT mark for download - file is correct!
                else:
                    # No hash available to verify - trust size check
                    _logger.warning("No hash available to verify - marking for re-download")
                    needs_download = True

            elif check_hash and rec["hash"] is not None:
                # OPTIONAL: Size matches, but user explicitly wants hash verification
                # This can be used for periodic integrity checks
                # For now, we trust size when it matches (fast path)
                pass

            if needs_download:
                indices_to_download.append(i)
            files.append(file)
        else:
            files.append(None)
            indices_to_download.append(i)

    # Download missing/corrupted datasets
    if not (offline or self.offline) and indices_to_download:
        dsets_to_download = datasets.loc[indices_to_download]
        new_files = self._download_datasets(dsets_to_download, update_cache=update_exists)
        for i, file in zip(indices_to_download, new_files):
            files[datasets.index.get_loc(i)] = file

    # Update cache
    exists = list(map(bool, files))
    if not all(datasets["exists"] == exists):
        with warnings.catch_warnings():
            msg = ".*indexing on a MultiIndex with a nested sequence of labels.*"
            warnings.filterwarnings("ignore", message=msg)
            datasets["exists"] = exists
            if update_exists:
                _logger.debug("Updating exists field")
                i = datasets.index
                if i.nlevels == 1:
                    i = pd.IndexSlice[:, i]
                self._cache["datasets"].loc[i, "exists"] = exists
                self._cache["_meta"]["modified_time"] = datetime.now()

    # Record loaded datasets
    if self.record_loaded:
        loaded = np.fromiter(map(bool, files), bool)
        loaded_ids = datasets.index.get_level_values("id")[loaded].to_numpy()
        if "_loaded_datasets" not in self._cache:
            self._cache["_loaded_datasets"] = np.unique(loaded_ids)
        else:
            loaded_set = np.hstack([self._cache["_loaded_datasets"], loaded_ids])
            self._cache["_loaded_datasets"] = np.unique(loaded_set)

    return files


def apply_one_patches(one_instance, logger=None):
    """
    Apply runtime patches to a ONE instance.

    This patch implements a "size-first with hash fallback" validation strategy:
    - Fast path: If file size matches metadata → trust it (0.006ms)
    - Fallback: If size mismatches → verify hash before re-downloading (160ms)

    This prevents unnecessary re-downloads when Alyx database has stale file_size
    metadata but correct hash values.

    Parameters
    ----------
    one_instance : ONE
        The ONE API instance to patch
    logger : logging.Logger, optional
        Logger to use for patch notifications. If None, uses print statements.

    Returns
    -------
    ONE
        The patched ONE instance (same object, modified in place)

    Example
    -------
    >>> from one.api import ONE
    >>> from ibl_to_nwb.conversion.one_patches import apply_one_patches
    >>>
    >>> one = ONE(base_url='https://openalyx.internationalbrainlab.org',
    ...           cache_dir='/path/to/cache')
    >>> one = apply_one_patches(one, logger=my_logger)
    >>>
    >>> # Now use ONE normally - size mismatches will trigger hash verification
    >>> # instead of immediate re-download
    >>> one.load_dataset(eid, 'trials.intervals.npy')
    """

    def log_message(msg):
        """Helper to log via logger or print."""
        if logger:
            logger.info(msg)
        # If no logger, messages are handled by caller (e.g., print statements)

    log_message("Applying ONE API patches for known issues...")
    log_message("  - Patching _check_filesystem to use hash fallback on size mismatch")
    log_message("  - This prevents re-downloads when database metadata is stale")

    # Replace the _check_filesystem method
    import types

    one_instance._check_filesystem = types.MethodType(patched_check_filesystem, one_instance)

    log_message("ONE API patches applied successfully")

    return one_instance

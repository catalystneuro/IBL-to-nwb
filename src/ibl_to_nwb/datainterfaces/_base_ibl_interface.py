"""
Base class for IBL data interfaces with standardized data requirement methods.

This module provides an abstract base class that all IBL data interfaces should inherit from.
It defines a three-method pattern for declaring, checking, and downloading data requirements:

1. get_data_requirements() - Declares exactly what data is needed (single source of truth)
2. check_availability() - Checks if required data exists without downloading
3. download_data() - Downloads the required data, failing loudly if unavailable

Additionally, interfaces that use ONE API loading should implement:

4. get_load_object_kwargs() - Returns kwargs for one.load_object() calls
5. get_load_dataset_kwargs() - Returns kwargs for one.load_dataset() calls

These methods provide a single source of truth for loading parameters, used by both
download_data() and add_to_nwbfile(). This avoids duplicating collection names, object
names, and other loading parameters in multiple places.

Philosophy: Fail-fast. Missing required data should raise exceptions, not be silently caught.
This ensures data quality issues are caught early and conversion failures are explicit.
"""

import logging
from abc import abstractmethod
from typing import Optional

from neuroconv.basedatainterface import BaseDataInterface
from one.api import ONE


class BaseIBLDataInterface(BaseDataInterface):
    """
    Abstract base class for IBL data interfaces.

    All IBL data interfaces should inherit from this class and implement
    the three required class methods for data management.

    Class Attributes
    ----------------
    REVISION : str | None
        Default revision for this interface's data. Subclasses MUST override this.
        - None: Raw data (no revision filtering) - e.g., raw videos, raw ephys
        - "2025-05-06": Specific revision (Brain-Wide Map standard for processed data)
        - Can be overridden at runtime by passing revision parameter to methods

    Design Principles
    -----------------
    1. Single Source of Truth: get_data_requirements() declares exact files needed
    2. Read-Only Checking: check_availability() never downloads, only checks existence
    3. Fail-Fast: download_data() raises exceptions for missing required data
    4. Provenance: Exact file paths are documented for audit trails
    5. No Silent Failures: Missing data causes loud, explicit failures

    Loading Methods
    ---------------
    Interfaces that use ONE API should implement one of:

    get_load_object_kwargs(**kwargs) -> dict | list[dict]
        Returns kwargs for one.load_object() call(s). Use dict for single object,
        list[dict] for multiple objects. Example:
            {"obj": "wheel", "collection": "alf"}

    get_load_dataset_kwargs(**kwargs) -> dict
        Returns kwargs for one.load_dataset() call. Example:
            {"dataset": "licks.times", "collection": "alf"}

    get_session_loader_kwargs(**kwargs) -> dict
        Returns kwargs for SessionLoader method calls (e.g., load_pose, load_trials).
        Used when the interface uses brainbox.io.one.SessionLoader. Example:
            {"tracker": "lightningPose", "views": ["left"]}

    These are used by download_data() and add_to_nwbfile() to avoid duplicating
    loading parameters. The kwargs should NOT include id/eid, revision, or
    download_only - those are always added by the caller.
    """

    # Subclasses MUST override this to explicitly declare revision requirement
    REVISION: str | None = None

    @classmethod
    @abstractmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare the exact data files required by this interface.

        This is the SINGLE SOURCE OF TRUTH for data requirements.
        Returns exact file paths for provenance and audit trails.

        Used by:
        - Documentation: To list exact files converted
        - Diagnose script: To check data availability across sessions
        - Download script: To download only required files
        - check_availability(): To verify data exists
        - download_data(): To fetch required files

        Parameters
        ----------
        **kwargs : dict
            Interface-specific parameters (e.g., camera_name for video interfaces,
            probe_name_to_probe_id_dict for probe-based interfaces)

        Returns
        -------
        dict
            Dictionary with standardized structure:
            {
                "exact_files_options": {  # Named file format options (required)
                    "option_name": [str, ...],  # List of files for this option
                    # Examples:
                    # "standard": ["alf/wheel.position.npy", "alf/wheel.timestamps.npy"]
                    # "lightning_pose": ["alf/_ibl_leftCamera.lightningPose.pqt"]
                    # "dlc": ["alf/_ibl_leftCamera.dlc.pqt"]
                    #
                    # Behavior:
                    # - ANY complete option = data available (order doesn't matter)
                    # - An option is complete when ALL its files exist
                    # - Supports wildcards: "alf/probe*/spikes.times.npy"
                    # - Supports _ibl_ namespace: tries both "wheel.position" and "_ibl_wheel.position"
                },
            }

            Note: If there's only one format, still use a dict with a descriptive name:
            {"standard": ["file1.npy", "file2.npy"]}
        """
        raise NotImplementedError(f"{cls.__name__} must implement get_data_requirements() class method")

    @classmethod
    def check_quality(cls, one: ONE, eid: str, logger: Optional[logging.Logger] = None, **kwargs) -> Optional[dict]:
        """
        Check data quality (QC) before checking file availability.

        Override this method to add quality control filtering. Called by
        check_availability() before checking file existence.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        logger : logging.Logger, optional
            Logger for progress tracking
        **kwargs
            Additional parameters (e.g., camera_name)

        Returns
        -------
        Optional[dict]
            - None: No quality issues, proceed with file check
            - {"available": False, "reason": str, ...}: Reject with reason
            - {"extra_field": value, ...}: Extra fields to merge into result
              (without "available" key = no rejection, just extra data)
        """
        return None

    @classmethod
    def check_availability(cls, one: ONE, eid: str, logger: Optional[logging.Logger] = None, **kwargs) -> dict:
        """
        Check if required data is available for a specific session.

        This method NEVER downloads data - it only checks if files exist
        using one.list_datasets(). It's designed to be fast and read-only,
        suitable for scanning many sessions.

        NO try-except patterns that hide failures. If checking fails,
        let the exception propagate.

        NOTE: Does NOT use revision filtering in check_availability(). Queries for latest
        version of all files regardless of revision tags. This matches the smart fallback
        behavior of load_object() and download methods, which try requested revision first
        but fall back to latest if not found.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID (experiment ID)
        logger : logging.Logger, optional
            Logger for progress/warning messages
        **kwargs : dict
            Interface-specific parameters

        Returns
        -------
        dict
            {
                "available": bool,              # Overall availability
                "missing_required": [str],      # Missing required files
                "found_files": [str],           # Files that exist
                "alternative_used": str,        # Which alternative was found (if applicable)
                "requirements": dict,           # Copy of get_data_requirements()
            }

        Examples
        --------
        >>> result = WheelInterface.check_availability(one, eid)
        >>> if not result["available"]:
        >>>     print(f"Missing: {result['missing_required']}")
        """
        # STEP 1: Check quality (QC filtering)
        quality_result = cls.check_quality(one=one, eid=eid, logger=logger, **kwargs)

        if quality_result is not None:
            # If quality check explicitly rejects, return immediately
            if quality_result.get("available") is False:
                return quality_result
            # Otherwise, save extra fields to merge later
            extra_fields = quality_result
        else:
            extra_fields = {}

        # STEP 2: Check file existence
        requirements = cls.get_data_requirements(**kwargs)

        # Query without revision filtering to get latest version of ALL files
        # This includes both revision-tagged files (spike sorting) and untagged files (behavioral)
        # The unfiltered query returns the superset of what any revision-specific query would return
        available_datasets = one.list_datasets(eid)
        available_files = set(str(d) for d in available_datasets)

        missing_required = []
        found_files = []
        alternative_used = None

        # Check file options - this is now REQUIRED (not optional)
        # Every interface must define exact_files_options dict
        exact_files_options = requirements.get("exact_files_options", {})

        if not exact_files_options:
            raise ValueError(
                f"{cls.__name__}.get_data_requirements() must return 'exact_files_options' dict. "
                f"Even for single-format interfaces, use: {{'standard': ['file1.npy', 'file2.npy']}}"
            )

        # Check each named option - ANY complete option = available
        for option_name, option_files in exact_files_options.items():
            all_files_found = True

            for exact_file in option_files:
                # Handle wildcards
                if "*" in exact_file:
                    import re

                    pattern = re.escape(exact_file).replace(r"\*", ".*")
                    found = any(re.search(pattern, avail) for avail in available_files)
                else:
                    # Check both with and without _ibl_ namespace prefix
                    # Need to handle revision tags like: alf/#2025-06-18#/_ibl_leftCamera.features.pqt
                    import re

                    # Build pattern that matches with or without revision tags
                    # e.g., "alf/leftCamera.features.pqt" should match "alf/#2025-06-18#/leftCamera.features.pqt"
                    parts = exact_file.split("/")
                    if len(parts) >= 2:
                        collection = parts[0]
                        filename = parts[-1]

                        # Pattern 1: without _ibl_ prefix (with optional revision tag)
                        pattern1 = re.escape(f"{collection}/") + r"(#[^#]+#/)?" + re.escape(filename)

                        # Pattern 2: with _ibl_ prefix (with optional revision tag)
                        pattern2 = re.escape(f"{collection}/") + r"(#[^#]+#/)?" + re.escape(f"_ibl_{filename}")

                        found = any(
                            re.search(pattern1, avail) or re.search(pattern2, avail) for avail in available_files
                        )
                    else:
                        # Fallback for single-part paths
                        found = any(exact_file in avail for avail in available_files)

                if not found:
                    all_files_found = False
                    break  # This option is incomplete

            # If this option has all files, mark as available
            if all_files_found:
                found_files.extend(option_files)
                alternative_used = option_name  # Report which option was found
                break  # Found one complete option, that's enough

        # If no options were complete, mark the first option as missing for reporting
        if not alternative_used:
            first_option_name = next(iter(exact_files_options.keys()))
            missing_required.extend(exact_files_options[first_option_name])

        # STEP 3: Build result and merge extra fields from quality check
        result = {
            "available": len(missing_required) == 0,
            "missing_required": missing_required,
            "found_files": found_files,
            "alternative_used": alternative_used,
            "requirements": requirements,
        }
        result.update(extra_fields)

        return result

    @classmethod
    def download_data(
        cls, one: ONE, eid: str, download_only: bool = True, logger: Optional[logging.Logger] = None, **kwargs
    ) -> dict:
        """
        Download required data for this interface.

        Uses ONE API to download data. NO try-except patterns that hide
        failures - if downloads fail, exceptions propagate. This is intentional:
        missing required data should cause loud, explicit failures.

        Respects ONE's caching - won't re-download if already cached.

        NOTE: Uses the class-level REVISION attribute. Does not accept revision
        parameter - each interface defines its own required revision.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID (experiment ID)
        download_only : bool, default=True
            If True, download but don't load into memory
            If False, download and return loaded data
        logger : logging.Logger, optional
            Logger for progress tracking
        **kwargs : dict
            Interface-specific parameters

        Returns
        -------
        dict
            {
                "success": bool,                    # Overall success
                "downloaded_files": [str],          # Exact files downloaded
                "already_cached": [str],            # Files that were already cached
                "alternative_used": str,            # Which alternative was used (if applicable)
                "data": dict or None,               # Loaded data if download_only=False
            }

        Raises
        ------
        FileNotFoundError
            If required files are missing and no alternatives exist
        Exception
            Any ONE API exceptions (let them propagate - fail fast!)

        Examples
        --------
        >>> result = WheelInterface.download_data(one, eid, logger=logger)
        >>> print(f"Downloaded: {result['downloaded_files']}")
        """
        requirements = cls.get_data_requirements(**kwargs)

        # Use the class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(
                f"Downloading {cls.__name__} data for session {eid}" + (f" (revision {revision})" if revision else "")
            )

        downloaded_files = []
        already_cached = []
        loaded_data = {} if not download_only else None
        alternative_used = None

        # Download files from exact_files_options
        # Try each format option until one succeeds
        exact_files_options = requirements.get("exact_files_options", {})

        for option_name, files in exact_files_options.items():
            try:
                for file_path in files:
                    if logger:
                        logger.info(f"  Loading file: {file_path}")
                    # Parse file path into collection and dataset name for proper revision handling
                    # ONE API requires collection/revision as kwargs, not embedded in path
                    parts = file_path.split("/")
                    if len(parts) >= 2:
                        collection = "/".join(parts[:-1])
                        filename = parts[-1]
                    else:
                        collection = None
                        filename = file_path

                    one.load_dataset(
                        eid, filename, collection=collection, revision=revision, download_only=download_only
                    )
                    downloaded_files.append(file_path)
                alternative_used = option_name
                break  # Successfully downloaded all files for this option
            except Exception:
                downloaded_files = []  # Reset for next option
                continue  # Try next format option

        if not alternative_used and exact_files_options:
            # FAIL LOUDLY - no option worked
            raise FileNotFoundError(
                f"No complete format option available for {cls.__name__}. "
                f"Tried options: {list(exact_files_options.keys())}"
            )

        return {
            "success": True,
            "downloaded_files": downloaded_files,
            "already_cached": already_cached,
            "alternative_used": alternative_used,
            "data": loaded_data,
        }

"""
Interface for passive receptive field mapping (RFM) stimuli.

This module provides an interface for adding receptive field mapping visual stimulus data
to NWB files during passive periods.
"""

import logging
from typing import Optional
import time

import numpy as np
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile, TimeSeries

from ._base_ibl_interface import BaseIBLDataInterface


class PassiveRFMInterface(BaseIBLDataInterface):
    """
    Interface for passive receptive field mapping (RFM) stimulus data.

    This interface handles the visual stimulus data used for receptive field mapping
    during passive periods.
    """

    # Passive data was re-released with new revisions (2025-12-04 and 2025-12-05).
    # We query ONE API to find which revision is available and pick the last one.
    REVISION_CANDIDATES: list[str] = ["2025-12-04", "2025-12-05"]

    @staticmethod
    def _resolve_revision(one: ONE, eid: str, candidates: list[str]) -> str | None:
        """
        Find the last available revision from candidates list.

        Queries ONE API to check which revisions have passive data available.
        Returns the last matching revision (preferring 2025-12-05 over 2025-12-04).

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        candidates : list[str]
            List of revision candidates to check, in order

        Returns
        -------
        str | None
            The last available revision, or None if none found
        """
        datasets = one.list_datasets(eid)
        dataset_strs = [str(d) for d in datasets]

        found_revision = None
        for revision in candidates:
            revision_tag = f"#{revision}#"
            if any(revision_tag in ds for ds in dataset_strs):
                found_revision = revision

        return found_revision

    def __init__(
        self,
        one: ONE,
        session: str,
    ):
        """
        Initialize the passive RFM interface.

        Parameters
        ----------
        one : ONE
            ONE API instance for data access
        session : str
            Session ID (eid)
        """
        super().__init__()
        self.one = one
        self.session = session
        self.revision = self._resolve_revision(one, session, self.REVISION_CANDIDATES)

        # Load RFM data - will fail loudly if data missing
        self.rfm_times = one.load_dataset(
            session,
            "_ibl_passiveRFM.times.npy",
            collection="alf",
            revision=self.revision
        )
        rfm_path = one.load_dataset(
            session,
            "_iblrig_RFMapStim.raw.bin",
            collection="raw_passive_data",
            revision=self.revision
        )
        self.rfm_data = np.fromfile(rfm_path, dtype=np.uint8).reshape(
            (self.rfm_times.shape[0], 15, 15)
        )

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare data files required for passive RFM stimuli.

        Parameters
        ----------
        **kwargs
            Accepts but ignores kwargs for API consistency with base class.

        Returns
        -------
        dict
            Data requirements with exact file patterns
        """
        return {
            "exact_files_options": {
                "standard": [
                    "alf/_ibl_passiveRFM.times.npy",
                    "raw_passive_data/_iblrig_RFMapStim.raw.bin"
                ],
            },
        }

    @classmethod
    def download_data(
        cls,
        one: ONE,
        eid: str,
        download_only: bool = True,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Download passive RFM stimulus data.

        NOTE: Queries ONE API to find the last available revision from REVISION_CANDIDATES.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        download_only : bool, default=True
            If True, download but don't load into memory
        logger : logging.Logger, optional
            Logger for progress tracking

        Returns
        -------
        dict
            Download status
        """
        requirements = cls.get_data_requirements()

        # Find the last available revision from candidates
        revision = cls._resolve_revision(one, eid, cls.REVISION_CANDIDATES)

        if logger:
            logger.info(f"Downloading passive RFM stimuli (session {eid}, revision {revision})")

        start_time = time.time()

        # Download both RFM files
        # Note: Must separate collection and filename for ONE API
        for file_path in requirements["exact_files_options"]["standard"]:
            # Extract collection and filename from path
            parts = file_path.split('/')
            collection = parts[0] if len(parts) > 1 else None
            filename = parts[-1]

            one.load_dataset(
                eid,
                filename,
                collection=collection,
                revision=revision,
                download_only=download_only
            )
            if logger:
                logger.info(f"  Downloaded: {file_path}")

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded passive RFM stimuli in {download_time:.2f}s")

        return {
            "success": True,
            "downloaded_objects": [],
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        """
        Add passive RFM stimulus data to the NWB file.

        Creates a TimeSeries containing the visual stimulus data used for
        receptive field mapping.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add data to
        metadata : dict, optional
            Additional metadata (not currently used)
        """
        # Get the passive module
        revision_str = f" Data revision: {self.revision}." if self.revision else ""
        passive_module = get_module(
            nwbfile=nwbfile,
            name="passive_protocol",
            description=(
                "Data from the IBL passive stimulus protocol, presented at the end of each recording session "
                "while the mouse is disengaged from the task. The protocol consists of three phases: "
                "(1) spontaneous activity with no stimuli, "
                "(2) receptive field mapping (RFM) using sparse noise visual stimuli, and "
                "(3) task replay presenting the same Gabor patches and auditory stimuli (valve, tone, noise) "
                f"used during the active behavioral task.{revision_str}"
            )
        )

        # Create the RFM stimulus TimeSeries
        rfm_stim = TimeSeries(
            name="rfm_stim",
            description="receptive field mapping visual stimulus",
            data=self.rfm_data,
            timestamps=self.rfm_times,
            unit="px",
        )

        # Add to module
        passive_module.add(rfm_stim)

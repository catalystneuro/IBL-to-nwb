"""
Interface for passive period intervals (detailed passive phase timing).

This module provides an interface for adding detailed passive protocol interval timing to NWB files,
defining when different phases of the passive period occur (spontaneous activity, RFM, task replay).
The intervals are stored in a custom TimeIntervals table in the processing module.
"""

import logging
from typing import Optional
import time

import pandas as pd
from one.api import ONE
from pynwb import NWBFile, ProcessingModule
from pynwb.epoch import TimeIntervals

from ._base_ibl_interface import BaseIBLDataInterface


class PassiveIntervalsInterface(BaseIBLDataInterface):
    """
    Interface for passive period interval timing data.

    This interface handles the detailed intervals table that defines when passive protocol
    phases occur during a session (spontaneous activity, receptive field mapping, task replay).
    The intervals are stored as a custom TimeIntervals table in processing/passive_protocol.
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
        Initialize the passive intervals interface.

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

        # Load the intervals table - will fail loudly if data missing
        self.passive_intervals_df = one.load_dataset(
            session,
            "_ibl_passivePeriods.intervalsTable.csv",
            collection="alf",
            revision=self.revision
        )

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare data files required for passive period intervals.

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
                    "alf/_ibl_passivePeriods.intervalsTable.csv"
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
        Download passive period intervals data.

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
            logger.info(f"Downloading passive intervals data (session {eid}, revision {revision})")

        start_time = time.time()

        # Download the intervals table
        # Note: Must separate collection and filename for ONE API
        one.load_dataset(
            eid,
            "_ibl_passivePeriods.intervalsTable.csv",
            collection="alf",
            revision=revision,
            download_only=download_only
        )

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded passive intervals in {download_time:.2f}s")

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
        Add passive period intervals to the NWB file.

        Creates a custom TimeIntervals table in processing/passive_protocol with intervals for:
        - Spontaneous activity phase
        - Receptive field mapping (RFM) phase
        - Task replay phase

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add data to
        metadata : dict, optional
            Additional metadata (not currently used)
        """
        df = self.passive_intervals_df

        # Get or create the passive processing module
        if "passive_protocol" not in nwbfile.processing:
            revision_str = f" Data revision: {self.revision}." if self.revision else ""
            passive_module = ProcessingModule(
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
            nwbfile.add_processing_module(passive_module)
        else:
            passive_module = nwbfile.processing["passive_protocol"]

        # Create a custom TimeIntervals table for passive intervals
        revision_str = f" Data revision: {self.revision}." if self.revision else ""
        passive_intervals = TimeIntervals(
            name="passive_intervals",
            description=f"Detailed timing of passive protocol phases (spontaneous activity, RFM, task replay).{revision_str}"
        )

        # Add custom column for protocol name
        passive_intervals.add_column(
            name="protocol_name",
            description="Name of the specific passive protocol phase"
        )

        # Add passive protocol intervals for spontaneousActivity, RFM, and taskReplay
        # NOTE: RFM is temporarily disabled due to data quality issues - waiting for upstream fix
        passive_protocols = ["spontaneousActivity", "taskReplay"]
        # passive_protocols = ["spontaneousActivity", "RFM", "taskReplay"]  # Uncomment when RFM data is fixed

        for protocol in passive_protocols:
            start_time = float(df.loc[df["Unnamed: 0"] == "start", protocol].iloc[0])
            stop_time = float(df.loc[df["Unnamed: 0"] == "stop", protocol].iloc[0])

            # Add interval to the custom table
            passive_intervals.add_interval(
                start_time=start_time,
                stop_time=stop_time,
                protocol_name=protocol
            )

        # Add the intervals table to the passive processing module
        passive_module.add(passive_intervals)

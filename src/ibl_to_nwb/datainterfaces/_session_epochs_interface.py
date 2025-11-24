"""
Interface for session-level epochs (high-level task vs passive phases).

This module provides an interface for adding simple session-level epochs to NWB files,
defining the two main phases: task/experiment phase and passive phase.
"""

import logging
from typing import Optional
import time

from one.api import ONE
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals

from ._base_ibl_interface import BaseIBLDataInterface


class SessionEpochsInterface(BaseIBLDataInterface):
    """
    Interface for session-level epoch timing data.

    This interface handles the high-level epochs table that defines the two main
    phases of an IBL session: the task/experiment phase and the passive phase.
    """

    # Session epochs use BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(
        self,
        one: ONE,
        session: str,
    ):
        """
        Initialize the session epochs interface.

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
        self.revision = self.REVISION

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
        Declare data files required for session epochs.

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
            "one_objects": [],
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
        Download session epochs data.

        NOTE: Uses class-level REVISION attribute automatically.

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

        # Use class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading session epochs data (session {eid}, revision {revision})")

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
            logger.info(f"  Downloaded session epochs data in {download_time:.2f}s")

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
        Add session-level epochs to the NWB file.

        Creates two epochs defining:
        - Task/experiment phase (0 to start of passive period)
        - Passive phase (start to end of passive period)

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add data to
        metadata : dict, optional
            Additional metadata (not currently used)
        """
        df = self.passive_intervals_df

        # Initialize epochs table if it doesn't exist
        if nwbfile.epochs is None:
            nwbfile.epochs = TimeIntervals(name="epochs", description="Experimental epochs")

        # Add custom column to the epochs table
        if "protocol_type" not in nwbfile.epochs.colnames:
            nwbfile.epochs.add_column(
                name="protocol_type",
                description="Type of protocol phase (task or passive)"
            )

        # Get the start and end of the passive protocol
        passive_start = float(df.loc[df["Unnamed: 0"] == "start", "passiveProtocol"].iloc[0])
        passive_end = float(df.loc[df["Unnamed: 0"] == "stop", "passiveProtocol"].iloc[0])

        # Add task/experiment epoch (0 to start of passive protocol)
        nwbfile.add_epoch(
            start_time=0.0,
            stop_time=passive_start,
            protocol_type="task"
        )

        # Add passive protocol epoch
        nwbfile.add_epoch(
            start_time=passive_start,
            stop_time=passive_end,
            protocol_type="passive"
        )

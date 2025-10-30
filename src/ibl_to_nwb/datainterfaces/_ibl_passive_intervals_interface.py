"""
Interface for passive period intervals (epoch timing).

This module provides an interface for adding passive protocol epoch timing to NWB files,
defining when different phases of the passive period occur (spontaneous activity, RFM, task replay).
"""

import logging
from typing import Optional
import time

import pandas as pd
from one.api import ONE
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals

from ._base_ibl_interface import BaseIBLDataInterface


class PassiveIntervalsInterface(BaseIBLDataInterface):
    """
    Interface for passive period interval timing data.

    This interface handles the intervals table that defines when passive protocol
    epochs occur during a session (spontaneous activity, receptive field mapping, task replay).
    """

    # Passive intervals use BWM standard revision
    REVISION: str | None = "2024-05-06"

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
        Download passive period intervals data.

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
        Add passive period epochs to the NWB file.

        Creates epochs defining:
        - Normal experiment phase (0 to start of passive period)
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

        # Initialize epochs table if it doesn't exist
        if nwbfile.epochs is None:
            nwbfile.epochs = TimeIntervals(name="epochs", description="Experimental epochs")

        # Add custom columns to the epochs table
        if "protocol_type" not in nwbfile.epochs.colnames:
            nwbfile.epochs.add_column(
                name="protocol_type",
                description="Type of protocol (normal or passive)"
            )
        if "protocol_name" not in nwbfile.epochs.colnames:
            nwbfile.epochs.add_column(
                name="protocol_name",
                description="Name of the specific protocol"
            )

        # Get the start of the passive protocol (first passive protocol start time)
        passive_start = float(df.loc[df["Unnamed: 0"] == "start", "passiveProtocol"].iloc[0])

        # Add normal experiment epoch (0 to start of passive protocol)
        nwbfile.add_epoch(
            start_time=0.0,
            stop_time=passive_start,
            protocol_type="normal",
            protocol_name="experiment"
        )

        # Add passive protocol epochs for spontaneousActivity, RFM, and taskReplay
        passive_protocols = ["spontaneousActivity", "RFM", "taskReplay"]

        for protocol in passive_protocols:
            start_time = float(df.loc[df["Unnamed: 0"] == "start", protocol].iloc[0])
            stop_time = float(df.loc[df["Unnamed: 0"] == "stop", protocol].iloc[0])

            # Add epoch using the built-in epochs table
            nwbfile.add_epoch(
                start_time=start_time,
                stop_time=stop_time,
                protocol_type="passive",
                protocol_name=protocol
            )

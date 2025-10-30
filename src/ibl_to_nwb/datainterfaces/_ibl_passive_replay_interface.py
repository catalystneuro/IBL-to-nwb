"""
Interface for passive task replay stimuli.

This module provides an interface for adding passive task replay stimulation data to NWB files,
including valve, tone, noise stimuli and gabor patch presentations.
"""

import logging
from typing import Optional
import time

import pandas as pd
from hdmf.common import VectorData
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals

from ._base_ibl_interface import BaseIBLDataInterface

logger = logging.getLogger(__name__)


class PassiveReplayStimInterface(BaseIBLDataInterface):
    """Interface for passive replay stimuli (revision-dependent processed data)."""

    # Passive replay stimuli use BWM standard revision
    REVISION: str | None = "2024-05-06"

    """
    Interface for passive task replay stimulation data.

    This interface handles the replay of task stimuli during passive periods,
    including valve, tone, and noise stimuli as well as gabor patch presentations.
    """

    def __init__(
        self,
        one: ONE,
        session: str,
    ):
        """
        Initialize the passive replay stimulation interface.

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

        # Load replay stimulation data - will fail loudly if data missing
        self.taskreplay_events_df = one.load_dataset(
            session,
            "_ibl_passiveStims.table.csv",
            collection="alf",
            revision=self.revision
        )
        self.gabor_events_df = one.load_dataset(
            session,
            "_ibl_passiveGabor.table.csv",
            collection="alf",
            revision=self.revision
        )

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare data files required for passive replay stimuli.

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
                    "alf/_ibl_passiveStims.table.csv",
                    "alf/_ibl_passiveGabor.table.csv"
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
        Download passive replay stimulation data.

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
            logger.info(f"Downloading passive replay stimuli (session {eid}, revision {revision})")

        start_time = time.time()

        # Download both replay stimuli files
        # Note: Must separate collection and filename for ONE API
        for file_path in requirements["exact_files_options"]["standard"]:
            # Extract filename from path (e.g., "alf/_ibl_passiveStims.table.csv" -> "_ibl_passiveStims.table.csv")
            filename = file_path.split('/')[-1]
            one.load_dataset(eid, filename, collection="alf", revision=revision, download_only=download_only)
            if logger:
                logger.info(f"  Downloaded: {file_path}")

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded passive replay stimuli in {download_time:.2f}s")

        return {
            "success": True,
            "downloaded_objects": [],
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def _exclude_overlapping_stimuli(self, gabor_df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect and exclude temporally overlapping stimulus presentations (data corruption).

        Stimuli cannot be shown simultaneously on the same screen. Overlapping time windows
        indicate corrupted timing data. This method identifies and excludes such entries.

        Parameters
        ----------
        gabor_df : pd.DataFrame
            Gabor events dataframe with columns: start, stop, position, contrast, phase

        Returns
        -------
        pd.DataFrame
            Cleaned dataframe with overlapping stimuli excluded (preserves original order)
        """
        start_times = gabor_df['start'].values
        stop_times = gabor_df['stop'].values
        n_original = len(gabor_df)

        # Detect temporal overlaps
        indices_to_exclude = set()

        for i in range(n_original):
            for j in range(i + 1, n_original):
                # Check if time intervals overlap
                if start_times[i] < stop_times[j] and start_times[j] < stop_times[i]:
                    overlap_duration = min(stop_times[i], stop_times[j]) - max(start_times[i], start_times[j])

                    # Only flag significant overlaps (>1ms to account for floating point precision)
                    if overlap_duration > 0.001:
                        overlap_ms = overlap_duration * 1000

                        # Determine which row to exclude: check which one breaks chronological order
                        # with its surrounding rows (not just the overlapping pair)

                        # Check if row i is in correct order with its neighbors
                        i_before_ok = (i == 0) or (start_times[i-1] < start_times[i])
                        i_after_ok = (i == n_original-1) or (start_times[i] < start_times[i+1])
                        i_sequential = i_before_ok and i_after_ok

                        # Check if row j is in correct order with its neighbors
                        j_before_ok = (j == 0) or (start_times[j-1] < start_times[j])
                        j_after_ok = (j == n_original-1) or (start_times[j] < start_times[j+1])
                        j_sequential = j_before_ok and j_after_ok

                        # Exclude the row that's NOT in sequence with its neighbors
                        if i_sequential and not j_sequential:
                            excluded_index = j
                            kept_index = i
                        elif j_sequential and not i_sequential:
                            excluded_index = i
                            kept_index = j
                        else:
                            # Both or neither in sequence - exclude the earlier row in file
                            excluded_index = i
                            kept_index = j

                        indices_to_exclude.add(excluded_index)

                        logger.warning(
                            f"Gabor stimulus overlap detected: excluding row {excluded_index} "
                            f"({overlap_ms:.1f}ms overlap with row {kept_index}). "
                            f"Stimulus timings - excluded: {start_times[excluded_index]:.3f}-{stop_times[excluded_index]:.3f}s, "
                            f"kept: {start_times[kept_index]:.3f}-{stop_times[kept_index]:.3f}s"
                        )

        # Exclude identified rows
        if indices_to_exclude:
            mask = ~gabor_df.index.isin(indices_to_exclude)
            gabor_cleaned = gabor_df[mask].copy()
            n_excluded = len(indices_to_exclude)
            n_retained = len(gabor_cleaned)

            logger.warning(
                f"Gabor data cleaning: excluded {n_excluded} overlapping stimulus entries "
                f"(rows {sorted(indices_to_exclude)}). Retained {n_retained}/{n_original} stimuli."
            )
        else:
            gabor_cleaned = gabor_df.copy()
            logger.info(f"Gabor data validation: all {n_original} stimuli passed temporal overlap check")

        return gabor_cleaned

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        """
        Add passive replay stimulation data to the NWB file.

        Creates TimeIntervals tables for:
        - Task replay events (valve, tone, noise stimuli)
        - Gabor patch presentations

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add data to
        metadata : dict, optional
            Additional metadata (not currently used)
        """
        # Get the passive module
        passive_module = get_module(
            nwbfile=nwbfile,
            name="passive",
            description="passive stimulation data."
        )

        # Add passive stimulation intervals as a TimeIntervals table
        passive_stims = TimeIntervals(
            name="passive_task_replay",
            description="Passive stimulation events including valve, tone, and noise stimuli.",
        )

        # Add custom column for stimulation type
        passive_stims.add_column(
            name="stim_type",
            description="Type of stimulation (valve, tone, or noise)"
        )

        # Collect all stimulation events with their start times for sorting
        all_stim_events = []

        # Add valve stimulation events
        for _, row in self.taskreplay_events_df.iterrows():
            all_stim_events.append({
                "start_time": row["valveOn"],
                "stop_time": row["valveOff"],
                "stim_type": "valve"
            })

        # Add tone stimulation events
        for _, row in self.taskreplay_events_df.iterrows():
            all_stim_events.append({
                "start_time": row["toneOn"],
                "stop_time": row["toneOff"],
                "stim_type": "tone"
            })

        # Add noise stimulation events
        for _, row in self.taskreplay_events_df.iterrows():
            all_stim_events.append({
                "start_time": row["noiseOn"],
                "stop_time": row["noiseOff"],
                "stim_type": "noise"
            })

        # Sort events by start time and add sorted events to the TimeIntervals table
        all_stim_events.sort(key=lambda x: x["start_time"])
        for event in all_stim_events:
            passive_stims.add_row(
                start_time=event["start_time"],
                stop_time=event["stop_time"],
                stim_type=event["stim_type"]
            )

        # Add to the module
        passive_module.add(passive_stims)

        # Gabor patch data - detect and exclude temporally overlapping stimuli (data corruption)
        gabor_cleaned = self._exclude_overlapping_stimuli(self.gabor_events_df)

        columns = [
            VectorData(
                name="start_time",
                description="The beginning of the stimulus.",
                data=gabor_cleaned["start"].values,
            ),
            VectorData(
                name="stop_time",
                description="The end of the stimulus.",
                data=gabor_cleaned["stop"].values,
            ),
        ]

        col_names = ["position", "contrast", "phase"]
        meta = dict(
            position="gabor patch position",
            contrast="gabor patch contrast",
            phase="gabor patch phase",
        )

        for name in col_names:
            columns.append(
                VectorData(
                    name=name,
                    description=meta[name],
                    data=gabor_cleaned[name].values,
                )
            )

        gabor_events = TimeIntervals(
            name="gabor_table",
            description="Gabor patch presentations table.",
            columns=columns,
        )

        passive_module.add(gabor_events)

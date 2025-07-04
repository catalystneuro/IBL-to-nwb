"""
Data interfaces for handling experimental epochs and passive stimulation intervals.

This module provides interfaces for adding experimental timing information to NWB files,
including epochs that define experimental phases and passive stimulation events.
"""

from typing import Optional
import pandas as pd
from neuroconv.basedatainterface import BaseDataInterface
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals
from one.api import ONE
import numpy as np
from pathlib import Path
from neuroconv.utils import load_dict_from_file
from pynwb import TimeSeries
from neuroconv.tools.nwb_helpers import get_module
from hdmf.common import VectorData


class PassivePeriodDataInterface(BaseDataInterface):
    def __init__(
        self,
        one: ONE,
        eid: str,
        revision: Optional[str] = None,
    ):
        if revision is None:  # if no revision is specified, use the latest
            revision = one.list_revisions(eid)[-1]

        # passive epochs
        self.passive_intervals_df = one.load_dataset(eid, "alf/_ibl_passivePeriods.intervalsTable.csv")

        # replay
        self.taskreplay_events_df = one.load_dataset(eid, "alf/_ibl_passiveStims.table.csv")

        # RFM
        self.gabor_events_df = one.load_dataset(eid, "alf/_ibl_passiveGabor.table.csv")
        self.rfm_times = one.load_dataset(eid, "alf/_ibl_passiveRFM.times.npy")
        path = one.load_dataset(eid, "raw_passive_data/_iblrig_RFMapStim.raw.bin")
        self.rfm_data = np.fromfile(path, dtype=np.uint8).reshape((self.rfm_times.shape[0], 15, 15))

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        PassiveEpochsInterface(self.passive_intervals_df).add_to_nwbfile(nwbfile, metadata=metadata)
        TaskReplayInterface(self.passive_intervals_df, self.taskreplay_events_df).add_to_nwbfile(nwbfile, metadata=metadata)
        GaborRFMInterface(self.gabor_events_df, self.rfm_times, self.rfm_data).add_to_nwbfile(nwbfile, metadata=metadata)


class PassiveEpochsInterface(BaseDataInterface):
    """
    Interface for adding experimental epochs to NWBFile.

    This interface creates epochs from interval data loaded from IntervalTable.csv,
    including one normal experiment epoch and three passive protocol epochs.
    """

    def __init__(self, passive_intervals_df: pd.DataFrame):
        """
        Initialize the PassiveEpochsInterface.

        Parameters
        ----------
        passive_intervals_df : pd.DataFrame
            DataFrame containing interval data with columns for different protocols
            (passiveProtocol, spontaneousActivity, RFM, taskReplay) and rows for
            'start' and 'stop' times.
        """
        self.passive_intervals_df = passive_intervals_df

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        """
        Add experimental epochs to the NWBFile.

        Creates a total of 4 epochs:
        - 1 normal experiment epoch (0 to start of passive protocol)
        - 3 passive protocol epochs (spontaneousActivity, RFM, taskReplay)

        Each epoch includes custom columns:
        - protocol_type: "normal" or "passive"
        - protocol_name: specific protocol name

        Parameters
        ----------
        nwbfile : NWBFile
            The NWBFile to add epochs to.
        metadata : dict, optional
            Additional metadata. If None, uses self.get_metadata().
        """
        if metadata is None:
            metadata = self.get_metadata()
        df = self.passive_intervals_df

        # Initialize epochs table if it doesn't exist and add custom columns
        if nwbfile.epochs is None:
            from pynwb.epoch import TimeIntervals

            nwbfile.epochs = TimeIntervals(name="epochs", description="Experimental epochs")

        # Add custom columns to the epochs table
        nwbfile.epochs.add_column(name="protocol_type", description="Type of protocol (normal or passive)")
        nwbfile.epochs.add_column(name="protocol_name", description="Name of the specific protocol")

        # Get the start of the passive protocol (first passive protocol start time)
        passive_start = float(df.loc[df["Unnamed: 0"] == "start", "passiveProtocol"].iloc[0])

        # Add normal experiment epoch (0 to start of passive protocol)
        nwbfile.add_epoch(start_time=0.0, stop_time=passive_start, protocol_type="normal", protocol_name="experiment")

        # Add passive protocol epochs for spontaneousActivity, RFM, and taskReplay
        passive_protocols = ["spontaneousActivity", "RFM", "taskReplay"]

        for protocol in passive_protocols:
            start_time = float(df.loc[df["Unnamed: 0"] == "start", protocol].iloc[0])
            stop_time = float(df.loc[df["Unnamed: 0"] == "stop", protocol].iloc[0])

            # Add epoch using the built-in epochs table
            nwbfile.add_epoch(start_time=start_time, stop_time=stop_time, protocol_type="passive", protocol_name=protocol)


class TaskReplayInterface(BaseDataInterface):
    """
    Interface for adding passive stimulation intervals to NWBFile.

    This interface creates a TimeIntervals table containing passive stimulation
    events (valve, tone, and noise) sorted by start time.
    """

    def __init__(self, passive_intervals_df: pd.DataFrame, taskreplay_events_df: pd.DataFrame):
        """
        Initialize the TaskReplayInterface.

        Parameters
        ----------
        passive_intervals_df : pd.DataFrame
            DataFrame containing interval data (not used in this interface but kept
            for consistency with the interface pattern).
        taskreplay_events_df : pd.DataFrame
            DataFrame containing passive stimulation data with columns:
            - valveOn, valveOff: valve stimulation start/stop times
            - toneOn, toneOff: tone stimulation start/stop times
            - noiseOn, noiseOff: noise stimulation start/stop times
        """
        self.passive_intervals_df = passive_intervals_df
        self.taskreplay_events_df = taskreplay_events_df

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        """
        Add passive stimulation intervals to the NWBFile.

        Creates a TimeIntervals table named "TaskReplayPassiveStimulusIntervals"
        containing all passive stimulation events sorted by start time.

        The table includes:
        - start_time, stop_time: timing of each stimulation event
        - stim_type: type of stimulation ("valve", "tone", or "noise")

        Parameters
        ----------
        nwbfile : NWBFile
            The NWBFile to add intervals to.
        metadata : dict, optional
            Additional metadata. If None, uses self.get_metadata().
        """
        if metadata is None:
            metadata = self.get_metadata()
        stims_df = self.taskreplay_events_df

        # Add passive stimulation intervals as a TimeIntervals table
        passive_stims = TimeIntervals(
            name="TaskReplayPassiveStimulusIntervals",
            description="Passive stimulation events including valve, tone, and noise stimuli.",
        )

        # Add custom columns for stimulation type
        passive_stims.add_column(name="stim_type", description="Type of stimulation (valve, tone, or noise)")

        # Collect all stimulation events with their start times for sorting
        all_stim_events = []

        # Add valve stimulation events
        for _, row in stims_df.iterrows():
            all_stim_events.append({"start_time": row["valveOn"], "stop_time": row["valveOff"], "stim_type": "valve"})

        # Add tone stimulation events
        for _, row in stims_df.iterrows():
            all_stim_events.append({"start_time": row["toneOn"], "stop_time": row["toneOff"], "stim_type": "tone"})

        # Add noise stimulation events
        for _, row in stims_df.iterrows():
            all_stim_events.append({"start_time": row["noiseOn"], "stop_time": row["noiseOff"], "stim_type": "noise"})

        # Sort events by start time
        all_stim_events.sort(key=lambda x: x["start_time"])

        # Add sorted events to the TimeIntervals table
        for event in all_stim_events:
            passive_stims.add_row(start_time=event["start_time"], stop_time=event["stop_time"], stim_type=event["stim_type"])

        # Add the TimeIntervals table to the NWB file # TODO testme
        # nwbfile.add_time_intervals(passive_stims)

        # or - add it to the module
        passive_module = get_module(nwbfile=nwbfile, name="passive", description="passive stimulation data.")
        passive_module.add(passive_stims)


class GaborRFMInterface(BaseDataInterface):
    def __init__(self, gabor_events_df, rfm_times, rfm_data):
        self.gabor_events_df = gabor_events_df
        self.rfm_times = rfm_times
        self.rfm_data = rfm_data

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        passive_module = get_module(nwbfile=nwbfile, name="passive", description="passive stimulation data.")

        # the stim
        gabor_data = TimeSeries(
            name="",
            description="",
            data=self.rfm_data,
            timestamps=self.rfm_times,
            unit="px",
        )

        passive_module.add(gabor_data)

        columns = [
            VectorData(
                name="start_time",
                description="The beginning of the stimulus.",
                data=self.gabor_events_df["start"].values,
            ),
            VectorData(
                name="stop_time",
                description="The end of the stimulus.",
                data=self.gabor_events_df["stop"].values,
            ),
        ]
        columns = ["position", "contrast", "phase"]
        meta = dict(position="", conrast="", phase="")

        for key in columns:
            columns.append(
                VectorData(
                    name=key,
                    description=meta[key],
                    data=self.gabor_events_df[key].values,
                )
            )

        gabor = TimeIntervals(
            name="trials",
            description="Trial intervals and conditions.",
            columns=columns,
        )

        # TODO try and verify
        # nwbfile.add_time_intervals(gabor)
        passive_module.add(gabor)

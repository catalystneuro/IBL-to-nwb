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
        session: str,
        revision: Optional[str] = None,
    ):
        if revision is None:  # if no revision is specified, use the latest
            revision = one.list_revisions(session)[-1]

        datasets = one.list_datasets(session)
        self.present_datasets = dict(
            has_passive = True if "alf/_ibl_passivePeriods.intervalsTable.csv" in datasets else False,
            has_replay = True if "alf/_ibl_passiveGabor.table.csv" in datasets else False,
            has_rfm = True if "alf/_ibl_passiveRFM.times.npy" in datasets else False,
        )
        
        # passive epochs
        if self.present_datasets['has_passive']:
            self.passive_intervals_df = one.load_dataset(session, "alf/_ibl_passivePeriods.intervalsTable.csv")

        # replay
        if self.present_datasets['has_replay']:
            self.taskreplay_events_df = one.load_dataset(session, "alf/_ibl_passiveStims.table.csv")

        # RFM
        if self.present_datasets['has_rfm']:
            self.gabor_events_df = one.load_dataset(session, "alf/_ibl_passiveGabor.table.csv")
            self.rfm_times = one.load_dataset(session, "alf/_ibl_passiveRFM.times.npy")
            path = one.load_dataset(session, "raw_passive_data/_iblrig_RFMapStim.raw.bin")
            self.rfm_data = np.fromfile(path, dtype=np.uint8).reshape((self.rfm_times.shape[0], 15, 15))

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        if self.present_datasets['has_passive']:
            PassiveEpochsInterface(self.passive_intervals_df).add_to_nwbfile(nwbfile, metadata=metadata)
        if self.present_datasets['has_replay']:
            TaskReplayInterface(self.passive_intervals_df, self.taskreplay_events_df).add_to_nwbfile(nwbfile, metadata=metadata)
        if self.present_datasets['has_rfm']:
            ReceptiveFieldMappingInterface(self.gabor_events_df, self.rfm_times, self.rfm_data).add_to_nwbfile(nwbfile, metadata=metadata)


class PassiveEpochsInterface(BaseDataInterface):

    def __init__(self, passive_intervals_df: pd.DataFrame):
        self.passive_intervals_df = passive_intervals_df

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):

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
    def __init__(self, taskreplay_events_df: pd.DataFrame, gabor_events_df: pd.DataFrame):
        self.taskreplay_events_df = taskreplay_events_df
        self.gabor_events_df = gabor_events_df

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        if metadata is None:
            metadata = self.get_metadata()

        # get the module
        passive_module = get_module(nwbfile=nwbfile, name="passive", description="passive stimulation data.")

        # Add passive stimulation intervals as a TimeIntervals table
        passive_stims = TimeIntervals(
            name="passive_task_replay",
            description="Passive stimulation events including valve, tone, and noise stimuli.",
        )

        # Add custom columns for stimulation type
        passive_stims.add_column(name="stim_type", description="Type of stimulation (valve, tone, or noise)")

        # Collect all stimulation events with their start times for sorting
        all_stim_events = []

        # Add valve stimulation events
        for _, row in self.taskreplay_events_df.iterrows():
            all_stim_events.append({"start_time": row["valveOn"], "stop_time": row["valveOff"], "stim_type": "valve"})

        # Add tone stimulation events
        for _, row in self.taskreplay_events_df.iterrows():
            all_stim_events.append({"start_time": row["toneOn"], "stop_time": row["toneOff"], "stim_type": "tone"})

        # Add noise stimulation events
        for _, row in self.taskreplay_events_df.iterrows():
            all_stim_events.append({"start_time": row["noiseOn"], "stop_time": row["noiseOff"], "stim_type": "noise"})

        # Sort events by start time and add sorted events to the TimeIntervals table
        all_stim_events.sort(key=lambda x: x["start_time"])
        for event in all_stim_events:
            passive_stims.add_row(start_time=event["start_time"], stop_time=event["stop_time"], stim_type=event["stim_type"])

        # add it to the module
        passive_module.add(passive_stims)

        # gabor patch data
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
        col_names = ["position", "contrast", "phase"]
        meta = dict(position="gabor patch position", contrast="gabor patch contrast", phase="gabor patch phase",)

        for name in col_names:
            columns.append(
                VectorData(
                    name=name,
                    description=meta[name],
                    data=self.gabor_events_df[name].values,
                )
            )

        gabor_events = TimeIntervals(
            name="gabor_table",
            description="Gabor patch presentations table.",
            columns=columns,
        )

        passive_module.add(gabor_events)


class ReceptiveFieldMappingInterface(BaseDataInterface):
    def __init__(self, rfm_times, rfm_data):

        self.rfm_times = rfm_times
        self.rfm_data = rfm_data

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        if metadata is None:
            metadata = self.get_metadata()
        # get module
        passive_module = get_module(nwbfile=nwbfile, name="passive", description="passive stimulation data.")

        # the stim data
        rfm_stim = TimeSeries(
            name="rfm_stim",
            description="receptive field mapping visual stimulus",
            data=self.rfm_data,
            timestamps=self.rfm_times,
            unit="px",
        )
        
        # add to module
        passive_module.add(rfm_stim)

        

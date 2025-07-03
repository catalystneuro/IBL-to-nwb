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


class EpochsInterface(BaseDataInterface):
    """
    Interface for adding experimental epochs to NWBFile.
    
    This interface creates epochs from interval data loaded from IntervalTable.csv,
    including one normal experiment epoch and three passive protocol epochs.
    """

    def __init__(self, intervals_dataframe: pd.DataFrame):
        """
        Initialize the EpochsInterface.
        
        Parameters
        ----------
        intervals_dataframe : pd.DataFrame
            DataFrame containing interval data with columns for different protocols
            (passiveProtocol, spontaneousActivity, RFM, taskReplay) and rows for
            'start' and 'stop' times.
        """
        self.intervals_dataframe = intervals_dataframe

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
        df = self.intervals_dataframe
        
        # Initialize epochs table if it doesn't exist and add custom columns
        if nwbfile.epochs is None:
            from pynwb.epoch import TimeIntervals
            nwbfile.epochs = TimeIntervals(name="epochs", description="Experimental epochs")
        
        # Add custom columns to the epochs table
        nwbfile.epochs.add_column(name="protocol_type", description="Type of protocol (normal or passive)")
        nwbfile.epochs.add_column(name="protocol_name", description="Name of the specific protocol")
        
        # Get the start of the passive protocol (first passive protocol start time)
        passive_start = float(df.loc[df['Unnamed: 0'] == 'start', 'passiveProtocol'].iloc[0])
        
        # Add normal experiment epoch (0 to start of passive protocol)
        nwbfile.add_epoch(
            start_time=0.0,
            stop_time=passive_start,
            protocol_type="normal",
            protocol_name="experiment"
        )
        
        # Add passive protocol epochs for spontaneousActivity, RFM, and taskReplay
        passive_protocols = ['spontaneousActivity', 'RFM', 'taskReplay']
        
        for protocol in passive_protocols:
            start_time = float(df.loc[df['Unnamed: 0'] == 'start', protocol].iloc[0])
            stop_time = float(df.loc[df['Unnamed: 0'] == 'stop', protocol].iloc[0])
            
            # Add epoch using the built-in epochs table
            nwbfile.add_epoch(
                start_time=start_time,
                stop_time=stop_time,
                protocol_type="passive",
                protocol_name=protocol
            )


class PassiveStimInterface(BaseDataInterface):
    """
    Interface for adding passive stimulation intervals to NWBFile.
    
    This interface creates a TimeIntervals table containing passive stimulation
    events (valve, tone, and noise) sorted by start time.
    """

    def __init__(self, intervals_dataframe: pd.DataFrame, passive_stims_dataframe: pd.DataFrame):
        """
        Initialize the PassiveStimInterface.
        
        Parameters
        ----------
        intervals_dataframe : pd.DataFrame
            DataFrame containing interval data (not used in this interface but kept
            for consistency with the interface pattern).
        passive_stims_dataframe : pd.DataFrame
            DataFrame containing passive stimulation data with columns:
            - valveOn, valveOff: valve stimulation start/stop times
            - toneOn, toneOff: tone stimulation start/stop times  
            - noiseOn, noiseOff: noise stimulation start/stop times
        """
        self.intervals_dataframe = intervals_dataframe
        self.passive_stims_dataframe = passive_stims_dataframe

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
        stims_df = self.passive_stims_dataframe
        
        # Add passive stimulation intervals as a TimeIntervals table
        passive_stims = TimeIntervals(
            name="TaskReplayPassiveStimulusIntervals",
            description="Passive stimulation events including valve, tone, and noise stimuli."
        )
        
        # Add custom columns for stimulation type
        passive_stims.add_column(name="stim_type", description="Type of stimulation (valve, tone, or noise)")
        
        # Collect all stimulation events with their start times for sorting
        all_stim_events = []
        
        # Add valve stimulation events
        for _, row in stims_df.iterrows():
            all_stim_events.append({
                'start_time': row['valveOn'],
                'stop_time': row['valveOff'],
                'stim_type': 'valve'
            })
        
        # Add tone stimulation events
        for _, row in stims_df.iterrows():
            all_stim_events.append({
                'start_time': row['toneOn'],
                'stop_time': row['toneOff'],
                'stim_type': 'tone'
            })
        
        # Add noise stimulation events
        for _, row in stims_df.iterrows():
            all_stim_events.append({
                'start_time': row['noiseOn'],
                'stop_time': row['noiseOff'],
                'stim_type': 'noise'
            })
        
        # Sort events by start time
        all_stim_events.sort(key=lambda x: x['start_time'])
        
        # Add sorted events to the TimeIntervals table
        for event in all_stim_events:
            passive_stims.add_row(
                start_time=event['start_time'],
                stop_time=event['stop_time'],
                stim_type=event['stim_type']
            )
        
        # Add the TimeIntervals table to the NWB file
        nwbfile.add_time_intervals(passive_stims)
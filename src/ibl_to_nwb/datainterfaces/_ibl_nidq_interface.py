"""IBL-specific NIDQ interface with wiring.json support."""

import logging
from pathlib import Path

from neuroconv.datainterfaces import SpikeGLXNIDQInterface
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile

from ._base_ibl_interface import BaseIBLDataInterface
from ..utils.nidq_wiring import (
    load_nidq_wiring,
    create_channel_name_mapping,
    apply_channel_name_mapping,
    enrich_nidq_metadata_with_wiring,
)


_logger = logging.getLogger(__name__)


class IblNIDQInterface(SpikeGLXNIDQInterface, BaseIBLDataInterface):
    """
    IBL-specific NIDQ interface that adds wiring.json support.

    Extends NeuroConv's SpikeGLXNIDQInterface to:
    1. Load wiring configuration from ONE
    2. Map technical channel IDs (XD0, XA0) to meaningful device names (left_camera, bpod)
    3. Enrich metadata with wiring documentation
    4. Use BWM standard revision for data loading

    The wiring.json file documents how behavioral devices are connected to NIDQ
    channels and varies by rig, making it essential session-specific metadata.
    """

    # Use BWM standard revision
    REVISION: str | None = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Get data requirements for NIDQ interface.

        Returns
        -------
        dict
            Dictionary with required NIDQ files (excluding optional wiring.json)
        """
        return {
            "one_objects": [],
            "exact_files_options": {
                "standard": [
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.cbin",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.meta",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.ch",
                ],
            },
        }

    @classmethod
    def download_data(cls, one, eid, download_only=True, logger=None, **kwargs):
        """
        Download NIDQ files for this session.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        download_only : bool, default=True
            If True, only download without loading into memory
        logger : logging.Logger, optional
            Logger instance
        **kwargs
            Additional keyword arguments

        Returns
        -------
        dict
            Download status with keys: success, downloaded_files, already_cached, etc.
        """
        requirements = cls.get_data_requirements()

        if logger:
            logger.info(f"Downloading NIDQ files for session {eid}")

        downloaded_files = []
        for nidq_file in requirements["exact_files_options"]["standard"]:
            try:
                one.load_dataset(eid, nidq_file, download_only=download_only)
                downloaded_files.append(nidq_file)
                if logger:
                    logger.info(f"  Downloaded {nidq_file}")
            except Exception as e:
                if logger:
                    logger.error(f"  Failed to download {nidq_file}: {e}")
                raise

        # Try to download wiring.json (optional - warn if missing but don't fail)
        try:
            wiring_file = "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.wiring.json"
            one.load_dataset(eid, wiring_file, download_only=download_only)
            downloaded_files.append(wiring_file)
            if logger:
                logger.info(f"  Downloaded {wiring_file}")
        except Exception as e:
            if logger:
                logger.warning(f"  Could not download wiring.json (optional): {e}")

        return {
            "success": True,
            "downloaded_objects": [],
            "downloaded_files": downloaded_files,
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def __init__(
        self,
        folder_path: DirectoryPath,
        one: ONE,
        eid: str,
        verbose: bool = False,
        es_key: str = "ElectricalSeriesNIDQ",
    ):
        """
        Initialize IBL NIDQ interface with wiring support.

        Parameters
        ----------
        folder_path : DirectoryPath
            Path to folder containing decompressed .nidq.bin file
        one : ONE
            ONE API instance for loading wiring configuration
        eid : str
            Session ID (used to load wiring.json)
        verbose : bool, default=False
            Whether to output verbose text
        es_key : str, default="ElectricalSeriesNIDQ"
            Key for the NIDQ ElectricalSeries in metadata
        """
        # Initialize parent interface
        super().__init__(
            folder_path=folder_path,
            verbose=verbose,
            es_key=es_key,
        )

        self.one = one
        self.eid = eid
        self.revision = self.REVISION

        # Load wiring configuration
        self.wiring = load_nidq_wiring(one=one, eid=eid)

        # Create channel name mapping
        self.channel_mapping = create_channel_name_mapping(self.wiring)

        if self.wiring:
            _logger.info(f"Loaded NIDQ wiring configuration for session {eid}")
            _logger.debug(f"Channel mapping: {self.channel_mapping}")
        else:
            _logger.warning(
                f"No wiring configuration found for session {eid}. "
                "Channel names will use default SpikeGLX identifiers."
            )

    def get_metadata(self):
        """
        Get metadata with wiring information included.

        Returns
        -------
        dict
            Metadata dictionary enriched with wiring configuration
        """
        metadata = super().get_metadata()

        # Add wiring information to metadata
        metadata = enrich_nidq_metadata_with_wiring(metadata, self.wiring)

        # Update TimeSeries description with meaningful channel names
        if "TimeSeries" in metadata and "TimeSeriesNIDQ" in metadata["TimeSeries"]:
            if self.has_analog_channels and self.channel_mapping:
                # Get analog channel IDs and apply mapping
                analog_channel_ids = self.analog_channel_ids
                mapped_names = apply_channel_name_mapping(analog_channel_ids, self.channel_mapping)

                # Update description with meaningful names
                original_desc = metadata["TimeSeries"]["TimeSeriesNIDQ"].get("description", "")
                mapped_desc = f"Analog data from the NIDQ board. Channels are {mapped_names} in that order."

                # Include technical IDs for reference
                mapped_desc += f" (Technical IDs: {analog_channel_ids})"

                metadata["TimeSeries"]["TimeSeriesNIDQ"]["description"] = mapped_desc

        return metadata

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: dict | None = None,
        stub_test: bool = False,
        iterator_type: str | None = "v2",
        iterator_opts: dict | None = None,
        always_write_timestamps: bool = False,
    ):
        """
        Add NIDQ data to NWB file with wiring-based channel names.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add data to
        metadata : dict, optional
            Metadata dictionary (will be enriched with wiring info)
        stub_test : bool, default=False
            If True, only write a small amount of data for testing
        iterator_type : str, optional, default="v2"
            Type of iterator for data streaming
        iterator_opts : dict, optional
            Additional iterator options
        always_write_timestamps : bool, default=False
            If True, always write timestamps instead of using sampling rate
        """
        # Get metadata with wiring information
        if metadata is None:
            metadata = self.get_metadata()

        # Enrich metadata with digital event descriptions based on wiring
        if self.has_digital_channels and self.channel_mapping:
            # The parent class creates digital events with keys like "EventsNIDQDigitalChannelXD0"
            # We can't rename them, but we can enrich their descriptions via metadata
            # However, the parent class doesn't use metadata for event descriptions
            # So we'll need to modify them after creation (see _rename_digital_events_with_wiring)
            pass

        # Stub the recording if in test mode (same as parent)
        from neuroconv.tools.spikeinterface import _stub_recording

        recording = self.recording_extractor
        if stub_test:
            recording = _stub_recording(recording=self.recording_extractor)

        # Add devices
        device_metadata = metadata.get("Devices", [])
        for device in device_metadata:
            if device["name"] not in nwbfile.devices:
                nwbfile.create_device(**device)

        # Add analog channels with stubbed recording
        if self.has_analog_channels:
            self._add_analog_channels(
                nwbfile=nwbfile,
                recording=recording,
                iterator_type=iterator_type,
                iterator_opts=iterator_opts,
                always_write_timestamps=always_write_timestamps,
                metadata=metadata,
            )

        # Add digital channels with our custom naming
        if self.has_digital_channels:
            self._add_digital_channels(nwbfile=nwbfile)

    def _add_analog_channels(
        self,
        nwbfile: NWBFile,
        recording,
        iterator_type: str | None,
        iterator_opts: dict | None,
        always_write_timestamps: bool,
        metadata: dict | None = None,
    ):
        """
        Add analog channels as separate TimeSeries with semantic names based on wiring.

        Creates one TimeSeries per analog channel with IBL-specific device names.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add the analog channels to
        recording : BaseRecording
            The recording extractor containing the analog channels
        iterator_type : str | None
            Type of iterator to use for data streaming
        iterator_opts : dict | None
            Additional options for the iterator
        always_write_timestamps : bool
            If True, always writes timestamps instead of using sampling rate
        metadata : dict | None, default: None
            Metadata dictionary with TimeSeries information
        """
        from neuroconv.tools.spikeinterface import add_recording_as_time_series_to_nwbfile

        analog_recorder = recording.select_channels(channel_ids=self.analog_channel_ids)

        # Create default metadata if not provided
        if metadata is None:
            metadata = self.get_metadata()

        # Map from technical channel IDs to semantic names and descriptions
        # Based on IBL NIDQ standard wiring: AI0=Bpod, AI1=laser, AI2=laser_ttl
        analog_channel_info = {
            "nidq#XA0": {
                "name": "TimeSeriesBpod",
                "description": (
                    "Analog signal from Bpod behavioral control system. "
                    "This continuous voltage signal encodes behavioral state machine events and timestamps "
                    "from the Bpod system, which controls stimulus presentation and reward delivery during tasks. "
                    "The analog encoding allows precise temporal alignment between Bpod events and neural recordings."
                ),
            },
            "nidq#XA1": {
                "name": "TimeSeriesLaser",
                "description": (
                    "Analog signal from laser power modulation. "
                    "This voltage signal represents the commanded laser power level for optogenetic stimulation. "
                    "The continuous signal enables precise characterization of laser intensity dynamics during experiments."
                ),
            },
            "nidq#XA2": {
                "name": "TimeSeriesLaserTTL",
                "description": (
                    "Analog signal from laser TTL gating. "
                    "This voltage signal indicates when the laser is enabled (high) or disabled (low). "
                    "Combined with the laser power signal (AI1), this provides complete characterization "
                    "of optogenetic stimulation timing and intensity."
                ),
            },
        }

        # Add each analog channel as a separate TimeSeries
        for channel_id in self.analog_channel_ids:
            # Get channel info or use defaults
            if channel_id in analog_channel_info:
                channel_info = analog_channel_info[channel_id]
                time_series_name = channel_info["name"]
                description = channel_info["description"]
            else:
                # Fallback for unexpected channels
                channel_name = channel_id.split("#")[-1]
                time_series_name = f"TimeSeries{channel_name}"
                description = f"Analog signal from NIDQ channel {channel_name}."

            # Select only this channel
            single_channel_recording = analog_recorder.select_channels(channel_ids=[channel_id])

            # Prepare metadata for this TimeSeries
            if "TimeSeries" not in metadata:
                metadata["TimeSeries"] = {}
            metadata["TimeSeries"][time_series_name] = dict(description=description)

            # Add as TimeSeries to acquisition
            add_recording_as_time_series_to_nwbfile(
                recording=single_channel_recording,
                nwbfile=nwbfile,
                metadata=metadata,
                iterator_type=iterator_type,
                iterator_opts=iterator_opts,
                always_write_timestamps=always_write_timestamps,
                time_series_name=time_series_name,
            )

    def _add_digital_channels(self, nwbfile: NWBFile):
        """
        Override parent method to add digital channels with IBL-specific device names from wiring.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add the digital channels to
        """
        from ndx_events import LabeledEvents
        import numpy as np

        # Left camera (body camera, left side) - P0.0
        channel_id = "nidq#XD0"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]

        # Create semantic labels
        semantic_labels = np.array(["exposure_end", "frame_start"])
        label_mapping = {"XD0 OFF": 0, "XD0 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]

        labeled_events = LabeledEvents(
            name="EventsLeftCamera",
            description=(
                "Video frame acquisition times for the left-side camera (body camera). "
                "Labels: 'exposure_end' = Camera exposure end or frame readout complete; "
                "'frame_start' = Camera frame acquisition start (frame timestamp). "
                "Each ON event marks when a video frame was captured by the camera, "
                "enabling temporal alignment of behavior videos with neural and task data."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

        # Right camera (body camera, right side) - P0.1
        channel_id = "nidq#XD1"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]
        semantic_labels = np.array(["exposure_end", "frame_start"])
        label_mapping = {"XD1 OFF": 0, "XD1 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]
        labeled_events = LabeledEvents(
            name="EventsRightCamera",
            description=(
                "Video frame acquisition times for the right-side camera (body camera). "
                "Labels: 'exposure_end' = Camera exposure end or frame readout complete; "
                "'frame_start' = Camera frame acquisition start (frame timestamp). "
                "Each ON event marks when a video frame was captured by the camera, "
                "enabling temporal alignment of behavior videos with neural and task data."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

        # Body camera - P0.2
        channel_id = "nidq#XD2"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]
        semantic_labels = np.array(["exposure_end", "frame_start"])
        label_mapping = {"XD2 OFF": 0, "XD2 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]
        labeled_events = LabeledEvents(
            name="EventsBodyCamera",
            description=(
                "Video frame acquisition times for the body camera. "
                "Labels: 'exposure_end' = Camera exposure end or frame readout complete; "
                "'frame_start' = Camera frame acquisition start (frame timestamp). "
                "Each ON event marks when a video frame was captured by the camera, "
                "enabling temporal alignment of behavior videos with neural and task data."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

        # ImecSync (multi-probe synchronization) - P0.3
        channel_id = "nidq#XD3"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]
        semantic_labels = np.array(["sync_low", "sync_high"])
        label_mapping = {"XD3 OFF": 0, "XD3 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]
        labeled_events = LabeledEvents(
            name="EventsImecSync",
            description=(
                "Multi-probe synchronization signal (1 Hz square wave). "
                "Labels: 'sync_low' = Sync signal low phase (0.5s duration at 1 Hz); "
                "'sync_high' = Sync signal high phase (0.5s duration at 1 Hz). "
                "This signal is simultaneously recorded on NIDQ (P0.3) and all Neuropixels probes (bit 6), "
                "enabling precise temporal alignment across multiple recording devices. "
                "The 1 Hz square wave provides regular alignment points for drift correction."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

        # Frame2TTL (visual stimulus timing via photodiode) - P0.4
        channel_id = "nidq#XD4"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]
        semantic_labels = np.array(["screen_dark", "screen_bright"])
        label_mapping = {"XD4 OFF": 0, "XD4 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]
        labeled_events = LabeledEvents(
            name="EventsFrame2ttl",
            description=(
                "Monitor refresh events detected by photodiode for visual stimulus timing. "
                "Labels: 'screen_dark' = Screen transitioned to dark (photodiode detected low luminance); "
                "'screen_bright' = Screen transitioned to bright (photodiode detected high luminance). "
                "The Frame2TTL device uses a photodiode to detect changes in screen luminance, "
                "providing precise timing of when visual stimuli are displayed on the monitor. "
                "This is essential for accurate stimulus-response latency measurements."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

        # Rotary encoder 0 (wheel tracking) - P0.5
        channel_id = "nidq#XD5"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]
        semantic_labels = np.array(["phase_low", "phase_high"])
        label_mapping = {"XD5 OFF": 0, "XD5 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]
        labeled_events = LabeledEvents(
            name="EventsRotaryEncoder0",
            description=(
                "Rotary encoder pulses tracking wheel movement (quadrature phase A). "
                "Labels: 'phase_low' = Encoder phase transition to LOW; "
                "'phase_high' = Encoder phase transition to HIGH. "
                "Each pulse represents a discrete angular increment of the wheel rotation, "
                "used to measure behavioral responses and locomotion with high temporal precision."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

        # Rotary encoder 1 (wheel tracking, quadrature channel 2) - P0.6
        channel_id = "nidq#XD6"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]
        semantic_labels = np.array(["phase_low", "phase_high"])
        label_mapping = {"XD6 OFF": 0, "XD6 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]
        labeled_events = LabeledEvents(
            name="EventsRotaryEncoder1",
            description=(
                "Rotary encoder pulses tracking wheel movement (quadrature phase B). "
                "Labels: 'phase_low' = Encoder phase transition to LOW; "
                "'phase_high' = Encoder phase transition to HIGH. "
                "Combined with rotary_encoder_0, this provides directional information "
                "for wheel rotation through quadrature encoding."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

        # Audio (auditory stimulus) - P0.7
        channel_id = "nidq#XD7"
        events_structure = self.event_extractor.get_events(channel_id=channel_id)
        timestamps = events_structure["time"]
        raw_labels = events_structure["label"]
        ordered_indices = np.argsort(timestamps)
        ordered_timestamps = timestamps[ordered_indices]
        ordered_raw_labels = raw_labels[ordered_indices]
        semantic_labels = np.array(["audio_off", "audio_on"])
        label_mapping = {"XD7 OFF": 0, "XD7 ON": 1}
        data = [label_mapping[str(label)] for label in ordered_raw_labels]
        labeled_events = LabeledEvents(
            name="EventsAudio",
            description=(
                "Auditory stimulus presentation events. "
                "Labels: 'audio_off' = Audio stimulus off; 'audio_on' = Audio stimulus on. "
                "Marks timing of audio stimulus delivery for auditory tasks or cue presentation."
            ),
            timestamps=ordered_timestamps,
            data=data,
            labels=semantic_labels,
        )
        nwbfile.add_acquisition(labeled_events)

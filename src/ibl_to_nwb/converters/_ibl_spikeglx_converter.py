from pathlib import Path
from typing import Optional
import logging
import time

import numpy as np
from brainbox.io.one import SpikeSortingLoader
from neuroconv.datainterfaces import SpikeGLXRecordingInterface, SpikeGLXSyncChannelInterface
from neuroconv.nwbconverter import ConverterPipe
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile
from spikeinterface.extractors.extractor_classes import SpikeGLXRecordingExtractor

from ..fixtures import get_probe_name_to_probe_id_dict


def _format_probe_label(probe_name: str) -> str:
    """Return the standardized Neuropixels probe label (e.g., 'NeuropixelsProbe01')."""
    if probe_name.lower().startswith("probe"):
        suffix = probe_name[5:]
    else:
        suffix = probe_name
    return f"NeuropixelsProbe{suffix}"


class IblSpikeGlxConverter(ConverterPipe):
    # Use BWM standard revision for spike sorting data
    REVISION: str | None = "2025-05-06"

    def __init__(
        self, folder_path: DirectoryPath, one: ONE, eid: str, probe_name_to_probe_id_dict: dict, streams=None
    ) -> None:
        folder_path = Path(folder_path)

        # Create interfaces manually from probe subfolders
        # This avoids Neo's duplicate stream name bug when scanning parent folder
        data_interfaces = {}

        for probe_name in probe_name_to_probe_id_dict.keys():
            probe_folder = folder_path / probe_name  # e.g., raw_ephys_data/probe00

            if not probe_folder.exists():
                continue  # Skip if probe folder doesn't exist

            # Auto-detect available streams (handles imec.ap, imec0.ap, imec1.ap variants)
            available_streams = SpikeGLXRecordingExtractor.get_streams(folder_path=str(probe_folder))[0]

            # Filter to AP/LF bands only (exclude SYNC streams)
            ap_lf_streams = [s for s in available_streams if s.endswith('.ap') or s.endswith('.lf')]

            for stream_id in ap_lf_streams:
                # Create interface pointing to probe subfolder
                # Neo will only see one probe's files, avoiding duplicate stream names
                interface = SpikeGLXRecordingInterface(
                    folder_path=str(probe_folder),
                    stream_id=stream_id
                )

                # Normalize stream naming: imec0/imec1 → imec for consistent internal keys
                # Key format: "probe00.imec.ap", "probe00.imec.lf", etc.
                # This preserves probe identity throughout the pipeline
                normalized_stream = stream_id.replace('imec0', 'imec').replace('imec1', 'imec')
                key = f"{probe_name}.{normalized_stream}"
                data_interfaces[key] = interface

        # Initialize parent with pre-built interfaces (bypasses Neo's auto-discovery)
        ConverterPipe.__init__(self, data_interfaces=data_interfaces, verbose=False)

        # Store ONE, eid, probe mappings
        self.one = one
        self.eid = eid
        self.probe_name_to_probe_id_dict = probe_name_to_probe_id_dict
        self.revision = self.REVISION

        # Build mappings for metadata (updated to handle new key format)
        probe_to_imec_map = {"probe00": 0, "probe01": 1}
        self.imec_to_probe_map = dict(zip(probe_to_imec_map.values(), probe_to_imec_map.keys()))

        self.stream_to_probe_map = {}
        self.device_name_to_probe_map = {}

        for key in self.data_interface_objects.keys():
            # Skip NIDQ interface (doesn't follow probe naming convention)
            if key == "nidq":
                continue

            # Parse key: "probe00.imec.ap" -> probe_name="probe00", imec_name="imec", band="ap"
            parts = key.split(".")
            probe_name = parts[0]  # "probe00"
            imec_name = parts[1]   # "imec"
            band = parts[2]        # "ap" or "lf"

            # Map imec -> probe for alignment
            self.stream_to_probe_map[imec_name] = probe_name

            # Map device name for metadata
            # NeuroConv uses different device names depending on file naming:
            # - "NeuropixelsImec" for files named imec.ap.bin (no-NIDQ sessions)
            # - "NeuropixelsImec0" for files named imec0.ap.bin (NIDQ sessions)
            # - "NeuropixelsImec1" for files named imec1.ap.bin (multi-probe NIDQ sessions)
            self.device_name_to_probe_map["NeuropixelsImec"] = probe_name
            self.device_name_to_probe_map["NeuropixelsImec0"] = probe_name
            self.device_name_to_probe_map["NeuropixelsImec1"] = probe_name

        # Override electrical series names and group names to use IBL convention
        # This must happen in __init__ before any metadata/electrode operations
        for key, recording_interface in self.data_interface_objects.items():
            # Skip NIDQ interface (doesn't follow probe naming convention)
            if key == "nidq":
                continue

            # Skip sync channel interfaces (they create TimeSeries, not ElectricalSeries)
            if '.sync' in key:
                continue

            parts = key.split(".")
            probe_name = parts[0]  # "probe00"
            band = parts[2]        # "ap" or "lf"

            # Update electrical series key to use IBL probe naming
            # e.g., "ElectricalSeriesAPImec" -> "ElectricalSeriesProbe00AP"
            band_caps = band.upper()
            ibl_es_key = f"ElectricalSeries{probe_name.capitalize()}{band_caps}"
            recording_interface.es_key = ibl_es_key

            # Update group_name property in recording extractor
            # This is critical for electrode deduplication in NeuroConv
            channel_ids = recording_interface.recording_extractor.get_channel_ids()
            ibl_group_name = _format_probe_label(probe_name)
            recording_interface.recording_extractor.set_property(
                key="group_name",
                ids=channel_ids,
                values=[ibl_group_name] * len(channel_ids)
            )

        # Add SYNC channel interface (one per probe, prefer AP band)
        sync_streams = [s for s in available_streams if '-SYNC' in s and '.ap-SYNC' in s]

        for stream_id in sync_streams:
            interface = SpikeGLXSyncChannelInterface(
                folder_path=str(probe_folder),
                stream_id=stream_id,
                verbose=False
            )

            # Normalize: "imec0.ap-SYNC" -> "imec.sync"
            normalized_stream = stream_id.replace('imec0', 'imec').replace('imec1', 'imec').replace('.ap-SYNC', '.sync')
            key = f"{probe_name}.{normalized_stream}"  # e.g., "probe00.imec.sync"
            data_interfaces[key] = interface

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare data file patterns required for raw SpikeGLX recordings.

        Returns
        -------
        dict
            Data requirements for raw ephys files (.cbin, .meta, .ch, wiring.json)
        """
        return {
            "one_objects": [],
            "exact_files_options": {
                "standard": [
                    # Compressed binary files (AP and LF bands)
                    "raw_ephys_data/probe*/_spikeglx_ephysData_g0_t0.imec*.ap.cbin",
                    "raw_ephys_data/probe*/_spikeglx_ephysData_g0_t0.imec*.lf.cbin",
                    # Metadata files
                    "raw_ephys_data/probe*/_spikeglx_ephysData_g0_t0.imec*.ap.meta",
                    "raw_ephys_data/probe*/_spikeglx_ephysData_g0_t0.imec*.lf.meta",
                    # Channel map files
                    "raw_ephys_data/probe*/_spikeglx_ephysData_g0_t0.imec*.ap.ch",
                    "raw_ephys_data/probe*/_spikeglx_ephysData_g0_t0.imec*.lf.ch",
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
        Download raw SpikeGLX data (.cbin, .meta, .ch files) for all probes.

        Uses SpikeSortingLoader.raw_electrophysiology() which downloads the raw data
        if not already cached.

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
            Download status with list of files downloaded
        """
        if logger:
            logger.info(f"Downloading raw SpikeGLX data (session {eid})")

        start_time = time.time()

        # Get probe insertions from fixture (fast, no Alyx query)
        probe_name_to_probe_id_dict = get_probe_name_to_probe_id_dict(eid)

        if logger:
            logger.info(f"  Found {len(probe_name_to_probe_id_dict)} probe(s)")

        downloaded_files = []

        # Download raw ephys data for each probe
        for probe_name, pid in probe_name_to_probe_id_dict.items():
            if logger:
                logger.info(f"  Downloading raw ephys data for {probe_name}")

            ssl = SpikeSortingLoader(one=one, eid=eid, pname=probe_name, pid=pid)

            # Download both AP and LF bands
            # stream=False triggers download if not cached
            # NO try-except - fail loudly if download fails
            for band in ['ap', 'lf']:
                ssl.raw_electrophysiology(band=band, stream=False, revision=cls.REVISION)
                if logger:
                    logger.info(f"    Downloaded {band.upper()} band data")

                # Track downloaded files
                downloaded_files.extend([
                    f"raw_ephys_data/{probe_name}/_spikeglx_ephysData_g0_t0.imec.{band}.cbin",
                    f"raw_ephys_data/{probe_name}/_spikeglx_ephysData_g0_t0.imec.{band}.meta",
                    f"raw_ephys_data/{probe_name}/_spikeglx_ephysData_g0_t0.imec.{band}.ch",
                ])

        download_time = time.time() - start_time

        if logger:
            logger.info(
                f"  Downloaded raw ephys data for {len(probe_name_to_probe_id_dict)} probe(s) "
                f"in {download_time:.2f}s"
            )

        return {
            "success": True,
            "downloaded_objects": ["raw_spikeglx"],
            "downloaded_files": downloaded_files,
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def get_metadata(self):
        """
        Override to use IBL naming convention for electrode groups and devices.

        IBL naming:
        - Devices: NeuropixelsProbe00, NeuropixelsProbe01
        - Electrode groups: NeuropixelsProbe00, NeuropixelsProbe01

        Note: group_name properties in recording extractors are already updated in __init__,
        so we only need to update the metadata dictionaries here.
        """
        # Generate metadata with already-updated group names
        metadata = super().get_metadata()

        # Update device names to IBL convention
        if "Device" in metadata.get("Ecephys", {}):
            for device in metadata["Ecephys"]["Device"]:
                # Map device name using pre-built mapping
                original_name = device["name"]
                if original_name in self.device_name_to_probe_map:
                    probe_name = self.device_name_to_probe_map[original_name]
                    device["name"] = _format_probe_label(probe_name)

        # Update electrode groups to reference new device names and use IBL convention
        if "ElectrodeGroup" in metadata.get("Ecephys", {}):
            for group in metadata["Ecephys"]["ElectrodeGroup"]:
                # Update device reference
                if "device" in group:
                    original_device = group["device"]
                    if original_device in self.device_name_to_probe_map:
                        probe_name = self.device_name_to_probe_map[original_device]
                        group["device"] = _format_probe_label(probe_name)

                # Group name is already updated from the property change above
                if "name" in group:
                    original_name = group["name"]
                    if original_name in self.device_name_to_probe_map:
                        probe_name = self.device_name_to_probe_map[original_name]
                        group["name"] = _format_probe_label(probe_name)
                    elif original_name.startswith("NeuropixelsShank_"):
                        probe_name = original_name.replace("NeuropixelsShank_", "")
                        group["name"] = _format_probe_label(probe_name)

                    group["description"] = f"Electrode group for IBL {group['name']}"

        return metadata

    def temporally_align_data_interfaces(self) -> None:
        """Align the raw data timestamps to the other data streams using the ONE API."""

        # only interate over present data interfaces
        for key, interface in self.data_interface_objects.items():
            # Parse new key format: "probe00.imec.ap" -> probe_name="probe00", band="ap"
            parts = key.split(".")
            probe_name = parts[0]  # "probe00"

            # Determine band: sync channels use AP band alignment
            if '.sync' in key:
                band = 'ap'  # Sync came from AP-SYNC stream
            else:
                band = parts[2]  # "ap" or "lf"

            pid = self.probe_name_to_probe_id_dict[probe_name]

            spike_sorting_loader = SpikeSortingLoader(pid=pid, eid=self.eid, pname=probe_name, one=self.one)
            # stream = False if "USE_SDSC_ONE" in os.environ else True
            stream = False
            sglx_streamer = spike_sorting_loader.raw_electrophysiology(
                band=band, stream=stream, revision=self.revision
            )

            # data_one = sglx_streamer._raw

            # if all we need is the number of samples, then this seems a bit overkill
            # and it is a not possible to get this work offline
            # sl = spike_sorting_loader.raw_electrophysiology(band=band, stream=True)

            # rather, the ns can be retrieved directly from the recording interface
            # ns = recording_interface._extractor_instance.get_num_samples()
            # aligned_timestamps = spike_sorting_loader.samples2times(np.arange(0, sl.ns), direction="forward")
            aligned_timestamps = spike_sorting_loader.samples2times(
                np.arange(0, sglx_streamer.ns), direction="forward", band=band
            )

            # Handle different interface types
            if hasattr(interface, 'set_aligned_timestamps'):
                # Recording interfaces (AP/LF) have this method
                interface.set_aligned_timestamps(aligned_timestamps=aligned_timestamps)
            elif hasattr(interface, 'recording_extractor'):
                # Sync interface doesn't have set_aligned_timestamps, use recording_extractor directly
                interface.recording_extractor.set_times(times=aligned_timestamps, with_warning=False)

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata, **conversion_options_kwargs) -> None:
        # Build conversion options from kwargs (which come from IblConverter unpacking)
        conversion_options = conversion_options_kwargs

        interface_names = list(self.data_interface_objects.keys())
        non_nidq_interfaces = [name for name in interface_names if name != "nidq"]
        for interface_name in non_nidq_interfaces:
            # Merge stub_test option with always_write_timestamps
            if interface_name not in conversion_options:
                conversion_options[interface_name] = dict()
            conversion_options[interface_name]["always_write_timestamps"] = True

        self.temporally_align_data_interfaces()
        super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, conversion_options=conversion_options)

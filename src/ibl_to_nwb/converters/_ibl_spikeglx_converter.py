from brainbox.io.one import SpikeSortingLoader
from neuroconv.converters import SpikeGLXConverterPipe
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile


def _format_probe_label(probe_name: str) -> str:
    """Return the standardized Neuropixels probe label (e.g., 'NeuropixelsProbe01')."""
    if probe_name.lower().startswith("probe"):
        suffix = probe_name[5:]
    else:
        suffix = probe_name
    return f"NeuropixelsProbe{suffix}"


class IblSpikeGlxConverter(SpikeGLXConverterPipe):
    def __init__(
        self, folder_path: DirectoryPath, one: ONE, eid: str, pname_pid_map: dict, revision: str, streams=None
    ) -> None:
        # # debug injection
        # streams = ['imec0.lf','imec1.lf']
        super().__init__(folder_path=folder_path, streams=streams)
        self.one = one
        self.eid = eid
        self.pname_pid_map = pname_pid_map
        self.revision = revision

        # get valid pnames
        probe_to_imec_map = {
            "probe00": 0,
            "probe01": 1,
        }
        self.imec_to_probe_map = dict(zip(probe_to_imec_map.values(), probe_to_imec_map.keys()))

        # excluding probes
        interfaces_to_drop = []
        for key, recording_interface in self.data_interface_objects.items():
            if key != "nidq":
                imec_name, band = key.split(".")
                probe_name = self.imec_to_probe_map[int(imec_name[-1])]
                if probe_name not in self.pname_pid_map:
                    interfaces_to_drop.append(key)

        # TEMPORARY: Exclude NIDQ interface to avoid large memory allocation from event memmap
        if "nidq" in self.data_interface_objects:
            interfaces_to_drop.append("nidq")

        # by dropping their data interface
        for interface in interfaces_to_drop:
            self.data_interface_objects.pop(interface)

        # Override electrical series names and group names to use IBL convention
        # This must happen in __init__ before any metadata/electrode operations
        for key, recording_interface in self.data_interface_objects.items():
            if key != "nidq":
                imec_name, band = key.split(".")
                imec_num = int(imec_name[-1])
                probe_name = self.imec_to_probe_map[imec_num]

                # Update electrical series key to use IBL probe naming
                # e.g., "ElectricalSeriesAPImec0" -> "ElectricalSeriesAP_probe00"
                original_es_key = recording_interface.es_key
                band_caps = band.upper()

                # Construct IBL-style electrical series name
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
                # Extract imec number from "NeuropixelsImec0" -> 0
                original_name = device["name"]
                if "NeuropixelsImec" in original_name:
                    imec_num = int(original_name.replace("NeuropixelsImec", ""))
                    probe_name = self.imec_to_probe_map[imec_num]
                    device["name"] = _format_probe_label(probe_name)

        # Update electrode groups to reference new device names and use IBL convention
        if "ElectrodeGroup" in metadata.get("Ecephys", {}):
            for group in metadata["Ecephys"]["ElectrodeGroup"]:
                # Update device reference
                if "device" in group:
                    original_device = group["device"]
                    if "NeuropixelsImec" in original_device:
                        imec_num = int(original_device.replace("NeuropixelsImec", ""))
                        probe_name = self.imec_to_probe_map[imec_num]
                        group["device"] = _format_probe_label(probe_name)

                # Group name is already updated from the property change above
                if "name" in group:
                    original_name = group["name"]
                    if "NeuropixelsImec" in original_name:
                        imec_num = int(original_name.replace("NeuropixelsImec", ""))
                        probe_name = self.imec_to_probe_map[imec_num]
                        group["name"] = _format_probe_label(probe_name)
                    elif original_name.startswith("NeuropixelsShank_"):
                        probe_name = original_name.replace("NeuropixelsShank_", "")
                        group["name"] = _format_probe_label(probe_name)

                    group["description"] = f"Electrode group for IBL {group['name']}"

        return metadata

    def temporally_align_data_interfaces(self) -> None:
        """Align the raw data timestamps to the other data streams using the ONE API."""

        # only interate over present data interfaces
        for key, recording_interface in self.data_interface_objects.items():
            if key != "nidq":
                imec_name, band = key.split(".")
                probe_name = self.imec_to_probe_map[int(imec_name[-1])]
                pid = self.pname_pid_map[probe_name]

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
                recording_interface.set_aligned_timestamps(aligned_timestamps=aligned_timestamps)

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

        # self.temporally_align_data_interfaces()
        super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, conversion_options=conversion_options)

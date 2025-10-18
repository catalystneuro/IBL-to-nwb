import numpy as np
from brainbox.io.one import SpikeSortingLoader
from iblatlas.atlas import AllenAtlas
from iblatlas.regions import BrainRegions
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

        # Override electrical series names to use IBL convention
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

    def get_metadata(self):
        """
        Override to use IBL naming convention for electrode groups and devices.

        IBL naming:
        - Devices: NeuropixelsProbe00, NeuropixelsProbe01
        - Electrode groups: NeuropixelsProbe00, NeuropixelsProbe01
        Channel naming is handled upstream by NeuroConv (>=0.8.2), which ensures AP and LF
        bands share electrode table entries while avoiding duplicates. Earlier NeuroConv
        versions used the NeuropixelsImec* naming scheme, so we still remap devices and
        groups here to keep the IBL convention.
        """
        # First, update group_name properties in all recording extractors
        for key, recording_interface in self.data_interface_objects.items():
            if key != "nidq":
                imec_name, band = key.split(".")
                imec_num = int(imec_name[-1])
                probe_name = self.imec_to_probe_map[imec_num]

                # Set IBL-style group name for all channels
                channel_ids = recording_interface.recording_extractor.get_channel_ids()
                ibl_group_name = _format_probe_label(probe_name)
                recording_interface.recording_extractor.set_property(
                    key="group_name",
                    ids=channel_ids,
                    values=[ibl_group_name] * len(channel_ids)
                )

        # Now generate metadata with updated group names
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

    def _add_electrode_localization(self, nwbfile: NWBFile) -> None:
        """
        Add anatomical localization (CCF coordinates and brain regions) to electrodes table.

        This method:
        1. Loads histology data for each probe from IBL
        2. Adds CCF coordinate columns (x, y, z) to electrodes table
        3. Adds brain region columns (location, beryl_location, cosmos_location) to electrodes table
        4. Populates the columns with electrode-specific anatomical information

        Only probes with high-quality histology ('alf' or 'resolved') are processed.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file containing the electrodes table to populate
        """
        atlas = AllenAtlas()
        brain_regions = BrainRegions()

        # Add columns to electrodes table if they don't exist
        num_electrodes = len(nwbfile.electrodes)

        if 'x' not in nwbfile.electrodes.colnames:
            nwbfile.add_electrode_column(
                name='x',
                description='CCF x coordinate (medio-lateral) in micrometers',
                data=[float('nan')] * num_electrodes
            )

        if 'y' not in nwbfile.electrodes.colnames:
            nwbfile.add_electrode_column(
                name='y',
                description='CCF y coordinate (antero-posterior) in micrometers',
                data=[float('nan')] * num_electrodes
            )

        if 'z' not in nwbfile.electrodes.colnames:
            nwbfile.add_electrode_column(
                name='z',
                description='CCF z coordinate (dorso-ventral) in micrometers',
                data=[float('nan')] * num_electrodes
            )

        if 'beryl_location' not in nwbfile.electrodes.colnames:
            nwbfile.add_electrode_column(
                name='beryl_location',
                description='Brain region in IBL Beryl atlas (coarse functional grouping)',
                data=[''] * num_electrodes
            )

        if 'cosmos_location' not in nwbfile.electrodes.colnames:
            nwbfile.add_electrode_column(
                name='cosmos_location',
                description='Brain region in IBL Cosmos atlas (very coarse functional grouping)',
                data=[''] * num_electrodes
            )

        # Process each probe
        for key in self.data_interface_objects.keys():
            if key == "nidq":
                continue

            imec_name, band = key.split(".")
            imec_num = int(imec_name[-1])
            probe_name = self.imec_to_probe_map[imec_num]
            pid = self.pname_pid_map[probe_name]

            # Load histology data
            ssl = SpikeSortingLoader(pid=pid, eid=self.eid, pname=probe_name, one=self.one, atlas=atlas)

            try:
                _, _, channels = ssl.load_spike_sorting(revision=self.revision)
            except Exception as e:
                print(f"Warning: Could not load histology for {probe_name}: {e}")
                continue

            # Check histology quality
            histology_quality = ssl.histology
            if not histology_quality:
                # Fallback: check insertion extended_qc
                insertion = self.one.alyx.rest('insertions', 'read', id=pid)
                extended_qc = insertion.get('json', {}).get('extended_qc', {})
                if extended_qc.get('tracing_exists') and extended_qc.get('alignment_resolved'):
                    histology_quality = 'resolved'
                elif extended_qc.get('alignment_count', 0) > 0:
                    histology_quality = 'aligned'

            # Only process high-quality histology
            if histology_quality not in ['alf', 'resolved']:
                print(f"Skipping {probe_name}: histology quality '{histology_quality}' not sufficient")
                continue

            n_channels = len(channels['x'])

            # Convert IBL coordinates to CCF
            ibl_coords_m = np.column_stack([channels['x'], channels['y'], channels['z']])
            ccf_coords_um = atlas.xyz2ccf(ibl_coords_m)
            ccf_coords_x_um = ccf_coords_um[:, 0]
            ccf_coords_y_um = ccf_coords_um[:, 1]
            ccf_coords_z_um = ccf_coords_um[:, 2]

            # Compute Beryl/Cosmos locations
            channel_atlas_ids = channels['atlas_id']
            beryl_locations = brain_regions.id2acronym(atlas_id=channel_atlas_ids, mapping="Beryl")
            cosmos_locations = brain_regions.id2acronym(atlas_id=channel_atlas_ids, mapping="Cosmos")

            # Find electrodes for this probe
            ibl_group_name = _format_probe_label(probe_name)
            electrode_indices = []
            for index in range(len(nwbfile.electrodes)):
                if nwbfile.electrodes['group_name'][index] == ibl_group_name:
                    electrode_indices.append(index)

            # Populate electrodes table
            # Note: AP and LF bands create duplicate electrodes, so we use modulo to map to channel index
            for electrode_index in electrode_indices:
                channel_index = electrode_index % n_channels

                nwbfile.electrodes['x'].data[electrode_index] = float(ccf_coords_x_um[channel_index])
                nwbfile.electrodes['y'].data[electrode_index] = float(ccf_coords_y_um[channel_index])
                nwbfile.electrodes['z'].data[electrode_index] = float(ccf_coords_z_um[channel_index])
                nwbfile.electrodes['location'].data[electrode_index] = str(channels['acronym'][channel_index])
                nwbfile.electrodes['beryl_location'].data[electrode_index] = str(beryl_locations[channel_index])
                nwbfile.electrodes['cosmos_location'].data[electrode_index] = str(cosmos_locations[channel_index])

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

        # Add anatomical localization to electrodes table
        self._add_electrode_localization(nwbfile)

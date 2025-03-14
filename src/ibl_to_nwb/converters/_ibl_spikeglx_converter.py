import numpy as np
from brainbox.io.one import EphysSessionLoader, SpikeSortingLoader
from neuroconv.converters import SpikeGLXConverterPipe
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile


class IblSpikeGlxConverter(SpikeGLXConverterPipe):
    def __init__(self, folder_path: DirectoryPath, one: ONE, eid: str, pname_pid_map: dict, revision: str, streams=None) -> None:
        super().__init__(folder_path=folder_path, streams=streams)
        self.one = one
        self.eid = eid
        self.pname_pid_map = pname_pid_map
        self.revision = revision

    def temporally_align_data_interfaces(self) -> None:
        """Align the raw data timestamps to the other data streams using the ONE API."""
        probe_to_imec_map = {
            "probe00": 0,
            "probe01": 1,
        }
        imec_to_probe_map = dict(zip(probe_to_imec_map.values(), probe_to_imec_map.keys()))
        
        # only interate over present data interfaces
        for key, recording_interface in self.data_interface_objects.items():
            if key != 'nidq':
                imec_name, band = key.split('.')
                probe_name = imec_to_probe_map[int(imec_name[-1])]
                pid = self.pname_pid_map[probe_name]

                spike_sorting_loader = SpikeSortingLoader(pid=pid, one=self.one) # FIXME
                sl = spike_sorting_loader.raw_electrophysiology(band=band, stream=True) # FIXME
                aligned_timestamps = spike_sorting_loader.samples2times(np.arange(0, sl.ns), direction="forward")
                recording_interface.set_aligned_timestamps(aligned_timestamps=aligned_timestamps)

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata) -> None:
        self.temporally_align_data_interfaces()
        super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)

        # TODO: Add ndx-extracellular-ephys here

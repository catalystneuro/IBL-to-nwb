import numpy as np
from brainbox.io.one import SpikeSortingLoader
from neuroconv.converters import SpikeGLXConverterPipe
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile


class IblSpikeGlxConverter(SpikeGLXConverterPipe):
    def __init__(self, folder_path: DirectoryPath, one: ONE, eid: str, streams: None) -> None:
        super().__init__(folder_path=folder_path, streams=streams)
        self.one = one
        self.eid = eid

    def temporally_align_data_interfaces(self) -> None:
        """Align the raw data timestamps to the other data streams using the ONE API."""
        # This is the syntax for aligning the raw timestamps; I cannot test this without the actual data as stored
        # on your end, so please work with Heberto if there are any problems after uncommenting
        probe_to_imec_map = {
            "probe00": 0,
            "probe01": 1,
        }
        imec_to_probe_map = dict(zip(probe_to_imec_map.values(), probe_to_imec_map.keys()))

        # new way - only interate over present data interfaces
        for key, recording_interface in self.data_interface_objects.items():
            imec_name, band = key.split(".")
            probe_name = imec_to_probe_map[int(imec_name[-1])]
            pids, pnames = self.one.eid2pid(self.eid)
            pid = dict(zip(pnames, pids))[probe_name]

            spike_sorting_loader = SpikeSortingLoader(pid=pid, one=self.one)
            sl = spike_sorting_loader.raw_electrophysiology(band=band, stream=True)
            aligned_timestamps = spike_sorting_loader.samples2times(np.arange(0, sl.ns), direction="forward")
            recording_interface.set_aligned_timestamps(aligned_timestamps=aligned_timestamps)

        # ephys_session_loader = EphysSessionLoader(one=self.one, eid=self.eid)
        # for probe_name, pid in ephys_session_loader.probes.items():
        #     spike_sorting_loader = SpikeSortingLoader(pid=pid, one=self.one)

        #     probe_index = probe_to_imec_map[probe_name]
        #     for band in ["ap", "lf"]:
        #         recording_interface = self.data_interface_objects[f"imec{probe_index}.{band}"]
        #         sl = spike_sorting_loader.raw_electrophysiology(band=band, stream=True)
        #         aligned_timestamps = spike_sorting_loader.samples2times(np.arange(0, sl.ns), direction="forward")
        #         recording_interface.set_aligned_timestamps(aligned_timestamps=aligned_timestamps)
        # pass

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata) -> None:
        self.temporally_align_data_interfaces()
        super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)

        # TODO: Add ndx-extracellular-ephys here

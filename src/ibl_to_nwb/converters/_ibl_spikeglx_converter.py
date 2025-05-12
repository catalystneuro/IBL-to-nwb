import os
import numpy as np
from brainbox.io.one import SpikeSortingLoader
from neuroconv.converters import SpikeGLXConverterPipe
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile

class IblSpikeGlxConverter(SpikeGLXConverterPipe):
    def __init__(self, folder_path: DirectoryPath, one: ONE, eid: str, pname_pid_map: dict, revision: str, streams=None) -> None:
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
            if key != 'nidq':
                imec_name, band = key.split('.')
                probe_name = self.imec_to_probe_map[int(imec_name[-1])]
                if probe_name not in self.pname_pid_map:
                    interfaces_to_drop.append(key)
        
        # by dropping their data interface
        for interface in interfaces_to_drop:
            self.data_interface_objects.pop(interface)


    def temporally_align_data_interfaces(self) -> None:
        """Align the raw data timestamps to the other data streams using the ONE API."""
        
        # only interate over present data interfaces
        for key, recording_interface in self.data_interface_objects.items():
            if key != 'nidq':
                imec_name, band = key.split('.')
                probe_name = self.imec_to_probe_map[int(imec_name[-1])]
                pid = self.pname_pid_map[probe_name]

                spike_sorting_loader = SpikeSortingLoader(pid=pid, eid=self.eid, pname=probe_name, one=self.one)
                # stream = False if "USE_SDSC_ONE" in os.environ else True
                stream = False
                sglx_streamer = spike_sorting_loader.raw_electrophysiology(band=band, stream=stream, revision=self.revision)
                
                # data_one = sglx_streamer._raw

                # if all we need is the number of samples, then this seems a bit overkill
                # and it is a not possible to get this work offline
                # sl = spike_sorting_loader.raw_electrophysiology(band=band, stream=True)

                # rather, the ns can be retrieved directly from the recording interface
                # ns = recording_interface._extractor_instance.get_num_samples()
                # aligned_timestamps = spike_sorting_loader.samples2times(np.arange(0, sl.ns), direction="forward")
                aligned_timestamps = spike_sorting_loader.samples2times(np.arange(0, sglx_streamer.ns), direction="forward", band=band)
                recording_interface.set_aligned_timestamps(aligned_timestamps=aligned_timestamps)

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata) -> None:
        self.temporally_align_data_interfaces()
        super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)

        # TODO: Add ndx-extracellular-ephys here

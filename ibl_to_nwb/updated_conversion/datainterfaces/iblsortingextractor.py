"""The interface for loadding spike sorted data via ONE access."""
from collections import defaultdict
from typing import Dict, Optional, Union

import numpy as np
from pydantic import DirectoryPath
from spikeinterface import BaseSorting, BaseSortingSegment


class IblSortingExtractor(BaseSorting):
    extractor_name = "IblSorting"
    installed = True  # check at class level if installed or not
    mode = "file"  # Not really, though...
    installation_mesg = ""
    name = "iblsorting"

<<<<<<< HEAD
    def __init__(self, session: str, cache_folder: Optional[DirectoryPath] = None):
        from one.api import ONE
=======
    def __init__(
        self,
        session: str,
        cache_folder: Optional[DirectoryPath] = None,
    ):
>>>>>>> 30b9a5392b209c28f249b00c368856db0608a008
        from brainbox.io.one import SpikeSortingLoader
        from ibllib.atlas import AllenAtlas
        from one.api import ONE

        one = ONE(cache_dir=cache_folder)
        atlas = AllenAtlas()

        dataset_contents = one.list_datasets(eid=session, collection="raw_ephys_data/*")
        raw_contents = [dataset_content for dataset_content in dataset_contents if not dataset_content.endswith(".npy")]
        probe_names = set([raw_content.split("/")[1] for raw_content in raw_contents])

        sorting_loaders = dict()
        spike_times_by_id = defaultdict(list)  # Cast lists per key as arrays after assembly
        unit_id_probe_property = list()
        unit_id_per_probe_shift = 0
        for probe_name in probe_names:
            sorting_loader = SpikeSortingLoader(eid=session, one=one, pname=probe_name, atlas=atlas)
            sorting_loaders.update({probe_name: sorting_loader})
            spikes, clusters, channels = sorting_loader.load_spike_sorting()
            number_of_units = len(spikes["clusters"])

            # TODO - compare speed against iterating over unique cluster IDs + vector index search
            for spike_cluster, spike_time in zip(spikes["clusters"], spikes["times"]):
                unit_id = unit_id_per_probe_shift + spike_cluster
                spike_times_by_id[unit_id].append(spike_time)

            unit_id_per_probe_shift += number_of_units
            unit_id_probe_property.extend([probe_name] * number_of_units)
        for unit_id in spike_times_by_id:  # Cast as arrays for fancy indexing
            spike_times_by_id[unit_id] = np.array(spike_times_by_id[unit_id])

        sampling_frequency = 30000.0  # Hard-coded to match SpikeGLX probe
        BaseSorting.__init__(self, sampling_frequency=sampling_frequency, unit_ids=list(spike_times_by_id.keys()))
        sorting_segment = IblSortingSegment(
            spike_times_by_id=spike_times_by_id,
        )
        self.add_sorting_segment(sorting_segment)

        # TODO: add more properties
        properties = dict(probe_name=unit_id_probe_property)
        for property_name, values in properties.items():
            self.set_property(key=property_name, values=np.array(values))


class IblSortingSegment(BaseSortingSegment):
    def __init__(self, sampling_frequency: float, spike_times_by_id: Dict[int, np.ndarray]):
        BaseSortingSegment.__init__(self)
        self._sampling_frequency = sampling_frequency
        self._spike_times_by_id = spike_times_by_id

    def get_unit_spike_train(
        self,
        unit_id: int,
        start_frame: Union[int, None] = None,
        end_frame: Union[int, None] = None,
    ) -> np.ndarray:
        times = np.array(self._spike_times_by_id[unit_id])  # Make a copy for possible mutation below
        frames = (times * self._sampling_frequency).astype(int)
        if start_frame is not None:
            frames = frames[frames >= start_frame]
        if end_frame is not None:
            frames = frames[frames < end_frame]
        return frames

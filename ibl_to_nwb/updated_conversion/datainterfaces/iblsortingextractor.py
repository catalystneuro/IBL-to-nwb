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

    def __init__(self, session: str, cache_folder: Optional[DirectoryPath] = None):
        from brainbox.io.one import SpikeSortingLoader
        from ibllib.atlas import AllenAtlas
        from ibllib.atlas.regions import BrainRegions
        from one.api import ONE

        one = ONE(
            base_url="https://openalyx.internationalbrainlab.org",
            password="international",
            silent=True,
            cache_dir=cache_folder,
        )  # cache_dir=cache_folder)
        atlas = AllenAtlas()
        brain_regions = BrainRegions()

        dataset_contents = one.list_datasets(eid=session, collection="raw_ephys_data/*")
        raw_contents = [dataset_content for dataset_content in dataset_contents if not dataset_content.endswith(".npy")]
        probe_names = set([raw_content.split("/")[1] for raw_content in raw_contents])

        sorting_loaders = dict()
        spike_times_by_id = defaultdict(list)  # Cast lists per key as arrays after assembly
        unit_id_probe_property = list()
        maximum_amplitude_channel = list()
        allen_location = list()
        beryl_location = list()
        cosmos_location = list()
        unit_id_per_probe_shift = 0
        for probe_name in probe_names:
            sorting_loader = SpikeSortingLoader(eid=session, one=one, pname=probe_name, atlas=atlas)
            sorting_loaders.update({probe_name: sorting_loader})
            spikes, clusters, channels = sorting_loader.load_spike_sorting()
            number_of_units = len(np.unique(spikes["clusters"]))

            # TODO - compare speed against iterating over unique cluster IDs + vector index search
            for spike_cluster, spike_time in zip(spikes["clusters"], spikes["times"]):
                unit_id = unit_id_per_probe_shift + spike_cluster
                spike_times_by_id[unit_id].append(spike_time)

            unit_id_per_probe_shift += number_of_units
            unit_id_probe_property.extend([probe_name] * number_of_units)

            # Maximum amplitude channel and locations
            unit_id_to_channel_id = clusters["channels"]
            maximum_amplitude_channel.extend(unit_id_to_channel_id)

            if sorting_loader.histology in ["alf", "resolved"]:  # Assume if one probe has histology, the other does too
                channel_id_to_allen_regions = channels["acronym"]
                channel_id_to_atlas_id = channels["atlas_id"]

                allen_location.extend(list(channel_id_to_allen_regions[unit_id_to_channel_id]))
                beryl_location.extend(
                    list(
                        brain_regions.id2acronym(
                            atlas_id=channel_id_to_atlas_id[unit_id_to_channel_id], mapping="Beryl"
                        )
                    )
                )
                cosmos_location.extend(
                    list(
                        brain_regions.id2acronym(
                            atlas_id=channel_id_to_atlas_id[unit_id_to_channel_id], mapping="Cosmos"
                        )
                    )
                )

        for unit_id in spike_times_by_id:  # Cast as arrays for fancy indexing
            spike_times_by_id[unit_id] = np.array(spike_times_by_id[unit_id])

        sampling_frequency = 30000.0  # Hard-coded to match SpikeGLX probe
        BaseSorting.__init__(self, sampling_frequency=sampling_frequency, unit_ids=list(spike_times_by_id.keys()))
        sorting_segment = IblSortingSegment(
            sampling_frequency=sampling_frequency,
            spike_times_by_id=spike_times_by_id,
        )
        self.add_sorting_segment(sorting_segment)

        # TODO: add more properties
        properties = dict(probe_name=unit_id_probe_property, maximum_amplitude_channel=maximum_amplitude_channel)
        if allen_location:
            properties.update(
                allen_location=allen_location, beryl_location=beryl_location, cosmos_location=cosmos_location
            )
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

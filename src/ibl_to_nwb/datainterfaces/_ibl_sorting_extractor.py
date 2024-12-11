"""The interface for loading spike sorted data via ONE access."""

from collections import defaultdict
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd
from pydantic import DirectoryPath
from spikeinterface import BaseSorting, BaseSortingSegment


class IblSortingExtractor(BaseSorting):
    extractor_name = "IblSorting"
    installed = True  # check at class level if installed or not
    mode = "file"  # Not really, though...
    installation_mesg = ""
    name = "iblsorting"

    def __init__(self, session: str, cache_folder: Optional[DirectoryPath] = None, revision=None):
        from brainbox.io.one import SpikeSortingLoader
        from iblatlas.atlas import AllenAtlas
        from iblatlas.regions import BrainRegions
        from one.api import ONE

        one = ONE(
            base_url="https://openalyx.internationalbrainlab.org",
            password="international",
            silent=True,
            cache_dir=cache_folder,
        )
        if revision is None: # latest
            revision = one.list_revisions(session)[-1]

        atlas = AllenAtlas()
        brain_regions = BrainRegions()

        dataset_contents = one.list_datasets(eid=session, collection="raw_ephys_data/*")
        raw_contents = [dataset_content for dataset_content in dataset_contents if not dataset_content.endswith(".npy")]
        probe_names = set([raw_content.split("/")[1] for raw_content in raw_contents])

        sorting_loaders = dict()
        spike_times_by_id = defaultdict(list)  # Cast lists per key as arrays after assembly
        spike_amplitudes_by_id = defaultdict(list)
        spike_depths_by_id = defaultdict(list)
        all_unit_properties = defaultdict(list)
        cluster_ids = list()
        unit_id_per_probe_shift = 0
        for probe_name in probe_names:
            sorting_loader = SpikeSortingLoader(eid=session, one=one, pname=probe_name, atlas=atlas)
            sorting_loaders.update({probe_name: sorting_loader})
            spikes, clusters, channels = sorting_loader.load_spike_sorting(revision=revision)
            # cluster_ids.extend(list(np.array(clusters["metrics"]["cluster_id"]) + unit_id_per_probe_shift))
            number_of_units = len(np.unique(spikes["clusters"]))
            cluster_ids.extend(list(np.arange(number_of_units).astype("int32") + unit_id_per_probe_shift))

            # TODO - compare speed against iterating over unique cluster IDs + vector index search
            for spike_cluster, spike_times, spike_amplitudes, spike_depths in zip(
                spikes["clusters"], spikes["times"], spikes["amps"], spikes["depths"]
            ):
                unit_id = unit_id_per_probe_shift + spike_cluster
                spike_times_by_id[unit_id].append(spike_times)
                spike_amplitudes_by_id[unit_id].append(spike_amplitudes)
                spike_depths_by_id[unit_id].append(spike_depths)

            unit_id_per_probe_shift += number_of_units
            all_unit_properties["probe_name"].extend([probe_name] * number_of_units)

            # Maximum amplitude channel and locations
            unit_id_to_channel_id = clusters["channels"]
            all_unit_properties["maximum_amplitude_channel"].extend(unit_id_to_channel_id)
            all_unit_properties["mean_relative_depth"].extend(clusters["depths"])

            ibl_metric_key_to_property_name = dict(
                amp_max="maximum_amplitude",
                amp_min="minimum_amplitude",
                amp_median="median_amplitude",
                amp_std_dB="standard_deviation_amplitude",
                contamination="contamination",
                contamination_alt="alternative_contamination",
                drift="drift",
                missed_spikes_est="missed_spikes_estimate",
                noise_cutoff="noise_cutoff",
                presence_ratio="presence_ratio",
                presence_ratio_std="presence_ratio_standard_deviation",
                slidingRP_viol="sliding_refractory_period_violation",
                spike_count="spike_count",
                firing_rate="firing_rate",
                label="label",
                cluster_uuid="cluster_uuid",
                cluster_id="cluster_id",
            )

            cluster_metrics = clusters["metrics"].reset_index(drop=True).join(pd.DataFrame(clusters["uuids"]))
            cluster_metrics.rename(columns={"uuids": "cluster_uuid"}, inplace=True)

            for ibl_metric_key, property_name in ibl_metric_key_to_property_name.items():
                all_unit_properties[property_name].extend(list(cluster_metrics[ibl_metric_key]))

            if sorting_loader.histology in ["alf", "resolved"]:  # Assume if one probe has histology, the other does too
                channel_id_to_allen_regions = channels["acronym"]
                channel_id_to_atlas_id = channels["atlas_id"]

                all_unit_properties["allen_location"].extend(list(channel_id_to_allen_regions[unit_id_to_channel_id]))
                all_unit_properties["beryl_location"].extend(
                    list(
                        brain_regions.id2acronym(
                            atlas_id=channel_id_to_atlas_id[unit_id_to_channel_id], mapping="Beryl"
                        )
                    )
                )
                all_unit_properties["cosmos_location"].extend(
                    list(
                        brain_regions.id2acronym(
                            atlas_id=channel_id_to_atlas_id[unit_id_to_channel_id], mapping="Cosmos"
                        )
                    )
                )

        for unit_id in spike_times_by_id:  # Cast as arrays for fancy indexing
            spike_times_by_id[unit_id] = np.array(spike_times_by_id[unit_id])
            spike_amplitudes_by_id[unit_id] = np.array(spike_amplitudes_by_id[unit_id])

        sampling_frequency = 30000.0  # Hard-coded to match SpikeGLX probe
        BaseSorting.__init__(self, sampling_frequency=sampling_frequency, unit_ids=list(spike_times_by_id.keys()))
        sorting_segment = IblSortingSegment(
            sampling_frequency=sampling_frequency,
            spike_times_by_id=spike_times_by_id,
        )
        self.add_sorting_segment(sorting_segment)

        # I know it looks weird, but it's the only way I could find
        self.set_property(
            key="spike_amplitudes",
            values=np.array(list(spike_amplitudes_by_id.values()), dtype=object),
            ids=cluster_ids,
        )
        self.set_property(
            key="spike_relative_depths",
            values=np.array(list(spike_depths_by_id.values()), dtype=object),
            ids=cluster_ids,
        )

        for property_name, values in all_unit_properties.items():
            self.set_property(key=property_name, values=values, ids=cluster_ids)


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

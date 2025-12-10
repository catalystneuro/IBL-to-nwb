"""The interface for loading spike sorted data via ONE access."""

from collections import defaultdict
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd
from brainbox.io.one import SpikeSortingLoader
from iblatlas.atlas import AllenAtlas
from iblatlas.regions import BrainRegions
from neuroconv.utils import get_json_schema_from_method_signature
from one.api import ONE
from spikeinterface import BaseSorting, BaseSortingSegment
from tqdm import tqdm


class IblSortingExtractor(BaseSorting):
    extractor_name = "IblSorting"
    installed = True  # check at class level if installed or not
    mode = "file"  # Not really, though...
    installation_mesg = ""
    name = "iblsorting"

    def get_source_schema(cls) -> dict:
        """
        Infer the JSON schema for the source_data from the method signature (annotation typing).

        Returns
        -------
        dict
            The JSON schema for the source_data.
        """
        return get_json_schema_from_method_signature(cls, exclude=["source_data", "one"])

    # def __init__(self, session: str, cache_folder: Optional[DirectoryPath] = None, revision: Optional[str] = None):
    def __init__(
        self,
        one: ONE,
        session: str,
        revision: Optional[str] = None,
    ):
        # Store parameters for lazy loading
        self.one = one
        self.session = session
        self.revision = revision if revision is not None else one.list_revisions(session)[-1]

        # Get probe names
        raw_ephys_datasets = one.list_datasets(eid=session, collection="raw_ephys_data/*")
        self.probe_names = set([filename.split("/")[1] for filename in raw_ephys_datasets])

        # Create sorting loaders but DON'T load data yet
        atlas = AllenAtlas()
        self.atlas = atlas
        self.brain_regions = BrainRegions()
        self.sorting_loaders = dict()
        for probe_name in self.probe_names:
            sorting_loader = SpikeSortingLoader(eid=session, one=one, pname=probe_name, atlas=atlas)
            self.sorting_loaders[probe_name] = sorting_loader

        # Store sampling frequency but defer BaseSorting.__init__() until data is loaded
        self._sampling_frequency = 30000.0

        # Flag to track if data has been loaded
        self._data_loaded = False

    def load_and_process_data(
        self, stub_test: bool = False, stub_units: Optional[int] = None, skip_properties: Optional[list[str]] = None
    ):
        """Load spike data and process into per-unit arrays.

        This method separates spike data by cluster/unit using np.where to index spike arrays.
        For full sessions with ~2000 units and ~60M spikes, this takes ~60-70 seconds.

        Alternative approaches tested but found slower:
        - Direct iteration over all spikes (too slow)
        - Pre-sorting + binary search (argsort + searchsorted overhead negates gains)

        Current limitation: O(n_spikes * n_units) complexity makes this the primary bottleneck.
        Mitigation: Use stub_test=True to process only a subset of units for testing/development.

        Parameters
        ----------
        stub_test : bool, default: False
            If True, only load a subset of units for testing
        stub_units : int, optional
            Number of units to load per probe when stub_test=True. Default is 10.
        skip_properties : list of str, optional
            Properties to skip computing/loading. Useful for memory optimization.
            For example: skip_properties=["spike_amplitudes_uv", "spike_relative_depths_um"]
        """
        if self._data_loaded:
            return  # Already loaded

        if stub_units is None:
            stub_units = 10

        if skip_properties is None:
            skip_properties = []

        spike_times_by_id = defaultdict(list)
        spike_amplitudes_by_id = defaultdict(list) if "spike_amplitudes_uv" not in skip_properties else None
        spike_depths_by_id = defaultdict(list) if "spike_relative_depths_um" not in skip_properties else None
        all_unit_properties = defaultdict(list)
        cluster_ids = list()
        unit_id_per_probe_shift = 0

        for probe_name in self.probe_names:
            # Load spike sorting data
            sorting_loader = self.sorting_loaders[probe_name]
            spikes, clusters, channels = sorting_loader.load_spike_sorting(revision=self.revision)

            # Determine which clusters to process
            unique_clusters = np.unique(spikes["clusters"])
            if stub_test:
                # Only process first N units for testing
                unique_clusters = unique_clusters[:stub_units]

            number_of_units = len(unique_clusters)
            cluster_ids.extend(list(np.arange(number_of_units).astype("int32") + unit_id_per_probe_shift))

            # Separate spikes by cluster using np.where indexing
            for cluster_index, spike_cluster in enumerate(
                tqdm(unique_clusters, desc=f"Separating spikes by cluster ({probe_name})", unit="cluster")
            ):
                spike_indices = np.where(spikes["clusters"] == spike_cluster)[0]
                unit_id = unit_id_per_probe_shift + cluster_index
                spike_times_by_id[unit_id] = spikes["times"][spike_indices]
                if spike_amplitudes_by_id is not None:
                    spike_amplitudes_by_id[unit_id] = spikes["amps"][spike_indices]
                if spike_depths_by_id is not None:
                    spike_depths_by_id[unit_id] = spikes["depths"][spike_indices]

            unit_id_per_probe_shift += number_of_units
            all_unit_properties["probe_name"].extend([probe_name] * number_of_units)

            # Maximum amplitude channel and locations (subset if stub_test)
            unit_id_to_channel_id = clusters["channels"][:number_of_units] if stub_test else clusters["channels"]
            all_unit_properties["maximum_amplitude_channel"].extend(unit_id_to_channel_id)
            mean_depths = clusters["depths"][:number_of_units] if stub_test else clusters["depths"]
            all_unit_properties["mean_relative_depth_um"].extend(mean_depths)

            ibl_metric_key_to_property_name = dict(
                amp_max="maximum_amplitude_uv",
                amp_min="minimum_amplitude_uv",
                amp_median="median_amplitude_uv",
                amp_std_dB="standard_deviation_amplitude_db",
                contamination="contamination",
                contamination_alt="alternative_contamination",
                drift="drift_um",
                missed_spikes_est="missed_spikes_estimate",
                noise_cutoff="noise_cutoff",
                presence_ratio="presence_ratio",
                presence_ratio_std="presence_ratio_standard_deviation",
                slidingRP_viol="sliding_refractory_period_violation",
                spike_count="spike_count",
                firing_rate="firing_rate_hz",
                label="ibl_quality_score",
                ks2_label="kilosort2_label",  # Original Kilosort2 classification (good/mua/noise)
                cluster_uuid="cluster_uuid",
                cluster_id="cluster_id",
                # NOTE: Removed x, y, z, ML, AP, DV - these are now accessed via electrodes table
            )

            cluster_metrics = clusters["metrics"].reset_index(drop=True).join(pd.DataFrame(clusters["uuids"]))
            cluster_metrics.rename(columns={"uuids": "cluster_uuid"}, inplace=True)

            # Subset cluster metrics if stub_test
            if stub_test:
                cluster_metrics = cluster_metrics.iloc[:number_of_units]

            # Add cluster metrics (spike count, firing rate, quality metrics, etc.)
            for ibl_metric_key, property_name in ibl_metric_key_to_property_name.items():
                all_unit_properties[property_name].extend(list(cluster_metrics[ibl_metric_key]))

            # NOTE: Removed anatomical location properties (allen_location, beryl_location, cosmos_location)
            # and coordinate properties (x, y, z, ML, AP, DV).
            # These are now accessed via the electrodes table through the unit-to-electrode link.

        # Initialize BaseSorting now that we know the unit_ids
        BaseSorting.__init__(self, sampling_frequency=self._sampling_frequency, unit_ids=cluster_ids)

        # Add sorting segment with spike times
        sorting_segment = IblSortingSegment(
            sampling_frequency=self._sampling_frequency,
            spike_times_by_id=spike_times_by_id,
        )
        self.add_sorting_segment(sorting_segment)

        # Set ragged array properties (spike-level data) if not skipped
        if spike_amplitudes_by_id is not None:
            self.set_property(
                key="spike_amplitudes_uv",
                values=np.array(list(spike_amplitudes_by_id.values()), dtype=object),
                ids=cluster_ids,
            )
        if spike_depths_by_id is not None:
            self.set_property(
                key="spike_relative_depths_um",
                values=np.array(list(spike_depths_by_id.values()), dtype=object),
                ids=cluster_ids,
            )

        for property_name, values in all_unit_properties.items():
            self.set_property(key=property_name, values=values, ids=cluster_ids)

        # Mark as loaded
        self._data_loaded = True

    def get_unit_spike_train(
        self,
        unit_id: str | int,
        segment_index: Union[int, None] = None,
        start_frame: Union[int, None] = None,
        end_frame: Union[int, None] = None,
        return_times: bool = False,
        use_cache: bool = True,
    ):
        segment_index = self._check_segment_index(segment_index)

        segment = self._sorting_segments[segment_index]
        spike_times = segment.get_unit_spike_times(unit_id=unit_id)

        # Apply time/frame filtering
        start_time = start_frame / self.get_sampling_frequency() if start_frame is not None else None
        end_time = end_frame / self.get_sampling_frequency() if end_frame is not None else None

        if start_time is not None:
            spike_times = spike_times[spike_times >= start_time]
        if end_time is not None:
            spike_times = spike_times[spike_times < end_time]

        # Return times or frames based on parameter
        if return_times:
            return spike_times
        else:
            # Convert times to frames
            return (spike_times * self.get_sampling_frequency()).astype(np.int64)


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

    def get_unit_spike_times(self, unit_id: int) -> np.ndarray:
        """
        Get the spike times for a given unit ID.

        Parameters
        ----------
        unit_id : int
            The ID of the unit.

        Returns
        -------
        np.ndarray
            The spike times in seconds.
        """
        return self._spike_times_by_id[unit_id]

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

    def load_ibl_data(
        self,
        stub_test: bool = False,
        stub_units: Optional[int] = None,
        skip_spike_amplitudes: bool = False,
        skip_spike_depths: bool = False,
    ) -> dict:
        """Load IBL spike sorting data and return it with IBL property names.

        This method separates spike data by cluster/unit using np.where to index spike arrays.
        For full sessions with ~2000 units and ~60M spikes, this takes ~60-70 seconds.

        Parameters
        ----------
        stub_test : bool, default: False
            If True, only load a subset of units for testing
        stub_units : int, optional
            Number of units to load per probe when stub_test=True. Default is 10.
        skip_spike_amplitudes : bool, default: False
            If True, skip loading per-spike amplitudes (saves memory).
        skip_spike_depths : bool, default: False
            If True, skip loading per-spike depths (saves memory).

        Returns
        -------
        dict
            Dictionary with IBL property names as keys:
            - "spike_times_by_id": dict mapping unit_id to spike times array
            - "spike_amplitudes_by_id": dict mapping unit_id to spike amplitudes (or None if skipped)
            - "spike_depths_by_id": dict mapping unit_id to spike depths (or None if skipped)
            - "cluster_ids": list of unit IDs
            - "unit_properties": dict with IBL property names as keys, lists of values
              Includes: probe_name, _max_amplitude_channel, cluster_depths, and all columns from clusters.metrics
        """
        if stub_units is None:
            stub_units = 10

        spike_times_by_id = defaultdict(list)
        spike_amplitudes_by_id = defaultdict(list) if not skip_spike_amplitudes else None
        spike_depths_by_id = defaultdict(list) if not skip_spike_depths else None
        unit_properties = defaultdict(list)
        cluster_ids = list()

        for probe_name in sorted(self.probe_names):
            # Load spike sorting data
            sorting_loader = self.sorting_loaders[probe_name]
            spikes, clusters, channels = sorting_loader.load_spike_sorting(revision=self.revision)

            # Determine which clusters to process
            unique_clusters = np.unique(spikes["clusters"])
            if stub_test:
                # Only process first N units for testing
                unique_clusters = unique_clusters[:stub_units]

            number_of_units = len(unique_clusters)
            # Generate unit IDs with probe name prefix: probe00_0, probe00_1, probe01_0, etc.
            probe_cluster_ids = [f"{probe_name}_{i}" for i in range(number_of_units)]
            cluster_ids.extend(probe_cluster_ids)

            # Separate spikes by cluster using np.where indexing
            for cluster_index, spike_cluster in enumerate(
                tqdm(unique_clusters, desc=f"Separating spikes by cluster ({probe_name})", unit="cluster")
            ):
                spike_indices = np.where(spikes["clusters"] == spike_cluster)[0]
                unit_id = f"{probe_name}_{cluster_index}"
                spike_times_by_id[unit_id] = spikes["times"][spike_indices]
                if spike_amplitudes_by_id is not None:
                    spike_amplitudes_by_id[unit_id] = spikes["amps"][spike_indices]
                if spike_depths_by_id is not None:
                    spike_depths_by_id[unit_id] = spikes["depths"][spike_indices]

            # Unit properties with IBL names
            unit_properties["probe_name"].extend([probe_name] * number_of_units)

            # Maximum amplitude channel (used internally for electrode mapping)
            max_amp_channels = clusters["channels"][:number_of_units] if stub_test else clusters["channels"]
            unit_properties["_max_amplitude_channel"].extend(max_amp_channels)

            # Cluster depths
            cluster_depths = clusters["depths"][:number_of_units] if stub_test else clusters["depths"]
            unit_properties["cluster_depths"].extend(cluster_depths)

            # Cluster metrics (includes uuids)
            cluster_metrics = clusters["metrics"].reset_index(drop=True).join(pd.DataFrame(clusters["uuids"]))
            cluster_metrics.rename(columns={"uuids": "cluster_uuid"}, inplace=True)

            # Subset cluster metrics if stub_test
            if stub_test:
                cluster_metrics = cluster_metrics.iloc[:number_of_units]

            # Add all cluster metrics columns
            for column in cluster_metrics.columns:
                unit_properties[column].extend(list(cluster_metrics[column]))

        return {
            "spike_times_by_id": dict(spike_times_by_id),
            "spike_amplitudes_by_id": dict(spike_amplitudes_by_id) if spike_amplitudes_by_id else None,
            "spike_depths_by_id": dict(spike_depths_by_id) if spike_depths_by_id else None,
            "cluster_ids": cluster_ids,
            "unit_properties": dict(unit_properties),
        }

    def initialize_sorting(self, spike_times_by_id: dict, cluster_ids: list):
        """Initialize the BaseSorting with spike times.

        Parameters
        ----------
        spike_times_by_id : dict
            Dictionary mapping unit_id to spike times array
        cluster_ids : list
            List of unit IDs
        """
        if self._data_loaded:
            return

        # Initialize BaseSorting
        BaseSorting.__init__(self, sampling_frequency=self._sampling_frequency, unit_ids=cluster_ids)

        # Add sorting segment with spike times
        sorting_segment = IblSortingSegment(
            sampling_frequency=self._sampling_frequency,
            spike_times_by_id=spike_times_by_id,
        )
        self.add_sorting_segment(sorting_segment)

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
    def __init__(self, sampling_frequency: float, spike_times_by_id: Dict[str, np.ndarray]):
        BaseSortingSegment.__init__(self)
        self._sampling_frequency = sampling_frequency
        self._spike_times_by_id = spike_times_by_id

    def get_unit_spike_train(
        self,
        unit_id: str,
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

    def get_unit_spike_times(self, unit_id: str) -> np.ndarray:
        """
        Get the spike times for a given unit ID.

        Parameters
        ----------
        unit_id : str
            The ID of the unit (e.g., 'probe00_0', 'probe01_5').

        Returns
        -------
        np.ndarray
            The spike times in seconds.
        """
        return self._spike_times_by_id[unit_id]

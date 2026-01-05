"""The interface for loading spike sorted data via ONE access."""

from typing import Literal, Optional
import logging
import time

import numpy as np
from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import BaseSortingExtractorInterface
from neuroconv.tools.spikeinterface import add_sorting_to_nwbfile
from neuroconv.utils import DeepDict
from one.api import ONE
from pynwb import NWBFile
from brainbox.io.one import SpikeSortingLoader

from ._ibl_sorting_extractor import IblSortingExtractor
from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures import get_probe_name_to_probe_id_dict
from ..utils.probe_naming import get_ibl_probe_name

# Single source of truth for unit property metadata
# Keys are NWB property names (dict order = property order in NWB file)
# Values contain IBL source column name (or None if computed/set separately) and description
# Note: ibl_name refers to column name in clusters.metrics.pqt or other IBL data structures
UNITS_COLUMNS = {
    # Identification
    "probe_name": {
        "ibl_name": "probe_name",
        "description": "Name of probe this unit was recorded from in canonical format (e.g., 'Probe00', 'Probe01').",
    },
    "cluster_uuid": {
        "ibl_name": "cluster_uuid",
        "description": "Globally unique identifier for cross-referencing with IBL database via ONE API.",
    },
    # Core activity metrics
    "spike_count": {
        "ibl_name": "spike_count",
        "description": "Total number of spikes assigned to this unit. Integer type; -1 indicates missing data.",
    },
    "firing_rate": {
        "ibl_name": "firing_rate",
        "description": "Average firing rate in Hz.",
    },
    # Location
    "distance_from_probe_tip_um": {
        "ibl_name": "cluster_depths",
        "description": "Mean distance from the probe tip in micrometers, computed from waveform center of mass. 0 = probe tip, values increase toward brain surface.",
    },
    "max_electrode": {
        "ibl_name": "clusters.channels",  # Mapped through electrodes table
        "description": "Index into the electrodes table for the electrode with maximum spike amplitude for this unit.",
    },
    # Quality labels (what users check first)
    "ibl_quality_score": {
        "ibl_name": "label",
        "description": "Proportion of IBL quality metrics passed (0.0, 0.33, 0.67, or 1.0). 1.0 = all three passed.",
    },
    "kilosort2_label": {
        "ibl_name": "ks2_label",
        "description": "Original Kilosort2 classification: 'good', 'mua', or 'noise'.",
    },
    # Quality metrics (detailed breakdown)
    "sliding_rp_violation": {
        "ibl_name": "slidingRP_viol",
        "description": "Binary pass/fail (0.0 or 1.0) using sliding refractory period algorithm. Primary metric for ibl_quality_score. Aligns with SpikeInterface's sliding_rp_violations.",
    },
    "isi_violations_ratio": {
        "ibl_name": "contamination",
        "description": "Ratio of observed to expected ISI violations (Steinmetz/cortex-lab method). Can exceed 1.0. Equivalent to SpikeInterface's isi_violations_ratio.",
    },
    "rp_violation": {
        "ibl_name": "contamination_alt",
        "description": "Contamination estimate using Hill et al. (2011) quadratic formula. Aligns with SpikeInterface's rp_violations.",
    },
    "noise_cutoff": {
        "ibl_name": "noise_cutoff",
        "description": "Standard deviations the lower amplitude quartile deviates from expected. Large values indicate missed spikes at detection threshold.",
    },
    "missed_spikes_estimate": {
        "ibl_name": "missed_spikes_est",
        "description": "Estimated fraction of spikes missed due to detection threshold (0.0-1.0).",
    },
    # Stability metrics
    "presence_ratio": {
        "ibl_name": "presence_ratio",
        "description": "Fraction of time bins (60s default) with at least one spike. Good units typically >0.9.",
    },
    "presence_ratio_std": {
        "ibl_name": "presence_ratio_std",
        "description": "Standard deviation of spike counts across 10-second time bins.",
    },
    "cumulative_drift_um_per_hour": {
        "ibl_name": "drift",
        "description": "Sum of absolute depth changes between consecutive spikes, normalized to um/hour. Formula: sum(abs(diff(spike_depths)))/duration*3600. High values indicate either electrode drift or depth estimation noise. Scales with spike count (~0.79 correlation). NOT actual electrode displacement.",
    },
    # Amplitude statistics (in microvolts - natural unit for neuroscience)
    "median_spike_amplitude_uV": {
        "ibl_name": "amp_median",
        "description": "Median spike amplitude in microvolts. IBL uses 50 uV threshold for quality filtering.",
    },
    "min_spike_amplitude_uV": {
        "ibl_name": "amp_min",
        "description": "Minimum spike amplitude in microvolts.",
    },
    "max_spike_amplitude_uV": {
        "ibl_name": "amp_max",
        "description": "Maximum spike amplitude in microvolts.",
    },
    "spike_amplitude_std_dB": {
        "ibl_name": "amp_std_dB",
        "description": "Standard deviation of log-transformed spike amplitudes in decibels. High values (>6 dB) may indicate drift or contamination.",
    },
    # Waveform shape metrics
    "peak_to_trough_duration_ms": {
        "ibl_name": "peak_to_trough_duration_ms",
        "description": "Duration from negative trough to positive peak of the mean waveform in milliseconds. Used to distinguish fast-spiking interneurons (~0.2-0.4 ms) from regular-spiking pyramidal cells (~0.4-0.8+ ms).",
    },
    # Ragged arrays (per-spike data)
    "spike_amplitudes_uV": {
        "ibl_name": None,  # Set separately from spike data
        "description": "Peak amplitude of each spike for each unit in microvolts.",
    },
    "spike_distances_from_probe_tip_um": {
        "ibl_name": None,  # Set separately from spike data
        "description": "Distance from the probe tip for each spike in micrometers, computed from waveform center of mass. 0 = probe tip, values increase toward brain surface.",
    },
}

# Derived mappings for convenience (generated from master table)
# Only includes properties that come from clusters.metrics.pqt (excludes None ibl_names
# and properties that are loaded/set separately like probe_name, cluster_depths, peak_to_trough_duration_ms)
IBL_METRICS_TO_NWB = {
    v["ibl_name"]: k
    for k, v in UNITS_COLUMNS.items()
    if v["ibl_name"] is not None and v["ibl_name"] not in ("probe_name", "cluster_depths", "peak_to_trough_duration_ms")
}


class IblSortingInterface(BaseSortingExtractorInterface, BaseIBLDataInterface):
    """Interface for spike sorting data (revision-dependent processed data)."""

    # Spike sorting uses BWM standard revision for consistency across all sessions
    REVISION: str | None = "2025-05-06"

    Extractor = IblSortingExtractor

    @classmethod
    def get_extractor_class(cls):
        """Get the extractor class for this interface."""
        return cls.Extractor

    def __init__(
        self,
        session: str,
        one: ONE,
    ):
        # Create extractor but don't load data yet (fast initialization)
        self.sorting_extractor = self.Extractor(session=session, one=one, revision=self.REVISION)
        self.verbose = False
        self._number_of_segments = 1  # Will be set after loading

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare exact data files required for spike sorting.

        SpikeSortingLoader loads all spike/cluster files per probe.

        Parameters
        ----------
        **kwargs
            Accepts but ignores kwargs for API consistency with base class.

        Returns
        -------
        dict
            Data requirements for spike sorting
        """
        return {
            "one_objects": [],  # Uses SpikeSortingLoader abstraction
            "exact_files_options": {
                "standard": [
                    # Per-probe spike files
                    "alf/probe*/spikes.times.npy",
                    "alf/probe*/spikes.clusters.npy",
                    "alf/probe*/spikes.amps.npy",
                    "alf/probe*/spikes.depths.npy",
                    # Per-probe cluster files
                    "alf/probe*/clusters.channels.npy",
                    "alf/probe*/clusters.depths.npy",
                    "alf/probe*/clusters.metrics.pqt",
                    "alf/probe*/clusters.uuids.csv",
                    "alf/probe*/clusters.waveformsChannels.npy",
                    "alf/probe*/clusters.waveforms.npy",
                    "alf/probe*/clusters.peakToTrough.npy",
                ],
            },
        }

    @classmethod
    def download_data(
        cls,
        one: ONE,
        eid: str,
        download_only: bool = True,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Download spike sorting data using SpikeSortingLoader.

        NOTE: Uses class-level REVISION attribute automatically.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        download_only : bool, default=True
            If True, download but don't load into memory
        logger : logging.Logger, optional
            Logger for progress tracking

        Returns
        -------
        dict
            Download status
        """
        requirements = cls.get_data_requirements()

        # Use class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading spike sorting data (session {eid}, revision {revision})")

        start_time = time.time()

        # Get probe insertions from fixture (fast, no Alyx query)
        # NO fallback - if fixture is missing, installation is broken
        probe_name_to_probe_id_dict = get_probe_name_to_probe_id_dict(eid)

        if logger:
            logger.info(f"  Found {len(probe_name_to_probe_id_dict)} probe(s)")

        # SpikeSortingLoader.load_spike_sorting() downloads all spike/cluster files
        # NO try-except - let it fail if files missing
        for probe_name, pid in probe_name_to_probe_id_dict.items():
            if logger:
                logger.info(f"  Downloading spike sorting for probe {probe_name}")

            ssl = SpikeSortingLoader(one=one, eid=eid, pname=probe_name, pid=pid, revision=revision)
            ssl.load_spike_sorting()

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded spike sorting data for {len(probe_name_to_probe_id_dict)} probe(s) in {download_time:.2f}s")

        return {
            "success": True,
            "downloaded_objects": ["spike_sorting"],
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def _create_electrodes_table_with_localization(self, nwbfile: NWBFile) -> dict:
        """
        Create electrodes table with anatomical localization for processed mode.

        This method creates a minimal electrodes table when none exists (processed data mode),
        populating it with CCF coordinates and brain regions from IBL histology.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add electrodes to

        Returns
        -------
        dict
            Channel-to-electrode mapping: {probe_name: {channel_idx: electrode_idx}}
        """
        if nwbfile.electrodes is None or len(nwbfile.electrodes) == 0:
            raise RuntimeError("Electrodes table must be populated before adding sorting data.")

        channel_to_electrode_map = {}
        for probe_name in self.sorting_extractor.probe_names:
            group_name = get_ibl_probe_name(probe_name)
            electrode_indices = [
                index for index in range(len(nwbfile.electrodes))
                if nwbfile.electrodes['group_name'][index] == group_name
            ]
            if not electrode_indices:
                raise RuntimeError(f"No electrodes found for probe '{probe_name}'.")

            channel_to_electrode_map[probe_name] = {
                channel_idx: electrode_index
                for channel_idx, electrode_index in enumerate(sorted(electrode_indices))
            }

        return channel_to_electrode_map

    def _map_units_to_electrodes(self, nwbfile: NWBFile, channel_to_electrode_map: dict = None) -> tuple:
        """
        Map units to electrode indices based on waveform channels.

        Uses clusters.waveformsChannels for multi-electrode linking (all channels where
        the unit's waveform is stored). Also computes max_electrode from clusters.channels.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file containing the electrodes table
        channel_to_electrode_map : dict, optional
            Pre-computed channel-to-electrode mapping. If None, will compute from electrodes table.

        Returns
        -------
        tuple of (list of list of int, list of int)
            - unit_electrode_indices: For each unit, list of electrode indices from waveformsChannels
            - max_electrodes: For each unit, the electrode index with maximum amplitude
        """
        # Get unit properties from instance variables (set during data loading)
        unit_probe_names = self._unit_probe_names
        unit_max_channels = self._max_amplitude_channels
        unit_waveform_channels = self._waveform_channels

        # If no mapping provided, build it from electrodes table
        if channel_to_electrode_map is None:
            channel_to_electrode_map = {}
            for probe_name in self.sorting_extractor.probe_names:
                group_name = get_ibl_probe_name(probe_name)
                channel_to_electrode_map[probe_name] = {}

                electrode_idx = 0
                for index in range(len(nwbfile.electrodes)):
                    if nwbfile.electrodes['group_name'][index] == group_name:
                        # Channel index is position within this probe's electrodes
                        channel_idx = electrode_idx % 384  # Neuropixels has 384 channels
                        channel_to_electrode_map[probe_name][channel_idx] = index
                        electrode_idx += 1

        # Map each unit to its electrodes (from waveformsChannels) and max electrode
        unit_electrode_indices = []
        max_electrodes = []

        for probe_name, max_channel, waveform_channels in zip(
            unit_probe_names, unit_max_channels, unit_waveform_channels
        ):
            if probe_name not in channel_to_electrode_map:
                raise ValueError(f"Probe '{probe_name}' not found in electrode mapping")

            channel_map = channel_to_electrode_map[probe_name]

            # Map max amplitude channel to electrode index
            max_channel_index = int(max_channel)
            if max_channel_index not in channel_map:
                raise ValueError(
                    f"Max channel {max_channel_index} not found for {probe_name}. "
                    f"Available channels: {sorted(channel_map.keys())[:10]}{'...' if len(channel_map) > 10 else ''}"
                )
            max_electrodes.append(channel_map[max_channel_index])

            # Map waveform channels to electrode indices
            # waveform_channels is a list of channel indices from clusters.waveformsChannels
            if waveform_channels:
                electrode_indices = []
                for channel in waveform_channels:
                    channel_index = int(channel)
                    if channel_index in channel_map:
                        electrode_indices.append(channel_map[channel_index])
                unit_electrode_indices.append(electrode_indices)
            else:
                # If waveformsChannels not available, use empty list
                unit_electrode_indices.append([])

        return unit_electrode_indices, max_electrodes

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: DeepDict | None = None,
        stub_test: bool = False,
        stub_units: Optional[int] = None,
        write_as: Literal["units", "processing"] = "units",
        units_name: str = "units",
        units_description: str = (
            "Spike-sorted units from Neuropixels 1.0 probes. "
            "Spike sorting was performed using a Python implementation of Kilosort 2.5 (iblsorter, formerly pykilosort) "
            "with IBL-specific optimizations for drift correction and automated quality control. "
            "Unit quality is determined by three metrics: "
            "(1) refractory period violations using the slidingRP algorithm (Hill et al. 2011), "
            "(2) noise cutoff based on amplitude distribution, and "
            "(3) median spike amplitude threshold (>50 uV). "
            "The 'label' column indicates the proportion of metrics passed (1.0 = all passed, i.e. 'good' unit). "
            "Each unit includes brain region assignment from IBL's histology pipeline with Allen CCF coordinates. "
            "For methodology details, see the IBL spike sorting white paper: "
            "https://doi.org/10.6084/m9.figshare.19705522"
        ),
        unit_electrode_indices: list[list[int]] | None = None,
        skip_properties: list[str] | None = None,
    ):
        """
        Add IBL sorting data to NWBFile.

        This method automatically handles electrode table creation and unit-to-electrode linking:
        - If electrodes table doesn't exist: creates it with anatomical localization (processed mode)
        - If electrodes table exists: uses existing electrodes (raw mode)
        - Always links units to electrodes automatically based on maximum amplitude channels

        Parameters
        ----------
        nwbfile : NWBFile
            The NWBFile object to add sorting data to.
        metadata : DeepDict, optional
            Metadata dictionary for the NWB file.
        stub_test : bool, default: False
            If True, only load and process a subset of units for faster testing.
        stub_units : int, optional
            Number of units to load per probe when stub_test=True. Default is 10.
        write_as : {'units', 'processing'}, default: 'units'
            Where to write the units table.
        units_name : str, default: 'units'
            Name of the units table.
        units_description : str
            Description of the units table. Defaults to a detailed description of the
            IBL spike sorting pipeline including methodology and quality metrics.
        unit_electrode_indices : list of list of int, optional
            Electrode indices for each unit. If not provided, will be automatically
            calculated based on maximum amplitude channels.
        skip_properties : list of str, optional
            Properties to exclude from the units table. For IBL data, consider:
            skip_properties=["spike_amplitudes_uV", "spike_distances_from_probe_tip_um"]
            to reduce memory usage by ~10 GB for large sessions.

        Notes
        -----
        Memory optimization: Data is loaded only when this method is called,
        allowing for localized memory usage. The ragged properties "spike_amplitudes_uV"
        and "spike_distances_from_probe_tip_um" contain spike-level data that can use significant
        memory (~5 GB each for large sessions). Skipping these properties can
        reduce peak memory usage from ~23 GB to ~10-12 GB while preserving:
        - All spike times
        - All unit-level quality metrics
        - Brain region annotations
        - Mean spike amplitudes and depths (unit-level)
        """
        if skip_properties is None:
            skip_properties = []

        # Load IBL data if not already loaded
        if not self.sorting_extractor._data_loaded:
            # Determine which per-spike properties to skip
            skip_spike_amplitudes = "spike_amplitudes_volts" in skip_properties
            skip_spike_depths = "spike_distances_from_probe_tip_um" in skip_properties

            # Load raw IBL data
            ibl_data = self.sorting_extractor.load_ibl_data(
                stub_test=stub_test,
                stub_units=stub_units,
                skip_spike_amplitudes=skip_spike_amplitudes,
                skip_spike_depths=skip_spike_depths,
            )

            # Initialize the sorting extractor with spike times
            self.sorting_extractor.initialize_sorting(
                spike_times_by_id=ibl_data["spike_times_by_id"],
                cluster_ids=ibl_data["cluster_ids"],
            )

            # Set properties with NWB names (mapping from IBL names)
            cluster_ids = ibl_data["cluster_ids"]
            ibl_properties = ibl_data["unit_properties"]

            # Properties that need Volts -> microvolts conversion (multiply by 1e6)
            amplitude_properties = {"median_spike_amplitude_uV", "min_spike_amplitude_uV", "max_spike_amplitude_uV"}

            # Map IBL property names to NWB names and set on extractor
            for ibl_name, nwb_name in IBL_METRICS_TO_NWB.items():
                if ibl_name in ibl_properties:
                    values = np.array(ibl_properties[ibl_name])
                    # Convert spike_count to int (IBL stores as float in parquet)
                    # Use -1 as sentinel for missing values (NaN)
                    if nwb_name == "spike_count":
                        values = np.where(np.isnan(values), -1, values).astype(np.int64)
                    # Convert amplitude from Volts to microvolts
                    elif nwb_name in amplitude_properties:
                        values = values * 1e6
                    self.sorting_extractor.set_property(
                        key=nwb_name,
                        values=values,
                        ids=cluster_ids,
                    )

            # Set properties that don't need renaming
            # Convert probe_name to canonical format (Probe00, Probe01)
            canonical_probe_names = np.array([get_ibl_probe_name(pn) for pn in ibl_properties["probe_name"]])
            self.sorting_extractor.set_property(
                key="probe_name",
                values=canonical_probe_names,
                ids=cluster_ids,
            )
            self.sorting_extractor.set_property(
                key="distance_from_probe_tip_um",
                values=ibl_properties["cluster_depths"],
                ids=cluster_ids,
            )

            # Store max amplitude channel internally for electrode linking (not written to NWB)
            self._max_amplitude_channels = ibl_properties["_max_amplitude_channel"]
            self._unit_probe_names = ibl_properties["probe_name"]
            # Store waveform channels for multi-electrode linking
            self._waveform_channels = ibl_properties["_waveform_channels"]

            # Store waveform_mean separately - will be passed directly to add_sorting_to_nwbfile
            # to use NWB's predefined waveform_mean column (non-ragged 3D array)
            # Shape: (num_units, num_samples=82, num_channels=32)
            # Convert from Volts to microvolts for consistency with amplitude columns
            self._waveform_means = np.array(ibl_properties["waveform_mean"], dtype=np.float32) * 1e6

            # Set peak-to-trough duration
            self.sorting_extractor.set_property(
                key="peak_to_trough_duration_ms",
                values=np.array(ibl_properties["peak_to_trough_duration_ms"]),
                ids=cluster_ids,
            )

            # Set ragged array properties (per-spike data) if not skipped
            if ibl_data["spike_amplitudes_by_id"] is not None:
                # Convert from Volts to microvolts
                spike_amps_uV = [arr * 1e6 for arr in ibl_data["spike_amplitudes_by_id"].values()]
                self.sorting_extractor.set_property(
                    key="spike_amplitudes_uV",
                    values=np.array(spike_amps_uV, dtype=object),
                    ids=cluster_ids,
                )
            if ibl_data["spike_depths_by_id"] is not None:
                self.sorting_extractor.set_property(
                    key="spike_distances_from_probe_tip_um",
                    values=np.array(list(ibl_data["spike_depths_by_id"].values()), dtype=object),
                    ids=cluster_ids,
                )

        # Automatically create electrodes table if it doesn't exist (processed mode)
        channel_to_electrode_map = None
        if nwbfile.electrodes is None or len(nwbfile.electrodes) == 0:
            print("Creating electrodes table with anatomical localization (processed mode)...")
            channel_to_electrode_map = self._create_electrodes_table_with_localization(nwbfile)

        # Automatically link units to electrodes if not provided
        if unit_electrode_indices is None:
            print("Automatically linking units to electrodes based on waveform channels...")
            unit_electrode_indices, max_electrodes = self._map_units_to_electrodes(nwbfile, channel_to_electrode_map)

            # Set max_electrode property on the sorting extractor
            cluster_ids = list(self.sorting_extractor.get_unit_ids())
            self.sorting_extractor.set_property(
                key="max_electrode",
                values=np.array(max_electrodes),
                ids=cluster_ids,
            )

        # Build property descriptions from UNITS_COLUMNS
        property_descriptions = {
            name: spec["description"] for name, spec in UNITS_COLUMNS.items()
        }

        # Call add_sorting_to_nwbfile directly to pass waveform_means parameter
        # This uses NWB's predefined waveform_mean column correctly (non-ragged 3D array)
        add_sorting_to_nwbfile(
            self.sorting_extractor,
            nwbfile=nwbfile,
            property_descriptions=property_descriptions,
            write_as=write_as,
            units_name=units_name,
            units_description=units_description,
            unit_electrode_indices=unit_electrode_indices,
            waveform_means=self._waveform_means,
        )

        # Note: waveform_rate and resolution are set directly on the HDF5 file in the conversion
        # pipeline (processed.py) because neuroconv's configure_backend strips these attributes.
        # The values are: waveform_rate=30000.0 Hz, resolution=1/30000 seconds

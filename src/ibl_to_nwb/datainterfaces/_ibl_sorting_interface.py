"""The interface for loading spike sorted data via ONE access."""

from typing import Literal, Optional
import logging
import time

import numpy as np
from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import BaseSortingExtractorInterface
from neuroconv.utils import DeepDict
from one.api import ONE
from pynwb import NWBFile
from brainbox.io.one import SpikeSortingLoader

from ._ibl_sorting_extractor import IblSortingExtractor
from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures import get_probe_name_to_probe_id_dict

# Unit property descriptions for NWB metadata
# Order: Identification → Activity → Location → Quality Labels → Quality Metrics → Stability → Amplitude → Ragged Arrays
UNIT_PROPERTY_DESCRIPTIONS = {
    # Identification
    "probe_name": "Name of probe this unit was recorded from (e.g., 'probe00', 'probe01').",
    "cluster_uuid": "Globally unique identifier for cross-referencing with IBL database via ONE API.",
    # Core activity metrics
    "spike_count": "Total number of spikes assigned to this unit. Integer type; -1 indicates missing data.",
    "firing_rate": "Average firing rate in Hz.",
    # Location
    "mean_relative_depth_um": "Average depth of each unit along the probe in micrometers. 0 is deepest site.",
    # Quality labels (what users check first)
    "ibl_quality_score": "Proportion of IBL quality metrics passed (0.0, 0.33, 0.67, or 1.0). 1.0 = all three passed.",
    "kilosort2_label": "Original Kilosort2 classification: 'good', 'mua', or 'noise'.",
    # Quality metrics (detailed breakdown)
    "sliding_rp_violation": "Binary pass/fail (0.0 or 1.0) using sliding refractory period algorithm. Primary metric for ibl_quality_score. Aligns with SpikeInterface's sliding_rp_violations.",
    "isi_violations_ratio": "Ratio of observed to expected ISI violations (Steinmetz/cortex-lab method). Can exceed 1.0. Equivalent to SpikeInterface's isi_violations_ratio.",
    "rp_violation": "Contamination estimate using Hill et al. (2011) quadratic formula. Aligns with SpikeInterface's rp_violations.",
    "noise_cutoff": "Standard deviations the lower amplitude quartile deviates from expected. Large values indicate missed spikes at detection threshold.",
    "missed_spikes_estimate": "Estimated fraction of spikes missed due to detection threshold (0.0-1.0).",
    # Stability metrics
    "presence_ratio": "Fraction of time bins (60s default) with at least one spike. Good units typically >0.9.",
    "presence_ratio_std": "Standard deviation of spike counts across 10-second time bins.",
    "cumulative_drift_um_per_hour": "Sum of absolute depth changes between consecutive spikes, normalized to um/hour. Formula: sum(abs(diff(spike_depths)))/duration*3600. High values indicate either electrode drift or depth estimation noise. Scales with spike count (~0.79 correlation). NOT actual electrode displacement.",
    # Amplitude statistics
    "median_spike_amplitude_volts": "Median spike amplitude in Volts. IBL uses 50 uV (5e-5 V) threshold for quality filtering.",
    "min_spike_amplitude_volts": "Minimum spike amplitude in Volts.",
    "max_spike_amplitude_volts": "Maximum spike amplitude in Volts.",
    "spike_amplitude_std_dB": "Standard deviation of log-transformed spike amplitudes in decibels. High values (>6 dB) may indicate drift or contamination.",
    # Ragged arrays (per-spike data)
    "spike_amplitudes_volts": "Peak amplitude of each spike for each unit in Volts.",
    "spike_relative_depths_um": "Relative depth along the probe for each spike in micrometers, computed from waveform center of mass. 0 is deepest site.",
}

# Mapping from IBL clusters.metrics column names to NWB property names
# Only includes properties that come from clusters.metrics.pqt
IBL_METRICS_TO_NWB = {
    "cluster_uuid": "cluster_uuid",
    "spike_count": "spike_count",
    "firing_rate": "firing_rate",
    "label": "ibl_quality_score",
    "ks2_label": "kilosort2_label",
    "slidingRP_viol": "sliding_rp_violation",
    "contamination": "isi_violations_ratio",
    "contamination_alt": "rp_violation",
    "noise_cutoff": "noise_cutoff",
    "missed_spikes_est": "missed_spikes_estimate",
    "presence_ratio": "presence_ratio",
    "presence_ratio_std": "presence_ratio_std",
    "drift": "cumulative_drift_um_per_hour",
    "amp_median": "median_spike_amplitude_volts",
    "amp_min": "min_spike_amplitude_volts",
    "amp_max": "max_spike_amplitude_volts",
    "amp_std_dB": "spike_amplitude_std_dB",
}


def get_unit_property_descriptions() -> list[dict]:
    """Build the UnitProperties list for NWB metadata."""
    return [{"name": name, "description": desc} for name, desc in UNIT_PROPERTY_DESCRIPTIONS.items()]


def _format_probe_label(probe_name: str) -> str:
    """Return the standardized Neuropixels probe label (e.g., 'NeuropixelsProbe01')."""
    if probe_name.lower().startswith("probe"):
        suffix = probe_name[5:]
    else:
        suffix = probe_name
    return f"NeuropixelsProbe{suffix}"


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
            group_name = _format_probe_label(probe_name)
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

    def _map_units_to_electrodes(self, nwbfile: NWBFile, channel_to_electrode_map: dict = None) -> list:
        """
        Map units to electrode indices based on maximum amplitude channels.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file containing the electrodes table
        channel_to_electrode_map : dict, optional
            Pre-computed channel-to-electrode mapping. If None, will compute from electrodes table.

        Returns
        -------
        list of list of int
            For each unit, a list containing the electrode table index
        """
        # Get unit properties (use internal property for channel mapping)
        unit_probe_names = self.sorting_extractor.get_property("probe_name")
        unit_channel_ids = self.sorting_extractor.get_property("_max_amplitude_channel")

        # If no mapping provided, build it from electrodes table
        if channel_to_electrode_map is None:
            channel_to_electrode_map = {}
            for probe_name in self.sorting_extractor.probe_names:
                group_name = _format_probe_label(probe_name)
                channel_to_electrode_map[probe_name] = {}

                electrode_idx = 0
                for index in range(len(nwbfile.electrodes)):
                    if nwbfile.electrodes['group_name'][index] == group_name:
                        # Channel index is position within this probe's electrodes
                        channel_idx = electrode_idx % 384  # Neuropixels has 384 channels
                        channel_to_electrode_map[probe_name][channel_idx] = index
                        electrode_idx += 1

        # Map each unit to its electrode
        unit_electrode_indices = []
        for pname, channel_id in zip(unit_probe_names, unit_channel_ids):
            if pname not in channel_to_electrode_map:
                raise ValueError(f"Probe '{pname}' not found in electrode mapping")

            channel_map = channel_to_electrode_map[pname]
            channel_idx = int(channel_id)

            if channel_idx not in channel_map:
                raise ValueError(
                    f"Channel {channel_idx} not found for {pname}. "
                    f"Available channels: {sorted(channel_map.keys())[:10]}{'...' if len(channel_map) > 10 else ''}"
                )

            electrode_idx = channel_map[channel_idx]
            unit_electrode_indices.append([electrode_idx])

        return unit_electrode_indices

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
            skip_properties=["spike_amplitudes_volts", "spike_relative_depths_um"]
            to reduce memory usage by ~10 GB for large sessions.

        Notes
        -----
        Memory optimization: Data is loaded only when this method is called,
        allowing for localized memory usage. The ragged properties "spike_amplitudes_volts"
        and "spike_relative_depths_um" contain spike-level data that can use significant
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
            skip_spike_depths = "spike_relative_depths_um" in skip_properties

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

            # Map IBL property names to NWB names and set on extractor
            for ibl_name, nwb_name in IBL_METRICS_TO_NWB.items():
                if ibl_name in ibl_properties:
                    values = np.array(ibl_properties[ibl_name])
                    # Convert spike_count to int (IBL stores as float in parquet)
                    # Use -1 as sentinel for missing values (NaN)
                    if nwb_name == "spike_count":
                        values = np.where(np.isnan(values), -1, values).astype(np.int64)
                    self.sorting_extractor.set_property(
                        key=nwb_name,
                        values=values,
                        ids=cluster_ids,
                    )

            # Set properties that don't need renaming
            self.sorting_extractor.set_property(
                key="probe_name",
                values=ibl_properties["probe_name"],
                ids=cluster_ids,
            )
            self.sorting_extractor.set_property(
                key="_max_amplitude_channel",
                values=ibl_properties["_max_amplitude_channel"],
                ids=cluster_ids,
            )
            self.sorting_extractor.set_property(
                key="mean_relative_depth_um",
                values=ibl_properties["cluster_depths"],
                ids=cluster_ids,
            )

            # Set ragged array properties (per-spike data) if not skipped
            if ibl_data["spike_amplitudes_by_id"] is not None:
                self.sorting_extractor.set_property(
                    key="spike_amplitudes_volts",
                    values=np.array(list(ibl_data["spike_amplitudes_by_id"].values()), dtype=object),
                    ids=cluster_ids,
                )
            if ibl_data["spike_depths_by_id"] is not None:
                self.sorting_extractor.set_property(
                    key="spike_relative_depths_um",
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
            print("Automatically linking units to electrodes based on maximum amplitude channels...")
            unit_electrode_indices = self._map_units_to_electrodes(nwbfile, channel_to_electrode_map)

        # Build metadata with unit property descriptions
        # Descriptions are defined here to keep all sorting-related metadata together
        if metadata is None:
            metadata = DeepDict()
        if "Ecephys" not in metadata:
            metadata["Ecephys"] = {}
        metadata["Ecephys"]["UnitProperties"] = get_unit_property_descriptions()

        # Delegate to parent class (with stub_test=False since we already loaded/subsetted data)
        super().add_to_nwbfile(
            nwbfile=nwbfile,
            metadata=metadata,
            stub_test=False,
            write_as=write_as,
            units_name=units_name,
            units_description=units_description,
            unit_electrode_indices=unit_electrode_indices,
        )

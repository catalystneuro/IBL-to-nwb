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

# IBL metric to NWB property mapping with descriptions
# Key: IBL clusters.metrics column name
# Value: dict with "nwb_name" and "description" for NWB units table
IBL_PROPERTY_MAPPING = {
    # Amplitude metrics - IBL stores in Volts
    "amp_max": {
        "nwb_name": "amplitude_max_V",
        "description": "Maximum spike amplitude in Volts.",
    },
    "amp_min": {
        "nwb_name": "amplitude_min_V",
        "description": "Minimum spike amplitude in Volts.",
    },
    "amp_median": {
        "nwb_name": "amplitude_median_V",
        "description": "Median spike amplitude in Volts. IBL uses 50 uV (5e-5 V) threshold for quality filtering.",
    },
    "amp_std_dB": {
        "nwb_name": "amplitude_std_dB",
        "description": "Standard deviation of log-transformed spike amplitudes in decibels. High values (>6 dB) may indicate drift or contamination.",
    },
    # Contamination metrics - SpikeInterface-aligned names
    "contamination": {
        "nwb_name": "isi_violations_ratio",
        "description": "Ratio of observed to expected ISI violations (Steinmetz/cortex-lab method). Can exceed 1.0. Equivalent to SpikeInterface's isi_violations_ratio.",
    },
    "contamination_alt": {
        "nwb_name": "rp_violation",
        "description": "Contamination estimate using Hill et al. (2011) quadratic formula. Aligns with SpikeInterface's rp_violations.",
    },
    "slidingRP_viol": {
        "nwb_name": "sliding_rp_violation",
        "description": "Binary pass/fail (0.0 or 1.0) using sliding refractory period algorithm. Primary metric for ibl_quality_score. Aligns with SpikeInterface's sliding_rp_violations.",
    },
    # Other quality metrics
    "missed_spikes_est": {
        "nwb_name": "missed_spikes_estimate",
        "description": "Estimated fraction of spikes missed due to detection threshold (0.0-1.0).",
    },
    "noise_cutoff": {
        "nwb_name": "noise_cutoff",
        "description": "Standard deviations the lower amplitude quartile deviates from expected. Large values indicate missed spikes at detection threshold.",
    },
    # Activity metrics
    "presence_ratio": {
        "nwb_name": "presence_ratio",
        "description": "Fraction of time bins (60s default) with at least one spike. Good units typically >0.9.",
    },
    "presence_ratio_std": {
        "nwb_name": "presence_ratio_std",
        "description": "Standard deviation of spike counts across 10-second time bins.",
    },
    "drift": {
        "nwb_name": "drift_um_per_hour",
        "description": "Cumulative depth change rate in um/hour. Formula: sum(abs(diff(depths)))/duration*3600. NOT absolute drift.",
    },
    "spike_count": {
        "nwb_name": "spike_count",
        "description": "Total number of spikes assigned to this unit.",
    },
    "firing_rate": {
        "nwb_name": "firing_rate",
        "description": "Average firing rate in Hz.",
    },
    # Quality labels
    "label": {
        "nwb_name": "ibl_quality_score",
        "description": "Proportion of IBL quality metrics passed (0.0, 0.33, 0.67, or 1.0). 1.0 = all three passed.",
    },
    "ks2_label": {
        "nwb_name": "kilosort2_label",
        "description": "Original Kilosort2 classification: 'good', 'mua', or 'noise'.",
    },
    # Identification
    "cluster_uuid": {
        "nwb_name": "cluster_uuid",
        "description": "Globally unique identifier for cross-referencing with IBL database via ONE API.",
    },
}

# Additional properties not from clusters.metrics (ragged arrays and computed properties)
ADDITIONAL_PROPERTY_DESCRIPTIONS = {
    "spike_amplitudes_V": "Peak amplitude of each spike for each unit in Volts.",
    "spike_relative_depths_um": "Relative depth along the probe for each spike in micrometers, computed from waveform center of mass. 0 is deepest site.",
    "maximum_amplitude_channel": "Channel index with the largest waveform amplitude for each unit.",
    "mean_relative_depth_um": "Average depth of each unit along the probe in micrometers. 0 is deepest site.",
    "probe_name": "Name of probe this unit was recorded from (e.g., 'probe00', 'probe01').",
}


def get_unit_property_descriptions() -> list[dict]:
    """Build the UnitProperties list for NWB metadata from the mapping dictionaries."""
    descriptions = []
    # Add properties from IBL_PROPERTY_MAPPING
    for mapping in IBL_PROPERTY_MAPPING.values():
        descriptions.append({"name": mapping["nwb_name"], "description": mapping["description"]})
    # Add additional properties
    for name, description in ADDITIONAL_PROPERTY_DESCRIPTIONS.items():
        descriptions.append({"name": name, "description": description})
    return descriptions


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
        # Get unit properties
        unit_probe_names = self.sorting_extractor.get_property("probe_name")
        unit_channel_ids = self.sorting_extractor.get_property("maximum_amplitude_channel")

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
            skip_properties=["spike_amplitudes_uv", "spike_relative_depths_um"]
            to reduce memory usage by ~10 GB for large sessions.

        Notes
        -----
        Memory optimization: Data is loaded only when this method is called,
        allowing for localized memory usage. The ragged properties "spike_amplitudes_uv"
        and "spike_relative_depths_um" contain spike-level data that can use significant
        memory (~5 GB each for large sessions). Skipping these properties can
        reduce peak memory usage from ~23 GB to ~10-12 GB while preserving:
        - All spike times
        - All unit-level quality metrics
        - Brain region annotations
        - Mean spike amplitudes and depths (unit-level)
        """
        # Load and process spike data if not already loaded
        # skip_properties are not loaded/computed at all (memory optimization)
        if not self.sorting_extractor._data_loaded:
            self.sorting_extractor.load_and_process_data(
                ibl_property_mapping=IBL_PROPERTY_MAPPING,
                stub_test=stub_test,
                stub_units=stub_units,
                skip_properties=skip_properties,
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

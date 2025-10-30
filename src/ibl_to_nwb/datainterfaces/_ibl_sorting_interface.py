"""The interface for loading spike sorted data via ONE access."""

from copy import deepcopy
from pathlib import Path
from typing import Literal, Optional
import logging
import time

import numpy as np
from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import BaseSortingExtractorInterface
from neuroconv.utils import DeepDict, load_dict_from_file
from one.api import ONE
from pynwb import NWBFile
from brainbox.io.one import SpikeSortingLoader

from ._ibl_sorting_extractor import IblSortingExtractor
from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures import get_probe_name_to_probe_id_dict


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

    def get_metadata(self) -> dict:
        """
        Get metadata for NWB file.

        Returns
        -------
        dict
            Metadata dictionary.
        """
        metadata = super().get_metadata()

        ecephys_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "ecephys.yml")

        metadata.update(Ecephys=dict())
        metadata["Ecephys"].update(UnitProperties=ecephys_metadata["Ecephys"]["UnitProperties"])

        return metadata

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
        units_description: str = "Autogenerated by neuroconv.",
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
        units_description : str, default: 'Autogenerated by neuroconv.'
            Description of the units table.
        unit_electrode_indices : list of list of int, optional
            Electrode indices for each unit. If not provided, will be automatically
            calculated based on maximum amplitude channels.
        skip_properties : list of str, optional
            Properties to exclude from the units table. For IBL data, consider:
            skip_properties=["spike_amplitudes", "spike_relative_depths"]
            to reduce memory usage by ~10 GB for large sessions.

        Notes
        -----
        Memory optimization: Data is loaded only when this method is called,
        allowing for localized memory usage. The ragged properties "spike_amplitudes"
        and "spike_relative_depths" contain spike-level data that can use significant
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
                stub_test=stub_test, stub_units=stub_units, skip_properties=skip_properties
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

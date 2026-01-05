"""Interface for adding anatomical localization data using ndx-anatomical-localization extension."""

from typing import Optional
import logging
import time

import numpy as np
import pandas as pd
from brainbox.io.one import SpikeSortingLoader
from iblatlas.atlas import AllenAtlas
from iblatlas.regions import BrainRegions
from ndx_anatomical_localization import AnatomicalCoordinatesTable, Localization, Space, AllenCCFv3Space
from one.api import ONE
from pynwb import NWBFile

from ..utils.electrodes import convert_ibl_to_ccf3_coordinates, _ensure_ibl_coordinates_um
from ..utils.probe_naming import get_ibl_probe_name
from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures.load_fixtures import load_bwm_histology_qc, get_probe_name_to_probe_id_dict


class IblAnatomicalLocalizationInterface(BaseIBLDataInterface):
    """
    Interface for adding anatomical localization information to NWB files using the
    ndx-anatomical-localization extension.

    This interface:
    - Fetches histology data (channel coordinates and brain regions) from IBL
    - Creates Space objects for CCF and IBL-Bregma coordinate systems
    - Creates AnatomicalCoordinatesTable objects with electrode positions in both coordinate systems

    NOTE: The electrodes table must already exist
    """

    # Histology alignments use BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(
        self,
        one: ONE,
        eid: str,
        verbose: bool = False,
    ):
        """
        Initialize the anatomical localization interface.

        Parameters
        ----------
        one : ONE
            ONE API instance for data access
        eid : str
            Experiment/session ID
        verbose : bool, default: False
            Whether to print verbose output
        """
        super().__init__(verbose=verbose)
        self.one = one
        self.eid = eid
        self.revision = self.REVISION
        self.atlas = AllenAtlas()
        self.brain_regions = BrainRegions()

        # Load histology QC table from fixtures (committed to git)
        # NO fallback - if fixture is missing, installation is broken
        histology_qc_df = load_bwm_histology_qc()
        probe_name_to_probe_id_dict = get_probe_name_to_probe_id_dict(eid, histology_qc_df)

        # Load histology data for all probes
        self.probe_data = {}
        filtered_pname_pid: dict[str, str] = {}

        for pname, pid in probe_name_to_probe_id_dict.items():
            # Check histology quality from pre-computed table
            probe_qc = histology_qc_df[
                (histology_qc_df['eid'] == eid) &
                (histology_qc_df['probe_name'] == pname)
            ]

            if probe_qc.empty:
                raise ValueError(
                    f"Data integrity error: probe {pname} (pid={pid}) found in probe_name_to_probe_id_dict "
                    f"but not in histology QC table for session {eid}. This indicates corrupted fixture data."
                )

            probe_qc_row = probe_qc.iloc[0]
            histology_quality = probe_qc_row['histology_quality']
            has_files = probe_qc_row['has_histology_files']

            # Skip if no files or insufficient quality
            if not has_files or histology_quality != 'alf':
                if self.verbose:
                    print(f"Skipping {pname}: quality '{histology_quality}', has_files={has_files}")
                continue

            # Load spike sorting data to get channels
            ssl = SpikeSortingLoader(pid=pid, eid=eid, pname=pname, one=one, atlas=self.atlas)
            _, _, channels = ssl.load_spike_sorting(revision=self.revision)

            required_fields = {"x", "y", "z", "acronym"}
            missing_fields = required_fields - set(channels.keys())
            if missing_fields:
                raise ValueError(
                    f"Histology channels for probe '{pname}' are missing required fields: {sorted(missing_fields)}"
                )

            # Get trajectory and insertion information
            insertion = one.alyx.rest('insertions', 'read', id=pid)
            trajectories = one.alyx.rest(
                'trajectories', 'list',
                probe_insertion=pid,
                provenance='Ephys aligned histology track'
            )

            self.probe_data[pname] = {
                'pid': pid,
                'channels': channels,
                'histology_quality': histology_quality,
                'insertion': insertion,
                'trajectory': trajectories[0] if trajectories else None,
            }

            if self.verbose:
                print(f"Loaded histology for {pname} (quality: {histology_quality})")

            filtered_pname_pid[pname] = pid

        self.probe_name_to_probe_id_dict = filtered_pname_pid

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare data file patterns required for anatomical localization.

        Histology data is loaded via SpikeSortingLoader which fetches channel coordinates
        and brain regions. Additionally, SpikeGLX .meta files are required to determine
        electrode geometry for creating the electrode table.
        Only probes with histology quality 'alf' are included.

        Parameters
        ----------
        **kwargs
            Accepts but ignores kwargs for API consistency with base class.

        Returns
        -------
        dict
            Data requirements with generic file patterns
        """
        return {
            "one_objects": [],  # Uses SpikeSortingLoader abstraction
            "exact_files_options": {
                "standard": [
                    # Histology files (anatomical coordinates and brain regions)
                    "alf/probe*/channels.localCoordinates.npy",
                    "alf/probe*/channels.mlapdv.npy",
                    "alf/probe*/channels.brainLocationIds_ccf_2017.npy",
                    "alf/probe*/electrodeSites.localCoordinates.npy",
                    "alf/probe*/electrodeSites.mlapdv.npy",
                    "alf/probe*/electrodeSites.brainLocationIds_ccf_2017.npy",
                    # SpikeGLX metadata files (electrode geometry - required for electrode table)
                    "raw_ephys_data/probe*/_spikeglx_ephysData_g0_t0.imec*.ap.meta",
                ],
            },
            "quality_filter": "histology quality == 'alf'",
        }

    @classmethod
    def check_availability(
        cls,
        one: ONE,
        eid: str,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Check if anatomical localization data is available with quality filtering.

        Uses pre-computed histology QC fixture - NO data downloads, pure metadata lookup.

        Parameters
        ----------
        one : ONE
            ONE API instance (not used for BWM sessions - fixture-based)
        eid : str
            Session ID
        logger : logging.Logger, optional
            Logger for messages

        Returns
        -------
        dict
            Availability status with detailed breakdown per probe
        """

        # Load histology QC table from fixtures (committed to git)
        histology_qc_df = load_bwm_histology_qc()
        probe_name_to_probe_id_dict = get_probe_name_to_probe_id_dict(eid, histology_qc_df)

        available_probes = []
        unavailable_probes = []
        missing_files = []

        for pname, pid in probe_name_to_probe_id_dict.items():
            # Check histology quality from pre-computed table
            probe_qc = histology_qc_df[
                (histology_qc_df['eid'] == eid) &
                (histology_qc_df['probe_name'] == pname)
            ]

            if probe_qc.empty:
                raise ValueError(
                    f"Data integrity error: probe {pname} (pid={pid}) found in probe_name_to_probe_id_dict "
                    f"but not in histology QC table for session {eid}. This indicates corrupted fixture data."
                )

            probe_qc_row = probe_qc.iloc[0]
            histology_quality = probe_qc_row['histology_quality']
            has_files = probe_qc_row['has_histology_files']

            if not has_files:
                unavailable_probes.append(pname)
                missing_files.append(f"alf/{pname}/electrodeSites.*")
                if logger:
                    logger.debug(f"  Probe {pname}: no electrodeSites files")
                continue

            if histology_quality == 'alf':
                available_probes.append(pname)
                if logger:
                    logger.debug(f"  Probe {pname}: available (quality: {histology_quality})")
            else:
                unavailable_probes.append(pname)
                if logger:
                    logger.debug(f"  Probe {pname}: insufficient quality ({histology_quality})")

        is_available = len(available_probes) > 0

        return {
            "available": is_available,
            "available_probes": available_probes,
            "unavailable_probes": unavailable_probes,
            "missing_files": missing_files,
            "note": "Requires histology quality 'alf'",
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
        Download anatomical localization data with quality filtering.

        Uses histology QC fixture to filter probes, then checks file availability
        with list_datasets (not downloading) before actually downloading.

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
            Download status with list of probes downloaded
        """
        # Use class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading anatomical localization data (session {eid}, revision {revision})")

        start_time = time.time()

        # Load histology QC table from fixtures (committed to git)
        # NO fallback - if fixture is missing, installation is broken
        histology_qc_df = load_bwm_histology_qc()
        probe_name_to_probe_id_dict = get_probe_name_to_probe_id_dict(eid, histology_qc_df)

        downloaded_probes = []
        skipped_probes = []

        for pname, pid in probe_name_to_probe_id_dict.items():
            # Check histology quality from pre-computed table
            probe_qc = histology_qc_df[
                (histology_qc_df['eid'] == eid) &
                (histology_qc_df['probe_name'] == pname)
            ]

            if probe_qc.empty:
                raise ValueError(
                    f"Data integrity error: probe {pname} (pid={pid}) found in probe_name_to_probe_id_dict "
                    f"but not in histology QC table for session {eid}. This indicates corrupted fixture data."
                )

            probe_qc_row = probe_qc.iloc[0]
            histology_quality = probe_qc_row['histology_quality']
            has_files = probe_qc_row['has_histology_files']

            # Skip if no files or insufficient quality
            if not has_files:
                skipped_probes.append((pname, "no histology files"))
                if logger:
                    logger.info(f"  Skipping {pname}: no electrodeSites files")
                continue

            if histology_quality != 'alf':
                skipped_probes.append((pname, f"insufficient quality ({histology_quality})"))
                if logger:
                    logger.info(f"  Skipping {pname}: quality '{histology_quality}' not sufficient")
                continue

            # Download histology data via SpikeSortingLoader
            # NO try-except - let it fail if data missing or invalid
            if logger:
                logger.info(f"  Downloading histology for {pname} (quality: {histology_quality})")

            atlas = AllenAtlas()
            ssl = SpikeSortingLoader(pid=pid, eid=eid, pname=pname, one=one, atlas=atlas)
            ssl.load_spike_sorting(revision=revision)

            # Download SpikeGLX .meta file for electrode geometry
            # This is REQUIRED for creating the electrode table
            meta_collection = f"raw_ephys_data/{pname}"
            meta_datasets = [d for d in one.list_datasets(eid, collection=meta_collection) if d.endswith('.ap.meta')]
            if meta_datasets:
                # NO try-except - fail loudly if .meta file cannot be downloaded
                one.load_dataset(id=eid, dataset=meta_datasets[0], download_only=True)
                if logger:
                    logger.info(f"    Downloaded .meta file for {pname}")
            else:
                # Fail loudly - .meta file is required
                raise FileNotFoundError(
                    f"No .meta file found for probe {pname} in session {eid}. "
                    f"Collection: {meta_collection}"
                )

            downloaded_probes.append(pname)

        download_time = time.time() - start_time

        if logger:
            logger.info(
                f"  Downloaded histology for {len(downloaded_probes)} probe(s) in {download_time:.2f}s "
                f"({len(skipped_probes)} skipped)"
            )

        # Build list of downloaded files (specific probes that were downloaded)
        downloaded_files = []
        for pname in downloaded_probes:
            downloaded_files.extend([
                f"alf/{pname}/channels.localCoordinates.npy",
                f"alf/{pname}/channels.mlapdv.npy",
                f"alf/{pname}/channels.brainLocationIds_ccf_2017.npy",
                f"alf/{pname}/electrodeSites.localCoordinates.npy",
                f"alf/{pname}/electrodeSites.mlapdv.npy",
                f"alf/{pname}/electrodeSites.brainLocationIds_ccf_2017.npy",
                f"raw_ephys_data/{pname}/_spikeglx_ephysData_g0_t0.imec.ap.meta",
            ])

        return {
            "success": True,
            "downloaded_probes": downloaded_probes,
            "skipped_probes": skipped_probes,
            "downloaded_files": downloaded_files,
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: Optional[dict] = None):
        """
        Add anatomical localization data to the NWB file.

        This method ONLY adds AnatomicalCoordinatesTable objects linking electrodes
        to IBL-Bregma and CCF coordinate systems. The electrodes table must already
        exist with anatomical columns populated (done by IblSpikeGlxConverter or
        IblSortingInterface).

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add data to
        metadata : dict, optional
            Metadata dictionary (not currently used)

        Raises
        ------
        ValueError
            If electrodes table doesn't exist or is missing required columns
        """
        # Check that electrodes table exists
        if nwbfile.electrodes is None or len(nwbfile.electrodes) == 0:
            raise ValueError(
                "Electrodes table is empty or doesn't exist. "
                "Populate the electrodes table first (e.g., via add_probe_electrodes_with_localization "
                "in the raw pipeline or IblSortingInterface in the processed pipeline) "
                "before running the anatomical localization interface."
            )

        # Check that required columns exist in electrodes table
        required_columns = ['x', 'y', 'z', 'location']
        missing = [col for col in required_columns if col not in nwbfile.electrodes.colnames]
        if missing:
            raise ValueError(
                f"Electrodes table is missing required anatomical columns: {missing}. "
                "IblSpikeGlxConverter or IblSortingInterface should have populated these columns."
            )

        if not self.probe_data:
            if self.verbose:
                print("No probe data with sufficient histology quality to add")
            return

        # Create or get the Localization container using dict.get
        localization = nwbfile.lab_meta_data.get('localization')
        if localization is None:
            localization = Localization()
            nwbfile.add_lab_meta_data(localization)

        # Create coordinate space objects
        self.ccf_space = AllenCCFv3Space(name="AllenCCFv3")

        self.ibl_space = Space(
            name="IBLBregma",
            space_name="IBLBregma",
            origin="bregma",
            units="um",
            orientation="RAS",
        )
        if self.ibl_space.name not in localization.spaces:
            localization.add_spaces(spaces=[self.ibl_space])
        if self.ccf_space.name not in localization.spaces:
            localization.add_spaces(spaces=[self.ccf_space])

        brain_regions = BrainRegions()

        # Create single merged IBL-Bregma table for all probes
        ibl_table = AnatomicalCoordinatesTable(
            name="ElectrodesIBLBregma",
            description='Electrode positions in the IBL-Bregma coordinate system',
            target=nwbfile.electrodes,
            space=self.ibl_space,
            method='IBL histology alignment pipeline',
        )
        # Add probe_name column to identify which probe each electrode belongs to
        ibl_table.add_column(
            name='probe_name',
            description='IBL probe name in canonical format (e.g., Probe00, Probe01).',
        )
        # Add custom columns for hierarchical brain region mappings and atlas ID
        ibl_table.add_column(
            name='atlas_id',
            description='Allen Brain Atlas region ID. Negative values indicate left hemisphere, positive values indicate right hemisphere.',
        )
        ibl_table.add_column(
            name='beryl_location',
            description='Brain region in IBL Beryl atlas (coarse grouping).',
        )
        ibl_table.add_column(
            name='cosmos_location',
            description='Brain region in IBL Cosmos atlas (very coarse grouping).',
        )

        # Create single merged CCF table for all probes
        ccf_table = AnatomicalCoordinatesTable(
            name='ElectrodesCCFv3',
            description='Electrode positions in the Allen CCF coordinate system',
            target=nwbfile.electrodes,
            space=self.ccf_space,
            method='IBL histology alignment pipeline',
        )
        # Add probe_name column to identify which probe each electrode belongs to
        ccf_table.add_column(
            name='probe_name',
            description='IBL probe name in canonical format (e.g., Probe00, Probe01).',
        )

        # Build mapping of electrode_index -> row_index for units linking
        electrode_to_row_index = {}

        for probe_name, data in self.probe_data.items():
            canonical_name = get_ibl_probe_name(probe_name)

            channels = data['channels']
            channels_x = np.asarray(channels["x"], dtype=np.float64)
            channels_y = np.asarray(channels["y"], dtype=np.float64)
            channels_z = np.asarray(channels["z"], dtype=np.float64)
            acronyms = np.asarray(channels["acronym"]).astype(str)

            # Get atlas IDs for hierarchical region mappings
            atlas_ids = np.asarray(channels["atlas_id"])
            beryl_locations = brain_regions.id2acronym(atlas_id=atlas_ids, mapping="Beryl")
            cosmos_locations = brain_regions.id2acronym(atlas_id=atlas_ids, mapping="Cosmos")

            n_channels = len(channels_x)

            # Get electrode indices for this probe
            electrode_indices = []
            # IBL naming convention for electrode groups
            ibl_group_name = get_ibl_probe_name(probe_name)

            # Use NeuroConv's global ID matching system
            for index in range(len(nwbfile.electrodes)):
                if nwbfile.electrodes['group_name'][index] == ibl_group_name:
                    electrode_indices.append(index)

            ibl_coords_um, _ = _ensure_ibl_coordinates_um(channels_x, channels_y, channels_z)
            ccf_result = convert_ibl_to_ccf3_coordinates(
                atlas=self.atlas,
                x=channels_x,
                y=channels_y,
                z=channels_z,
                acronyms=acronyms,
                probe_name=probe_name,
                eid=self.eid,
            )
            ibl_x_um = ibl_coords_um[:, 0]
            ibl_y_um = ibl_coords_um[:, 1]
            ibl_z_um = ibl_coords_um[:, 2]
            ccf_coords_x_um = ccf_result['coords_um'][:, 0]
            ccf_coords_y_um = ccf_result['coords_um'][:, 1]
            ccf_coords_z_um = ccf_result['coords_um'][:, 2]

            # Map electrode index to channel index using modulo
            for electrode_index in electrode_indices:
                channel_index = electrode_index % n_channels

                # Store mapping for units linking (row index in the merged table)
                row_index = len(ccf_table)
                electrode_to_row_index[electrode_index] = row_index

                # Add rows to merged AnatomicalCoordinatesTables
                # Use acronym for brain_region in the tables (standard identifier)
                acronym_value = ccf_result['acronym'][channel_index]

                ibl_table.add_row(
                    localized_entity=electrode_index,
                    probe_name=canonical_name,
                    x=float(ibl_x_um[channel_index]),
                    y=float(ibl_y_um[channel_index]),
                    z=float(ibl_z_um[channel_index]),
                    brain_region=acronym_value,
                    atlas_id=int(atlas_ids[channel_index]),
                    beryl_location=str(beryl_locations[channel_index]),
                    cosmos_location=str(cosmos_locations[channel_index]),
                )

                ccf_table.add_row(
                    localized_entity=electrode_index,
                    probe_name=canonical_name,
                    x=float(ccf_coords_x_um[channel_index]),
                    y=float(ccf_coords_y_um[channel_index]),
                    z=float(ccf_coords_z_um[channel_index]),
                    brain_region=acronym_value,
                )

        # Validate that tables were populated
        if len(ibl_table) == 0 or len(ccf_table) == 0:
            raise ValueError(
                "Failed to create anatomical coordinates tables. "
                "Ensure probe data contains histology information."
            )

        # Add both tables to localization
        localization.add_anatomical_coordinates_tables([ibl_table, ccf_table])

        # TEMPORARILY DISABLED: Units table links to AnatomicalCoordinatesTable
        # The pynwb validator (v3.1.3) incorrectly rejects DynamicTableRegion references
        # to DynamicTable subclasses like AnatomicalCoordinatesTable, even though the
        # schema correctly defines inheritance (neurodata_type_inc: DynamicTable).
        #
        # Error: "incorrect data_type - expected 'DynamicTable', got 'AnatomicalCoordinatesTable'"
        #
        # See: build/pynwb_validation_issue.md for reproducible example
        # TODO: Re-enable once pynwb/hdmf fixes this validation bug
        #
        # The AnatomicalCoordinatesTable objects are still added to the file and can be
        # accessed via nwbfile.lab_meta_data['localization'].anatomical_coordinates_tables
        # Users can manually correlate units to electrodes using the existing columns.

        # # Add anatomical coordinates links to units table (if units exist)
        # # Units inherit coordinates from their max-amplitude electrode
        # # Skip if units table doesn't exist (e.g., in raw-only conversion)
        # if nwbfile.units is None or len(nwbfile.units) == 0:
        #     if self.verbose:
        #         print("Units table not present - skipping units anatomical coordinates columns")
        #     return
        #
        # if 'ccf_anatomical_coordinates' in nwbfile.units.colnames:
        #     raise ValueError("ccf_anatomical_coordinates column already exists in units table")
        # if 'ibl_bregma_centered_coordinates' in nwbfile.units.colnames:
        #     raise ValueError("ibl_bregma_centered_coordinates column already exists in units table")
        #
        # # Build row indices for each unit (works for all sessions - single and multi-probe)
        # # Use max_electrode column which contains the electrode with maximum spike amplitude
        # # max_electrode is a DynamicTableRegion linking to the electrodes table
        # row_indices = []
        # for unit_index in range(len(nwbfile.units)):
        #     # Access the DynamicTableRegion to get the electrode data (returns DataFrame)
        #     electrode_row = nwbfile.units['max_electrode'][unit_index]
        #     # The DataFrame index contains the electrode index from the electrodes table
        #     max_amp_electrode_index = int(electrode_row.index[0])
        #     row_index = electrode_to_row_index[max_amp_electrode_index]
        #     row_indices.append(row_index)
        #
        # # For non-ragged data (each unit has exactly 1 reference), create cumulative index
        # # Index[i] indicates the end position (exclusive) of unit i's references in the data array
        # # For non-ragged: index = [1, 2, 3, ..., n_units]
        # index = np.arange(1, len(nwbfile.units) + 1, dtype=np.uint32)
        #
        # # Add CCF anatomical coordinates column with VectorIndex for schema compliance
        # nwbfile.units.add_column(
        #     name='ccf_anatomical_coordinates',
        #     description=(
        #         'Link to the ElectrodesCCFv3 AnatomicalCoordinatesTable row containing '
        #         'Allen CCF coordinates and brain region for this unit. Links to the CCF localization '
        #         "of the unit's maximum amplitude electrode. Provides access to formal Space "
        #         'metadata, CCF coordinates, and hierarchical brain region mappings.'
        #     ),
        #     data=row_indices,
        #     table=ccf_table,
        #     index=index,
        # )
        #
        # # Add IBL Bregma-centered coordinates column (same indices, different table)
        # nwbfile.units.add_column(
        #     name='ibl_bregma_centered_coordinates',
        #     description=(
        #         'Link to the ElectrodesIBLBregma AnatomicalCoordinatesTable row containing '
        #         'IBL Bregma-centered coordinates and hierarchical brain region mappings for this unit. '
        #         "Links to the localization of the unit's maximum amplitude electrode. Provides access "
        #         'to atlas_id, Beryl brain regions, and Cosmos brain regions.'
        #     ),
        #     data=row_indices,
        #     table=ibl_table,
        #     index=index,
        # )

    @staticmethod
    def _probe_has_histology_files(one: ONE, eid: str, probe_name: str, revision: Optional[str]) -> bool:
        collection = f"alf/{probe_name}"
        datasets = set(one.list_datasets(eid, collection=collection))
        if revision:
            datasets.update(one.list_datasets(eid, collection=collection, revision=revision))
        return any("electrodeSites" in dataset for dataset in datasets)

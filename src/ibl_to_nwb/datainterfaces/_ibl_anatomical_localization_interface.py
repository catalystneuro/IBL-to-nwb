"""Interface for adding anatomical localization data using ndx-anatomical-localization extension."""

from typing import Optional

import numpy as np
from brainbox.io.one import SpikeSortingLoader
from iblatlas.atlas import AllenAtlas
from iblatlas.regions import BrainRegions
from neuroconv.basedatainterface import BaseDataInterface
from ndx_anatomical_localization import AnatomicalCoordinatesTable, Localization, Space
from one.api import ONE
from pynwb import NWBFile
from pynwb.device import Device


def _format_probe_label(probe_name: str) -> str:
    """Return the standardized Neuropixels probe label (e.g., 'NeuropixelsProbe01')."""
    if probe_name.lower().startswith("probe"):
        suffix = probe_name[5:]
    else:
        suffix = probe_name
    return f"NeuropixelsProbe{suffix}"


class IblAnatomicalLocalizationInterface(BaseDataInterface):
    """
    Interface for adding anatomical localization information to NWB files using the
    ndx-anatomical-localization extension.

    This interface:
    - Fetches histology data (channel coordinates and brain regions) from IBL
    - Creates Space objects for CCF and IBL-Bregma coordinate systems
    - Creates AnatomicalCoordinatesTable objects with electrode positions in both coordinate systems

    NOTE: This interface does NOT modify the electrodes table. The electrodes table must already
    exist with anatomical localization populated by either IblSpikeGlxConverter (raw mode) or
    IblSortingInterface (processed mode).
    """

    def __init__(
        self,
        one: ONE,
        eid: str,
        pname_pid_map: dict,
        revision: Optional[str] = None,
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
        pname_pid_map : dict
            Mapping from probe names (e.g., 'probe00') to probe insertion IDs (PIDs)
        revision : str, optional
            Data revision to use
        verbose : bool, default: False
            Whether to print verbose output
        """
        super().__init__(verbose=verbose)
        self.one = one
        self.eid = eid
        self.pname_pid_map = pname_pid_map
        self.revision = revision
        self.atlas = AllenAtlas()
        self.brain_regions = BrainRegions()

        # Load histology data for all probes
        self.probe_data = {}
        for pname, pid in pname_pid_map.items():
            ssl = SpikeSortingLoader(pid=pid, eid=eid, pname=pname, one=one, atlas=self.atlas)

            # Load spike sorting to get channels data
            _, _, channels = ssl.load_spike_sorting(revision=revision)

            # Check histology quality - if ssl.histology is empty, check insertion directly
            histology_quality = ssl.histology
            if not histology_quality:
                # Fallback: check insertion extended_qc directly
                insertion = one.alyx.rest('insertions', 'read', id=pid)
                extended_qc = insertion.get('json', {}).get('extended_qc', {})
                if extended_qc.get('tracing_exists') and extended_qc.get('alignment_resolved'):
                    histology_quality = 'resolved'
                elif extended_qc.get('alignment_count', 0) > 0:
                    histology_quality = 'aligned'
            else:
                insertion = None  # Will be loaded later if needed

            # Only include probes with high-quality histology
            if histology_quality in ['alf', 'resolved']:
                # Get trajectory information
                if insertion is None:
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
            else:
                if self.verbose:
                    print(f"Skipping {pname}: histology quality '{histology_quality}' not sufficient")

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
                "IblSpikeGlxConverter (raw mode) or IblSortingInterface (processed mode) "
                "must be run first to create the electrodes table with anatomical localization."
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
        self.ccf_space = Space(
            name="CCFv3_space",
            space_name="CCFv3",
            origin="corner (0,0,0) of the Allen CCF atlas volume",
            units="um",
            orientation="RAS",  # Right-Anterior-Superior
        )

        self.ibl_space = Space(
            name="IBL_Bregma_space",
            space_name="IBL_Bregma",
            origin="bregma",
            units="um",
            orientation="RAS",
        )
        if self.ibl_space.name not in localization.spaces:
            localization.add_spaces(spaces=[self.ibl_space])
        if self.ccf_space.name not in localization.spaces:
            localization.add_spaces(spaces=[self.ccf_space])


        # Create AnatomicalCoordinatesTable for IBL-Bregma coordinates
        ibl_table = AnatomicalCoordinatesTable(
            name=f"AnatomicalCoordinatesTableElectrodesIBLBregma",
            description=f'Electrode positions for in the IBL-Bregma coordinate system',
            target=nwbfile.electrodes,
            space=self.ibl_space,
            method='IBL histology alignment pipeline',
        )

        # Create AnatomicalCoordinatesTable for CCF coordinates
        ccf_table = AnatomicalCoordinatesTable(
            name=f'AnatomicalCoordinatesTableElectrodesCCFv3',
            description=f'Electrode positions in the CCF coordinate system',
            target=nwbfile.electrodes,
            space=self.ccf_space,
            method='IBL histology alignment pipeline',
        )

        for pname, data in self.probe_data.items():
            channels = data['channels']
            n_channels = len(channels['x'])

            # Get electrode indices for this probe
            electrode_indices = []
            # IBL naming convention for electrode groups
            ibl_group_name = _format_probe_label(pname)

            # Use NeuroConv's global ID matching system
            for index in range(len(nwbfile.electrodes)):
                if nwbfile.electrodes['group_name'][index] == ibl_group_name:
                    electrode_indices.append(index)

            # Convert IBL coordinates (meters) to micrometers
            # Ensure float64 dtype for proper NWB serialization
            ibl_x_um = np.array(channels['x'], dtype=np.float64) * 1e6
            ibl_y_um = np.array(channels['y'], dtype=np.float64) * 1e6
            ibl_z_um = np.array(channels['z'], dtype=np.float64) * 1e6

            # Convert to CCF coordinates
            ibl_coords_m = np.column_stack([channels['x'], channels['y'], channels['z']])
            ccf_coords_um = self.atlas.xyz2ccf(ibl_coords_m)
            # Ensure float64 dtype for proper NWB serialization
            ccf_coords_x_um = np.array(ccf_coords_um[:, 0], dtype=np.float64)
            ccf_coords_y_um = np.array(ccf_coords_um[:, 1], dtype=np.float64)
            ccf_coords_z_um = np.array(ccf_coords_um[:, 2], dtype=np.float64)

            # The electrode indices may include duplicates for AP and LF bands
            # Map electrode index to channel index using modulo
            for electrode_index in electrode_indices:
                channel_index = electrode_index % n_channels

                # Add rows to AnatomicalCoordinatesTable (ONLY - no longer modifying electrodes table)
                # Ensure all values are scalar float64 for proper NWB serialization
                ibl_table.add_row(
                    localized_entity=electrode_index,
                    x=float(ibl_x_um[channel_index]),
                    y=float(ibl_y_um[channel_index]),
                    z=float(ibl_z_um[channel_index]),
                    brain_region=str(channels['acronym'][channel_index]),
                )

                ccf_table.add_row(
                    localized_entity=electrode_index,
                    x=float(ccf_coords_x_um[channel_index]),
                    y=float(ccf_coords_y_um[channel_index]),
                    z=float(ccf_coords_z_um[channel_index]),
                    brain_region=str(channels['acronym'][channel_index]),
                )

        # Add tables to localization
        localization.add_anatomical_coordinates_tables([ibl_table, ccf_table])

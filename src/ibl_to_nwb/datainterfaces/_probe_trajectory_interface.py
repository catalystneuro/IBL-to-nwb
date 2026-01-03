"""Interface for IBL probe trajectory data (insertion geometry)."""

from __future__ import annotations

import logging
import math
from typing import Optional

from ndx_ibl import IblProbeInsertionTrajectoryTable, IblProbeInsertionTrajectories
from one.api import ONE
from pynwb import NWBFile

from ._base_ibl_interface import BaseIBLDataInterface
from ..utils.probe_naming import get_ibl_probe_name


class ProbeTrajectoryInterface(BaseIBLDataInterface):
    """
    Interface for probe insertion trajectory data.

    This interface fetches probe trajectory information from the Alyx database,
    including entry point coordinates (x, y, z), insertion angles (theta, phi),
    depth, and roll. Multiple provenance levels may exist for each probe:

    - Planned: Pre-surgical target coordinates
    - Micro-manipulator: Recorded from stereotaxic manipulator during surgery
    - Histology track: Traced from post-mortem brain slices
    - Ephys aligned histology track: Histology refined using electrophysiology

    The data is stored in a ProbeTrajectoryTable (from ndx-ibl) as
    lab metadata, since it describes experimental setup/methodology.
    """

    # Trajectory data comes from Alyx REST API, not revision-tagged files
    REVISION: str | None = None

    def __init__(
        self,
        one: ONE,
        eid: str,
        probe_name_to_probe_id_dict: dict[str, str],
    ):
        """
        Initialize the ProbeTrajectoryInterface.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Experiment ID (session UUID)
        probe_name_to_probe_id_dict : dict[str, str]
            Mapping of probe names (e.g., 'probe00') to probe insertion IDs (PIDs)
        """
        self.one = one
        self.eid = eid
        self.probe_name_to_probe_id_dict = probe_name_to_probe_id_dict

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Declare data requirements for probe trajectories.

        Trajectory data comes from Alyx REST API (trajectories endpoint),
        not from file downloads. This interface requires probe insertion IDs
        which are obtained from the anatomical localization interface.

        Returns
        -------
        dict
            Data requirements specification
        """
        return {
            "one_objects": [],  # Uses Alyx REST API, not ONE objects
            "exact_files_options": {
                # No files required - data comes from Alyx REST API
                # We use a special marker to indicate API-based data
                "alyx_api": [],
            },
            "notes": "Data fetched from Alyx REST API: /trajectories endpoint",
        }

    @classmethod
    def check_availability(
        cls,
        one: ONE,
        eid: str,
        probe_name_to_probe_id_dict: dict[str, str] | None = None,
        logger: Optional[logging.Logger] = None,
        **kwargs,
    ) -> dict:
        """
        Check if trajectory data is available for the given probes.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID (experiment ID)
        probe_name_to_probe_id_dict : dict, optional
            Mapping of probe names to probe insertion IDs. If not provided,
            will attempt to get insertions for the session.
        logger : logging.Logger, optional
            Logger for progress/warning messages

        Returns
        -------
        dict
            Availability status including found trajectories
        """
        if probe_name_to_probe_id_dict is None:
            # Try to get insertions for the session
            try:
                insertions = one.alyx.rest("insertions", "list", session=eid)
                probe_name_to_probe_id_dict = {ins["name"]: ins["id"] for ins in insertions}
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to fetch insertions for session {eid}: {e}")
                return {
                    "available": False,
                    "missing_required": ["probe insertions"],
                    "found_files": [],
                    "alternative_used": None,
                    "requirements": cls.get_data_requirements(),
                }

        if not probe_name_to_probe_id_dict:
            return {
                "available": False,
                "missing_required": ["probe insertions"],
                "found_files": [],
                "alternative_used": None,
                "requirements": cls.get_data_requirements(),
            }

        # Check if any trajectories exist
        trajectories_found = []
        for probe_name, pid in probe_name_to_probe_id_dict.items():
            try:
                trajectories = one.alyx.rest("trajectories", "list", probe_insertion=pid)
                if trajectories:
                    trajectories_found.extend(
                        [f"{probe_name}:{traj['provenance']}" for traj in trajectories]
                    )
            except Exception:
                continue

        return {
            "available": len(trajectories_found) > 0,
            "missing_required": [] if trajectories_found else ["trajectories"],
            "found_files": trajectories_found,
            "alternative_used": "alyx_api",
            "requirements": cls.get_data_requirements(),
        }

    @classmethod
    def download_data(
        cls,
        one: ONE,
        eid: str,
        download_only: bool = True,
        logger: Optional[logging.Logger] = None,
        **kwargs,
    ) -> dict:
        """
        No download needed - data comes from Alyx REST API.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        download_only : bool, default=True
            Ignored for this interface
        logger : logging.Logger, optional
            Logger for progress tracking

        Returns
        -------
        dict
            Status indicating no download needed
        """
        if logger:
            logger.info(f"ProbeTrajectoryInterface: No download needed (data from Alyx API)")

        return {
            "success": True,
            "downloaded_objects": [],
            "downloaded_files": [],
            "already_cached": [],
            "alternative_used": "alyx_api",
            "data": None,
        }

    def _get_device_for_probe(self, nwbfile: NWBFile, probe_name: str):
        """
        Find the Device object corresponding to a probe name.

        Looks for devices with names matching common patterns:
        - "probe00" -> "Probe00" (canonical IBL format)
        - Also checks electrode groups which reference devices

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file containing devices
        probe_name : str
            The probe name (e.g., "probe00")

        Returns
        -------
        Device or None
            The Device object if found, None otherwise
        """
        # Try canonical name first (Probe00, Probe01)
        canonical_name = get_ibl_probe_name(probe_name)
        if canonical_name in nwbfile.devices:
            return nwbfile.devices[canonical_name]

        # Try direct match (lowercase probe00)
        if probe_name in nwbfile.devices:
            return nwbfile.devices[probe_name]

        # Try via electrode groups (each group has a device reference)
        if canonical_name in nwbfile.electrode_groups:
            return nwbfile.electrode_groups[canonical_name].device

        return None

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: dict,
        **kwargs,
    ) -> None:
        """
        Add probe trajectory tables to the NWB file.

        Fetches trajectory data from Alyx and creates one ProbeTrajectoryTable
        per probe, stored in a ProbeTrajectories container as lab metadata.
        Each row links to the actual Device object in the NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to add the trajectory tables to
        metadata : dict
            Metadata dictionary (unused but required by interface contract)
        """
        if not self.probe_name_to_probe_id_dict:
            return

        # Create one table per probe
        trajectory_tables = []
        for probe_name, pid in self.probe_name_to_probe_id_dict.items():
            try:
                trajectories = self.one.alyx.rest("trajectories", "list", probe_insertion=pid)
            except Exception:
                continue

            if not trajectories:
                continue

            # Get the Device object for this probe
            device = self._get_device_for_probe(nwbfile, probe_name)
            if device is None:
                # Skip if no device found - can't create proper device reference
                continue

            # Create table for this probe
            # Use canonical name like "Probe00", "Probe01" - nesting in ProbeInsertionTrajectories provides context
            canonical_name = get_ibl_probe_name(probe_name)
            trajectory_table = IblProbeInsertionTrajectoryTable(
                name=canonical_name,
                description=(
                    f"Probe insertion trajectory parameters for {probe_name}. Each row represents a "
                    "trajectory estimate from a different provenance level, progressing from theoretical "
                    "to validated: Planned (pre-surgical target), Micro-manipulator (recorded during "
                    "surgery), Histology track (traced from post-mortem brain slices), and Ephys aligned "
                    "histology track (histology refined using electrophysiology). "
                    "Insertion point coordinates (ml, ap, dv) are bregma-centered with units in micrometers: "
                    "ml is medio-lateral (positive=right), ap is anterior-posterior (positive=anterior), "
                    "dv is dorso-ventral (positive=dorsal). "
                    "Angles characterize the spatial orientation of the probe: "
                    "theta is polar angle from vertical (0=straight down into brain, 90=horizontal), "
                    "phi is azimuth angle from the AP axis (0=tilted anteriorly, 90=tilted left, 180=posteriorly), "
                    "roll defines the electrode-facing direction (rotation around probe axis). "
                    "Depth is the insertion distance along the probe axis from the brain surface entry point "
                    "to the probe tip."
                ),
            )

            for traj in trajectories:
                # Extract trajectory parameters, using NaN for missing numeric values
                trajectory_table.add_row(
                    device=device,
                    pid=pid,
                    trajectory_source=traj.get("provenance", ""),
                    ml=float(traj["x"]) if traj.get("x") is not None else math.nan,
                    ap=float(traj["y"]) if traj.get("y") is not None else math.nan,
                    dv=float(traj["z"]) if traj.get("z") is not None else math.nan,
                    depth_um=float(traj["depth"]) if traj.get("depth") is not None else math.nan,
                    theta=float(traj["theta"]) if traj.get("theta") is not None else math.nan,
                    phi=float(traj["phi"]) if traj.get("phi") is not None else math.nan,
                    roll=float(traj["roll"]) if traj.get("roll") is not None else math.nan,
                )

            trajectory_tables.append(trajectory_table)

        if not trajectory_tables:
            return

        # Wrap tables in LabMetaData container and add to nwbfile
        # Note: IblProbeInsertionTrajectories has a fixed name in the spec, so we don't pass name=
        probe_trajectories = IblProbeInsertionTrajectories(
            ibl_probe_insertion_trajectory_tables=trajectory_tables
        )
        nwbfile.add_lab_meta_data(probe_trajectories)

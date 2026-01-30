"""
Converter for IBL Neuropixels 2.0 multi-shank recordings.

This converter handles IBL's specific data organization where each shank of a
Neuropixels 2.0 multi-shank probe is stored in a separate compressed file.
Standard SpikeGLX recordings store all shanks in a single file, but IBL splits
the data during preprocessing for parallel processing and storage efficiency.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from neuroconv.nwbconverter import ConverterPipe
from one.api import ONE
from pynwb import NWBFile

from ..datainterfaces._ibl_neuropixels2_shank_interface import IblNeuropixels2ShankInterface
from ..utils.probe_naming import get_ibl_probe_name


class IblNeuropixels2Converter(ConverterPipe):
    """
    Converter for IBL Neuropixels 2.0 multi-shank recordings.

    This converter handles IBL's specific data organization where each shank of a
    Neuropixels 2.0 multi-shank probe is stored in a separate compressed file.
    Standard SpikeGLX recordings store all shanks in a single file, but IBL splits
    the data during preprocessing for parallel processing and storage efficiency.

    The converter:
    - Creates one interface per shank per band (up to 24 for 3 probes x 4 shanks x 2 bands)
    - Coordinates temporal alignment across all shanks (TODO)
    - Manages shared NIDQ behavioral sync signals
    - Merges device metadata (one device per physical probe)

    Parameters
    ----------
    folder_path : Path or str
        Path to the decompressed ephys data folder (containing raw_ephys_data/)
    one : ONE
        ONE API instance
    eid : str
        Session ID (experiment UUID)
    probe_name_to_probe_id_dict : dict
        Mapping from physical probe names (e.g., "probe00") to probe insertion IDs
    bands : list of {"ap", "lf"}, optional
        Which frequency bands to include. Default is ["ap", "lf"] (both bands).

    Examples
    --------
    >>> converter = IblNeuropixels2Converter(
    ...     folder_path="/path/to/decompressed/session",
    ...     one=one,
    ...     eid="abc123",
    ...     probe_name_to_probe_id_dict={"probe00": "pid1", "probe01": "pid2"},
    ... )
    >>> converter.run_conversion(nwbfile_path="output.nwb")
    """

    REVISION: str = "2025-05-06"

    def __init__(
        self,
        folder_path: Path | str,
        one: ONE,
        eid: str,
        probe_name_to_probe_id_dict: dict,
        bands: list[Literal["ap", "lf"]] | None = None,
        verbose: bool = False,
        logger: logging.Logger | None = None,
    ):
        self.folder_path = Path(folder_path)
        self.one = one
        self.eid = eid
        self.probe_name_to_probe_id_dict = probe_name_to_probe_id_dict
        self.bands = bands or ["ap", "lf"]
        self.logger = logger

        data_interfaces = {}

        # Discover all shank folders
        raw_ephys_folder = self.folder_path / "raw_ephys_data"
        if not raw_ephys_folder.exists():
            raise FileNotFoundError(f"raw_ephys_data folder not found at {raw_ephys_folder}")

        shank_folders = sorted([
            f for f in raw_ephys_folder.iterdir()
            if f.is_dir() and f.name.startswith("probe") and len(f.name) == 8  # probe00a format
        ])

        if len(shank_folders) == 0:
            raise FileNotFoundError(
                f"No per-shank folders (probeXXY format) found in {raw_ephys_folder}. "
                "This converter is for IBL Neuropixels 2.0 data with per-shank file organization."
            )

        if logger:
            logger.info(f"Found {len(shank_folders)} shank folders")

        # Create interface for each shank and band
        for shank_folder in shank_folders:
            shank_name = shank_folder.name  # e.g., "probe00a"

            for band in self.bands:
                # Find .bin file for this band
                bin_files = list(shank_folder.glob(f"*.{band}.bin"))

                if not bin_files:
                    if verbose and logger:
                        logger.debug(f"No {band.upper()} .bin file found in {shank_folder.name}")
                    continue

                bin_file = bin_files[0]

                try:
                    interface = IblNeuropixels2ShankInterface(
                        bin_file_path=bin_file,
                        shank_name=shank_name,
                        band=band,
                        verbose=verbose,
                    )

                    # Key format: "probe00a.ap" or "probe00a.lf"
                    key = f"{shank_name}.{band}"
                    data_interfaces[key] = interface

                    if verbose and logger:
                        logger.debug(f"Created interface for {key}")

                except Exception as e:
                    if logger:
                        logger.warning(f"Failed to create interface for {shank_name} {band}: {e}")
                    continue

        if len(data_interfaces) == 0:
            raise RuntimeError(
                f"No interfaces could be created from {raw_ephys_folder}. "
                "Ensure .bin files exist (run decompression first)."
            )

        # Initialize parent ConverterPipe
        super().__init__(data_interfaces=list(data_interfaces.values()), verbose=verbose)

        # Store interface dict for direct access
        self.data_interface_objects = data_interfaces

        if logger:
            logger.info(f"Created {len(data_interfaces)} shank interfaces")

        # Set group_name property on each extractor for electrode table grouping
        self._set_group_names()

    def _set_group_names(self) -> None:
        """Set group_name property on extractors for NWB electrode table."""
        for key, interface in self.data_interface_objects.items():
            # Parse key: "probe00a.ap" -> shank_name="probe00a"
            shank_name = key.split(".")[0]

            # Get formatted name: "probe00a" -> "Probe00ShankA"
            group_name = interface._format_shank_name()

            # Set group_name property on the recording extractor
            extractor = interface.recording_extractor
            channel_ids = extractor.get_channel_ids()
            extractor.set_property(
                key="group_name",
                ids=channel_ids,
                values=[group_name] * len(channel_ids),
            )

    def get_metadata(self) -> dict:
        """
        Aggregate metadata from all shank interfaces.

        Merges device metadata (one device per physical probe) and electrode
        group metadata (one group per shank).
        """
        metadata = super().get_metadata()

        # Deduplicate devices - each physical probe should have one device
        seen_devices = {}
        merged_devices = []

        for key, interface in self.data_interface_objects.items():
            iface_meta = interface.get_metadata()
            if "Ecephys" in iface_meta and "Device" in iface_meta["Ecephys"]:
                for device in iface_meta["Ecephys"]["Device"]:
                    if device["name"] not in seen_devices:
                        seen_devices[device["name"]] = True
                        merged_devices.append(device)

        if merged_devices:
            metadata.setdefault("Ecephys", {})["Device"] = merged_devices

        return metadata

    def temporally_align_data_interfaces(self) -> None:
        """
        Align timestamps across all shanks using SpikeSortingLoader.

        TODO: Implement temporal alignment for per-shank data.
        This requires understanding how SpikeSortingLoader works with
        the per-shank file organization.
        """
        # For now, skip temporal alignment - timestamps will be sample-based
        # This can be implemented later when we understand the alignment requirements
        if self.logger:
            self.logger.warning(
                "Temporal alignment not yet implemented for NP2.0 per-shank data. "
                "Using sample-based timestamps."
            )

    def add_to_nwbfile(
        self,
        nwbfile: NWBFile,
        metadata: dict,
        conversion_options: dict | None = None,
    ) -> None:
        """
        Write all shank data to NWB file.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWB file to write to
        metadata : dict
            Metadata dictionary
        conversion_options : dict, optional
            Per-interface conversion options, keyed by interface name.
            Each interface can have options like stub_test, iterator_options, etc.
        """
        conversion_options = conversion_options or {}

        # Temporal alignment (currently a no-op)
        self.temporally_align_data_interfaces()

        # Remove inter_sample_shift property to avoid multi-probe electrode issues
        # (Same workaround as in IblSpikeGlxConverter)
        for key, interface in self.data_interface_objects.items():
            if hasattr(interface, "recording_extractor"):
                rec = interface.recording_extractor
                if "inter_sample_shift" in rec.get_property_keys():
                    rec.delete_property("inter_sample_shift")

        # Set always_write_timestamps for all interfaces
        for key in self.data_interface_objects.keys():
            if key not in conversion_options:
                conversion_options[key] = {}
            conversion_options[key]["always_write_timestamps"] = True

        # Call parent's add_to_nwbfile
        super().add_to_nwbfile(
            nwbfile=nwbfile,
            metadata=metadata,
            conversion_options=conversion_options,
        )


def discover_np2_shank_folders(raw_ephys_folder: Path) -> list[str]:
    """
    Discover NP2.0 per-shank folders in a raw_ephys_data directory.

    Parameters
    ----------
    raw_ephys_folder : Path
        Path to raw_ephys_data folder

    Returns
    -------
    list[str]
        List of shank folder names (e.g., ["probe00a", "probe00b", ...])
    """
    if not raw_ephys_folder.exists():
        return []

    return sorted([
        f.name for f in raw_ephys_folder.iterdir()
        if f.is_dir() and f.name.startswith("probe") and len(f.name) == 8
    ])


def get_physical_probe_from_shank(shank_name: str) -> str:
    """
    Extract physical probe name from shank folder name.

    Parameters
    ----------
    shank_name : str
        Shank folder name (e.g., "probe00a")

    Returns
    -------
    str
        Physical probe name (e.g., "probe00")
    """
    return shank_name[:7]  # "probe00a" -> "probe00"

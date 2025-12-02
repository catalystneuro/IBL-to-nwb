"""IBL-specific NIDQ interface with wiring.json support.

This interface extends NeuroConv's SpikeGLXNIDQInterface to use the session's
wiring.json file for dynamic channel configuration. Instead of hardcoding
channel-to-device mappings, it reads the wiring configuration and generates
appropriate metadata for semantic channel names and descriptions.
"""

import logging
import warnings
from pathlib import Path

from neuroconv.datainterfaces import SpikeGLXNIDQInterface
from neuroconv.utils import dict_deep_update, load_dict_from_file
from one.api import ONE
from pydantic import DirectoryPath

from ._base_ibl_interface import BaseIBLDataInterface


_logger = logging.getLogger(__name__)

# Path to the NIDQ metadata YAML file (in NeuroConv format)
_NIDQ_METADATA_PATH = Path(__file__).parent.parent / "_metadata" / "ibl_nidq_device_configs.yaml"


class IblNIDQInterface(SpikeGLXNIDQInterface, BaseIBLDataInterface):
    """
    IBL-specific NIDQ interface that uses wiring.json for channel configuration.

    This interface extends NeuroConv's SpikeGLXNIDQInterface to:
    1. Load wiring configuration from ONE (required)
    2. Validate that devices in wiring.json have corresponding metadata in YAML
    3. Use NeuroConv's metadata customization API with channel-ID-keyed YAML

    The wiring.json file documents how behavioral devices are connected to NIDQ
    channels and varies by rig, making it essential session-specific metadata.

    Example wiring.json structure:
    {
        "SYSTEM": "3B",
        "SYNC_WIRING_DIGITAL": {
            "P0.0": "left_camera",
            "P0.1": "right_camera",
            ...
        },
        "SYNC_WIRING_ANALOG": {
            "AI0": "bpod",
            "AI1": "laser",
            ...
        }
    }
    """

    # Use BWM standard revision
    REVISION: str | None = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """
        Get data requirements for NIDQ interface.

        Returns
        -------
        dict
            Dictionary with required NIDQ files including wiring.json.
        """
        return {
            "one_objects": [],
            "exact_files_options": {
                "standard": [
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.cbin",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.meta",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.ch",
                    "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.wiring.json",
                ],
            },
        }

    @classmethod
    def download_data(cls, one, eid, download_only=True, logger=None, **kwargs):
        """
        Download NIDQ files for this session.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        download_only : bool, default=True
            If True, only download without loading into memory
        logger : logging.Logger, optional
            Logger instance
        **kwargs
            Additional keyword arguments

        Returns
        -------
        dict
            Download status with keys: success, downloaded_files, already_cached, etc.
        """
        requirements = cls.get_data_requirements()

        if logger:
            logger.info(f"Downloading NIDQ files for session {eid}")

        downloaded_files = []
        for nidq_file in requirements["exact_files_options"]["standard"]:
            try:
                one.load_dataset(eid, nidq_file, download_only=download_only)
                downloaded_files.append(nidq_file)
                if logger:
                    logger.info(f"  Downloaded {nidq_file}")
            except Exception as e:
                if logger:
                    logger.error(f"  Failed to download {nidq_file}: {e}")
                raise

        return {
            "success": True,
            "downloaded_objects": [],
            "downloaded_files": downloaded_files,
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def __init__(
        self,
        folder_path: DirectoryPath,
        one: ONE,
        eid: str,
        verbose: bool = False,
        es_key: str = "ElectricalSeriesNIDQ",
    ):
        """
        Initialize IBL NIDQ interface with wiring-driven configuration.

        Parameters
        ----------
        folder_path : DirectoryPath
            Path to folder containing decompressed .nidq.bin file
        one : ONE
            ONE API instance for loading wiring configuration
        eid : str
            Session ID (used to load wiring.json)
        verbose : bool, default=False
            Whether to output verbose text
        es_key : str, default="ElectricalSeriesNIDQ"
            Key for the NIDQ ElectricalSeries in metadata

        Raises
        ------
        ValueError
            If wiring.json is not found for the session.
        """
        self.one = one
        self.eid = eid
        self.revision = self.REVISION

        # Load wiring configuration (required)
        self.wiring = one.load_dataset(
            id=eid,
            dataset="raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.wiring.json",
            download_only=False,
        )
        _logger.info(f"Loaded NIDQ wiring configuration for session {eid}")

        # Create analog channel groups from wiring
        analog_channel_groups = self._create_analog_channel_groups()
        _logger.debug(f"Analog channel groups: {analog_channel_groups}")

        # Initialize parent interface with analog channel groups
        super().__init__(
            folder_path=folder_path,
            verbose=verbose,
            es_key=es_key,
            analog_channel_groups=analog_channel_groups if analog_channel_groups else None,
        )

        # Validate wiring.json against metadata YAML
        self._validate_wiring_against_metadata()

    def _create_analog_channel_groups(self) -> dict[str, list[str]]:
        """
        Generate analog channel groups from wiring configuration.

        Returns
        -------
        dict[str, list[str]]
            Mapping from device names to lists of SpikeGLX analog channel IDs.
            Example: {'bpod': ['nidq#XA0'], 'laser': ['nidq#XA1']}
        """
        analog_channel_groups = {}
        analog_wiring = self.wiring.get("SYNC_WIRING_ANALOG", {})

        for analog_input, device_name in analog_wiring.items():
            if analog_input.startswith("AI"):
                channel_num = analog_input[2:]
                channel_id = f"nidq#XA{channel_num}"
                analog_channel_groups[device_name] = [channel_id]

        return analog_channel_groups

    def _validate_wiring_against_metadata(self) -> None:
        """
        Validate that wiring.json is consistent with the metadata YAML.

        This method checks that:
        1. Digital channels in wiring.json have corresponding entries in metadata YAML
        2. Analog channels in wiring.json have corresponding entries in metadata YAML

        If a device in wiring.json doesn't have metadata configured, a warning is raised.

        Warns
        -----
        UserWarning
            If any device in wiring.json doesn't have corresponding metadata
        """
        nidq_metadata = load_dict_from_file(_NIDQ_METADATA_PATH)
        metadata_key = self.metadata_key

        # Get configured channel IDs from metadata YAML
        events_metadata = nidq_metadata.get("Events", {}).get(metadata_key, {})
        configured_digital_channels = set(events_metadata.keys())

        timeseries_metadata = nidq_metadata.get("TimeSeries", {}).get(metadata_key, {})
        configured_analog_devices = set(timeseries_metadata.keys())

        # Check digital channels from wiring.json
        digital_wiring = self.wiring.get("SYNC_WIRING_DIGITAL", {})
        for port_pin, device_name in digital_wiring.items():
            if port_pin.startswith("P0."):
                bit_num = port_pin.split(".")[-1]
                channel_id = f"nidq#XD{bit_num}"

                if channel_id not in configured_digital_channels:
                    warnings.warn(
                        f"NIDQ metadata missing for digital channel {channel_id}:\n"
                        f"  Device in wiring.json: '{device_name}' (at {port_pin})\n"
                        f"  No metadata entry found in {_NIDQ_METADATA_PATH.name}\n"
                        f"  Add an entry under Events.{metadata_key}.\"{channel_id}\" to configure this channel.",
                        UserWarning,
                        stacklevel=3,
                    )

        # Check analog channels from wiring.json
        analog_wiring = self.wiring.get("SYNC_WIRING_ANALOG", {})
        for analog_input, device_name in analog_wiring.items():
            if analog_input.startswith("AI"):
                if device_name not in configured_analog_devices:
                    warnings.warn(
                        f"NIDQ metadata missing for analog device '{device_name}':\n"
                        f"  Device in wiring.json at {analog_input}\n"
                        f"  No metadata entry found in {_NIDQ_METADATA_PATH.name}\n"
                        f"  Add an entry under TimeSeries.{metadata_key}.\"{device_name}\" to configure this device.",
                        UserWarning,
                        stacklevel=3,
                    )

    def get_metadata(self):
        """
        Get metadata with IBL-specific channel configurations.

        The metadata is loaded directly from the YAML file in NeuroConv format
        and merged with the parent metadata.

        Returns
        -------
        dict
            Metadata dictionary with:
            - Events metadata for digital channels (semantic names, descriptions, labels)
            - TimeSeries metadata for analog channels (semantic names, descriptions)
        """
        metadata = super().get_metadata()

        # Load and merge NIDQ metadata from YAML (already in NeuroConv format)
        nidq_metadata = load_dict_from_file(_NIDQ_METADATA_PATH)
        metadata = dict_deep_update(metadata, nidq_metadata)

        return metadata

"""IBL-specific NIDQ interface with wiring.json support.

This interface extends NeuroConv's SpikeGLXNIDQInterface to use the session's
wiring.json file for dynamic channel configuration. Device metadata is stored
in a static YAML file, and channel IDs are determined at runtime from wiring.json.
"""

import warnings
from pathlib import Path
from ._base_ibl_interface import BaseIBLDataInterface

from neuroconv.datainterfaces import SpikeGLXNIDQInterface
from neuroconv.utils import dict_deep_update, load_dict_from_file
from pydantic import DirectoryPath

# =============================================================================
# Digital Device Labels (needed at init time for digital_channel_groups)
# These define how to interpret binary values (0/1) for each device type
# =============================================================================

DIGITAL_DEVICE_LABELS = {
    "left_camera": {0: "exposure_end", 1: "frame_start"},
    "right_camera": {0: "exposure_end", 1: "frame_start"},
    "body_camera": {0: "exposure_end", 1: "frame_start"},
    "imec_sync": {0: "sync_low", 1: "sync_high"},
    "frame2ttl": {0: "screen_dark", 1: "screen_bright"},
    "rotary_encoder_0": {0: "phase_low", 1: "phase_high"},
    "rotary_encoder_1": {0: "phase_low", 1: "phase_high"},
    "audio": {0: "audio_off", 1: "audio_on"},
}


class IblNIDQInterface(SpikeGLXNIDQInterface, BaseIBLDataInterface):
    """
    IBL-specific NIDQ interface that uses wiring.json for channel configuration.

    This interface extends NeuroConv's SpikeGLXNIDQInterface to:
    1. Build digital_channel_groups and analog_channel_groups from wiring.json
    2. Load static NWB metadata (name, description, meanings) from YAML

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
        one,
        eid: str,
        verbose: bool = False,
        metadata_key: str = "IblNIDQ",
    ):
        """
        Initialize IBL NIDQ interface with wiring-driven configuration.

        Parameters
        ----------
        folder_path : DirectoryPath
            Path to folder containing .nidq.bin file
        one : ONE
            ONE API instance for loading wiring.json
        eid : str
            Session ID (experiment ID)
        verbose : bool, default=False
            Whether to output verbose text
        metadata_key : str, default="IblNIDQ"
            Key for organizing NIDQ metadata in the metadata dictionary
        """
        # Load wiring.json which maps hardware ports to device names
        self.wiring = one.load_dataset(eid, "_spikeglx_ephysData_g0_t0.nidq.wiring.json", collection="raw_ephys_data")

        # Build channel groups from wiring
        digital_channel_groups = self.get_digital_channel_groups_from_wiring(self.wiring)
        analog_channel_groups = self.get_analog_channel_groups_from_wiring(self.wiring)

        # Initialize parent interface with channel groups
        super().__init__(
            folder_path=folder_path,
            verbose=verbose,
            metadata_key=metadata_key,
            digital_channel_groups=digital_channel_groups if digital_channel_groups else None,
            analog_channel_groups=analog_channel_groups if analog_channel_groups else None,
        )

    @staticmethod
    def get_digital_channel_groups_from_wiring(wiring: dict) -> dict:
        """
        Build digital_channel_groups from wiring.json.

        Maps each digital device in wiring.json to its channel ID and labels_map.

        Parameters
        ----------
        wiring : dict
            Wiring configuration loaded from wiring.json

        Returns
        -------
        dict
            NeuroConv-compatible digital_channel_groups structure.
            Example: {
                "left_camera": {
                    "channels": {
                        "nidq#XD0": {"labels_map": {0: "exposure_end", 1: "frame_start"}}
                    }
                }
            }
        """
        digital_channel_groups = {}
        digital_wiring = wiring.get("SYNC_WIRING_DIGITAL", {})

        for port_pin, device_name in digital_wiring.items():
            if port_pin.startswith("P0."):
                bit_num = port_pin.split(".")[-1]
                channel_id = f"nidq#XD{bit_num}"

                if device_name in DIGITAL_DEVICE_LABELS:
                    digital_channel_groups[device_name] = {
                        "channels": {
                            channel_id: {"labels_map": DIGITAL_DEVICE_LABELS[device_name]}
                        }
                    }
                else:
                    warnings.warn(
                        f"No labels configured for digital device '{device_name}' "
                        f"at channel {channel_id} (port {port_pin}). "
                        f"Add an entry to DIGITAL_DEVICE_LABELS in _ibl_nidq_interface.py.",
                        UserWarning,
                        stacklevel=2,
                    )

        return digital_channel_groups

    @staticmethod
    def get_analog_channel_groups_from_wiring(wiring: dict) -> dict:
        """
        Build analog_channel_groups from wiring.json.

        Maps each analog device in wiring.json to its channel ID.

        Parameters
        ----------
        wiring : dict
            Wiring configuration loaded from wiring.json

        Returns
        -------
        dict
            NeuroConv-compatible analog_channel_groups structure.
            Example: {"bpod": {"channels": ["nidq#XA0"]}}
        """
        analog_channel_groups = {}
        analog_wiring = wiring.get("SYNC_WIRING_ANALOG", {})

        for analog_input, device_name in analog_wiring.items():
            if analog_input.startswith("AI"):
                channel_num = analog_input[2:]
                channel_id = f"nidq#XA{channel_num}"
                analog_channel_groups[device_name] = {"channels": [channel_id]}

        return analog_channel_groups

    def get_metadata(self):
        """
        Get metadata with IBL-specific channel configurations.

        Loads static metadata from YAML and filters to only include devices
        present in this session's wiring.json.

        Returns
        -------
        dict
            Metadata dictionary with:
            - Events metadata for digital channels (name, description, meanings)
            - TimeSeries metadata for analog channels (name, description)
        """
        metadata = super().get_metadata()

        # Load static metadata from YAML
        static_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "nidq.yml")

        # Get devices present in this session's wiring
        digital_devices = set(self.wiring.get("SYNC_WIRING_DIGITAL", {}).values())
        analog_devices = set(self.wiring.get("SYNC_WIRING_ANALOG", {}).values())

        # Filter Events metadata to only include devices in wiring
        events_metadata = {}
        for device in digital_devices:
            if device in static_metadata.get("Events", {}):
                events_metadata[device] = static_metadata["Events"][device].copy()
            else:
                warnings.warn(
                    f"No metadata configured for digital device '{device}'. "
                    f"Add an entry to _metadata/nidq.yml.",
                    UserWarning,
                    stacklevel=2,
                )

        if events_metadata:
            metadata = dict_deep_update(metadata, {"Events": {self.metadata_key: events_metadata}})

        # Filter TimeSeries metadata to only include devices in wiring
        timeseries_metadata = {}
        for device in analog_devices:
            if device in static_metadata.get("TimeSeries", {}):
                timeseries_metadata[device] = static_metadata["TimeSeries"][device].copy()
            else:
                warnings.warn(
                    f"No metadata configured for analog device '{device}'. "
                    f"Add an entry to _metadata/nidq.yml.",
                    UserWarning,
                    stacklevel=2,
                )

        if timeseries_metadata:
            metadata = dict_deep_update(metadata, {"TimeSeries": {self.metadata_key: timeseries_metadata}})

        return metadata

"""
Neuroconv interface for IBL Neuropixels 2.0 per-shank recordings.

This interface is specific to IBL's data organization where each shank of a
Neuropixels 2.0 multi-shank probe is stored in a separate file. The IBL pipeline
splits the data during preprocessing for parallel processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import (
    BaseRecordingExtractorInterface,
)
from neuroconv.utils import DeepDict


class IblNeuropixels2ShankInterface(BaseRecordingExtractorInterface):
    """
    Interface for a single IBL Neuropixels 2.0 shank.

    This interface is specific to IBL's data organization where each shank of a
    Neuropixels 2.0 multi-shank probe is stored in a separate file. The IBL pipeline
    splits the data during preprocessing for parallel processing.

    Each shank is written as a separate ElectricalSeries in the NWB file, with
    unique naming based on the physical probe and shank letter (A-D).

    Parameters
    ----------
    bin_file_path : Path or str
        Path to the decompressed .bin file for this shank
    shank_name : str
        IBL shank folder name (e.g., "probe00a", "probe01b", "probe02d")
    band : {"ap", "lf"}
        Recording band - "ap" for action potential (30 kHz) or "lf" for
        local field potential (2.5 kHz)
    verbose : bool, default: False
        Whether to print verbose output during initialization

    Examples
    --------
    >>> interface = IblNeuropixels2ShankInterface(
    ...     bin_file_path="/path/to/probe00a/_spikeglx_ephysData_g0_t0.imec0.ap.bin",
    ...     shank_name="probe00a",
    ...     band="ap",
    ... )
    >>> interface.add_to_nwbfile(nwbfile, metadata)
    """

    display_name = "IBL Neuropixels 2.0 Shank"
    associated_suffixes = (".bin", ".meta")
    info = "Interface for IBL's per-shank Neuropixels 2.0 recordings."

    @classmethod
    def get_extractor_class(cls):
        from ._ibl_neuropixels2_shank_extractor import IblNeuropixels2ShankExtractor

        return IblNeuropixels2ShankExtractor

    def __init__(
        self,
        bin_file_path: Path | str,
        shank_name: str,
        band: Literal["ap", "lf"] = "ap",
        verbose: bool = False,
    ):
        self.shank_name = shank_name
        self.bin_file_path = Path(bin_file_path)
        self.band = band

        # Set es_key for unique ElectricalSeries naming
        # e.g., "ElectricalSeriesProbe00ShankAAP" or "ElectricalSeriesProbe00ShankALF"
        es_key = f"ElectricalSeries{self._format_shank_name()}{band.upper()}"

        super().__init__(
            bin_file_path=bin_file_path,
            band=band,
            verbose=verbose,
            es_key=es_key,
        )

    def _initialize_extractor(self, interface_kwargs: dict):
        """
        Initialize the extractor, removing unsupported kwargs.

        The base class adds 'all_annotations=True' which our custom extractor
        doesn't support, so we remove it here.
        """
        self.extractor_kwargs = interface_kwargs.copy()
        self.extractor_kwargs.pop("verbose", None)
        self.extractor_kwargs.pop("all_annotations", None)
        self.extractor_kwargs.pop("es_key", None)

        extractor_class = self.get_extractor_class()
        return extractor_class(**self.extractor_kwargs)

    def _format_shank_name(self) -> str:
        """
        Convert IBL shank folder name to NWB-friendly name.

        'probe00a' -> 'Probe00ShankA'
        'probe01b' -> 'Probe01ShankB'
        """
        probe_num = self.shank_name[5:7]  # "00", "01", "02"
        shank_letter = self.shank_name[7].upper()  # "A", "B", "C", "D"
        return f"Probe{probe_num}Shank{shank_letter}"

    def _get_physical_probe_name(self) -> str:
        """
        Get physical probe name from shank name.

        'probe00a' -> 'Probe00'
        'probe01b' -> 'Probe01'
        """
        probe_num = self.shank_name[5:7]
        return f"Probe{probe_num}"

    def _get_shank_letter(self) -> str:
        """Get shank letter (A, B, C, D) from shank name."""
        return self.shank_name[7].upper()

    def get_metadata(self) -> DeepDict:
        """Get metadata for this shank interface."""
        metadata = super().get_metadata()

        # Get information from the extractor
        extractor = self.recording_extractor

        # Device name is per physical probe (3 devices for 12 shanks)
        device_name = f"Neuropixels2{self._get_physical_probe_name()}"

        # Electrode group name is per shank (12 groups total)
        group_name = self._format_shank_name()

        # Get probe info from extractor
        serial_number = extractor.probe_serial
        probe_type = extractor.probe_type
        shank_idx = extractor.shank_index

        # Map probe type codes to human-readable names
        probe_type_names = {
            "24": "NP2010 (Neuropixels 2.0 4-shank)",
            "2013": "NP2014 (Neuropixels 2.0 4-shank)",
            "2014": "NP2014 (Neuropixels 2.0 4-shank)",
            "21": "NP2000 (Neuropixels 2.0 single-shank)",
        }
        probe_type_desc = probe_type_names.get(str(probe_type), f"Neuropixels 2.0 (type {probe_type})")

        # Build device metadata
        metadata["Ecephys"]["Device"] = [
            {
                "name": device_name,
                "description": f"{probe_type_desc}, serial {serial_number}",
                "manufacturer": "IMEC",
            }
        ]

        # Build electrode group metadata
        metadata["Ecephys"]["ElectrodeGroup"] = [
            {
                "name": group_name,
                "description": (
                    f"Shank {self._get_shank_letter()} (index {shank_idx}) of "
                    f"Neuropixels 2.0 probe {self.shank_name[5:7]}"
                ),
                "location": "unknown",
                "device": device_name,
            }
        ]

        # Update ElectricalSeries metadata
        band_desc = "action potential" if self.band == "ap" else "local field potential"
        sampling_rate = extractor.get_sampling_frequency()
        metadata["Ecephys"][self.es_key] = {
            "name": self.es_key,
            "description": (
                f"Raw {band_desc} band ({self.band.upper()}) recording from "
                f"{self._format_shank_name()} at {sampling_rate:.0f} Hz"
            ),
        }

        return metadata

    def get_metadata_schema(self) -> dict:
        """Get JSON schema for the metadata."""
        metadata_schema = super().get_metadata_schema()
        return metadata_schema

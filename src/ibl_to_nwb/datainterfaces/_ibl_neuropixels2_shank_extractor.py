"""
SpikeInterface extractor for IBL Neuropixels 2.0 per-shank recordings.

This extractor is specific to IBL's data organization where each shank of a
Neuropixels 2.0 multi-shank probe is stored in a separate compressed file.
Standard SpikeGLX recordings store all shanks in a single file, but IBL
splits the data during preprocessing for parallel processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import probeinterface
from neo.rawio.spikeglxrawio import read_meta_file
from spikeinterface.core import BaseRecording, BaseRecordingSegment


class IblNeuropixels2ShankRecordingSegment(BaseRecordingSegment):
    """Recording segment for a single IBL Neuropixels 2.0 shank."""

    def __init__(
        self,
        bin_file_path: Path,
        sampling_frequency: float,
        num_channels: int,
        dtype: np.dtype,
        t_start: float = 0.0,
    ):
        BaseRecordingSegment.__init__(self, sampling_frequency=sampling_frequency, t_start=t_start)
        self.bin_file_path = Path(bin_file_path)
        self.num_channels = num_channels
        self.dtype = np.dtype(dtype)
        self.bytes_per_sample = num_channels * self.dtype.itemsize
        self.file_size = self.bin_file_path.stat().st_size
        self._num_samples = self.file_size // self.bytes_per_sample

        # Memory-map the file for efficient access
        self._memmap = np.memmap(self.bin_file_path, dtype=self.dtype, mode="r")
        self._memmap = self._memmap.reshape(-1, num_channels)

    def get_num_samples(self) -> int:
        return self._num_samples

    def get_traces(
        self,
        start_frame: int | None = None,
        end_frame: int | None = None,
        channel_indices: np.ndarray | list | None = None,
    ) -> np.ndarray:
        start_frame = start_frame or 0
        end_frame = end_frame or self._num_samples

        traces = self._memmap[start_frame:end_frame, :]
        if channel_indices is not None:
            traces = traces[:, channel_indices]
        return np.asarray(traces)


class IblNeuropixels2ShankExtractor(BaseRecording):
    """
    SpikeInterface extractor for a single IBL Neuropixels 2.0 shank.

    This extractor is specific to IBL's data organization where each shank of a
    Neuropixels 2.0 multi-shank probe is stored in a separate compressed file.
    Standard SpikeGLX recordings store all shanks in a single file.

    The extractor reads decompressed .bin files (after mtscomp decompression)
    and parses metadata from accompanying .meta files.

    Parameters
    ----------
    bin_file_path : Path or str
        Path to the decompressed .bin file for this shank
    meta_file_path : Path or str, optional
        Path to the .meta file. If not provided, looks for .meta file with
        same stem as bin file.
    band : {"ap", "lf"}
        Recording band - "ap" for action potential (30 kHz) or "lf" for
        local field potential (2.5 kHz). Used for metadata and naming.

    Examples
    --------
    >>> extractor = IblNeuropixels2ShankExtractor(
    ...     bin_file_path="/path/to/probe00a/_spikeglx_ephysData_g0_t0.imec0.ap.bin",
    ...     band="ap"
    ... )
    >>> traces = extractor.get_traces(start_frame=0, end_frame=30000)
    """

    extractor_name = "IblNeuropixels2Shank"
    mode = "file"
    name = "ibl_neuropixels2_shank"

    def __init__(
        self,
        bin_file_path: Path | str,
        meta_file_path: Path | str | None = None,
        band: Literal["ap", "lf"] = "ap",
    ):
        bin_file_path = Path(bin_file_path)

        # Find meta file
        if meta_file_path is None:
            meta_file_path = bin_file_path.with_suffix(".meta")
        else:
            meta_file_path = Path(meta_file_path)

        if not bin_file_path.exists():
            raise FileNotFoundError(f"Binary file not found: {bin_file_path}")
        if not meta_file_path.exists():
            raise FileNotFoundError(f"Meta file not found: {meta_file_path}")

        # Store paths
        self.bin_file_path = bin_file_path
        self.meta_file_path = meta_file_path
        self.band = band

        # Parse metadata using neo's parser
        self.meta = read_meta_file(meta_file_path)

        # Extract parameters from meta
        sampling_frequency = float(self.meta["imSampRate"])
        num_channels = int(self.meta["nSavedChans"])
        dtype = np.dtype("int16")

        # Calculate gain to convert from int16 to microvolts
        # Formula: value_uV = raw_int16 * (imAiRangeMax / imMaxInt) * 1e6 / gain
        gain = float(self.meta.get("imChan0apGain", 80.0))
        im_max_int = float(self.meta.get("imMaxInt", 512))
        ai_range_max = float(self.meta.get("imAiRangeMax", 0.6))
        gain_to_uV = (ai_range_max / im_max_int) * 1e6 / gain

        # Initialize base class
        channel_ids = np.arange(num_channels)
        BaseRecording.__init__(
            self,
            sampling_frequency=sampling_frequency,
            channel_ids=channel_ids,
            dtype=dtype,
        )

        # Add recording segment
        rec_segment = IblNeuropixels2ShankRecordingSegment(
            bin_file_path=bin_file_path,
            sampling_frequency=sampling_frequency,
            num_channels=num_channels,
            dtype=dtype,
        )
        self.add_recording_segment(rec_segment)

        # Set gain property for all channels
        self.set_property("gain_to_uV", np.full(num_channels, gain_to_uV))

        # Set offset (typically 0 for Neuropixels)
        self.set_property("offset_to_uV", np.zeros(num_channels))

        # Add probe geometry from probeinterface
        try:
            probe = probeinterface.read_spikeglx(meta_file_path)
            self.set_probe(probe, in_place=True)
        except Exception as e:
            # If probeinterface fails, continue without probe geometry
            import warnings

            warnings.warn(f"Could not load probe geometry from {meta_file_path}: {e}")

        # Store additional metadata
        self._probe_serial = self.meta.get("imDatPrb_sn", "unknown")
        self._probe_type = self.meta.get("imDatPrb_type", "unknown")
        self._shank_index = int(self.meta.get("NP2.4_shank", 0))

        # Store kwargs for serialization
        self._kwargs = {
            "bin_file_path": str(bin_file_path),
            "meta_file_path": str(meta_file_path),
            "band": band,
        }

    @property
    def probe_serial(self) -> str:
        """Serial number of the probe."""
        return self._probe_serial

    @property
    def probe_type(self) -> str:
        """Probe type identifier (e.g., '2013' for NP2014, '24' for NP2010)."""
        return self._probe_type

    @property
    def shank_index(self) -> int:
        """Shank index (0-3 for 4-shank probes)."""
        return self._shank_index

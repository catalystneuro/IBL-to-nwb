# Components Needed for Neuropixels 2.0 NWB Conversion

This document outlines the code components required to convert IBL's Neuropixels 2.0 (NP2.4) data to NWB format, following the existing NP1.0 pipeline pattern with batch decompression to disk.

**Important Note:** The per-shank file organization (separate .cbin files for each shank) is specific to the IBL data pipeline. Standard SpikeGLX recordings store all shanks in a single file. All components are prefixed with "Ibl" to reflect this IBL-specific data organization.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      IblNeuropixels2Converter                                │
│  (coordinates all shanks, all probes, and sync channels)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐       ┌─────────────────┐       │
│   │IblNeuropixels2  │  │IblNeuropixels2  │  ...  │IblNeuropixels2  │       │
│   │ShankInterface   │  │ShankInterface   │       │ShankInterface   │       │
│   │ (probe00a, AP)  │  │ (probe00b, AP)  │       │ (probe02d, AP)  │       │
│   └────────┬────────┘  └────────┬────────┘       └────────┬────────┘       │
│            │                    │                         │                 │
│   ┌────────▼────────┐  ┌────────▼────────┐       ┌────────▼────────┐       │
│   │IblNeuropixels2  │  │IblNeuropixels2  │  ...  │IblNeuropixels2  │       │
│   │ShankExtractor   │  │ShankExtractor   │       │ShankExtractor   │       │
│   │ (reads .bin)    │  │ (reads .bin)    │       │ (reads .bin)    │       │
│   └─────────────────┘  └─────────────────┘       └─────────────────┘       │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────┐      │
│   │                    IblNIDQInterface                              │      │
│   │              (behavioral sync signals - shared)                  │      │
│   └─────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │     decompress_ephys_cbins()  │
                    │   (existing, should work)     │
                    └───────────────────────────────┘
```

---

## Component 0: Decompression (Existing)

**Status:** Should work as-is, needs verification

**File:** `IBL-to-nwb/src/ibl_to_nwb/utils/ephys_decompression.py`

**Function:** `decompress_ephys_cbins(source_folder, target_folder)`

The existing decompression utility uses `rglob("*.cbin")` which should find all per-shank compressed files. It preserves the relative folder structure when decompressing to the target folder.

**Why IBL stores data this way:** The IBL data pipeline splits Neuropixels 2.0 multi-shank recordings into separate compressed files per shank. This is different from standard SpikeGLX output which stores all shanks in a single file. The split is done during IBL's preprocessing pipeline for easier parallel processing and storage management.

**Verification needed:**
- Confirm it correctly handles the per-shank folder structure (probe00a/, probe00b/, etc.)
- Confirm .meta files are copied alongside .bin files for each shank

**Input structure:**
```
source_folder/raw_ephys_data/
├── probe00a/_spikeglx_ephysData_g0_t0.imec0.ap.cbin
├── probe00a/_spikeglx_ephysData_g0_t0.imec0.ap.meta
├── probe00b/_spikeglx_ephysData_g0_t0.imec0.ap.cbin
├── probe00b/_spikeglx_ephysData_g0_t0.imec0.ap.meta
...
```

**Output structure:**
```
target_folder/raw_ephys_data/
├── probe00a/_spikeglx_ephysData_g0_t0.imec0.ap.bin
├── probe00a/_spikeglx_ephysData_g0_t0.imec0.ap.meta
├── probe00b/_spikeglx_ephysData_g0_t0.imec0.ap.bin
├── probe00b/_spikeglx_ephysData_g0_t0.imec0.ap.meta
...
```

---

## Component 1: IBL Per-Shank Extractor

**Status:** New component needed

**File:** `IBL-to-nwb/src/ibl_to_nwb/datainterfaces/_ibl_neuropixels2_shank_extractor.py`

**Purpose:** A SpikeInterface-compatible extractor that reads decompressed .bin files for a single IBL Neuropixels 2.0 shank. This is IBL-specific because standard SpikeGLX recordings don't split data per-shank.

```python
from spikeinterface.core import BaseRecording, BaseRecordingSegment
from neo.rawio.spikeglxrawio import read_meta_file
import probeinterface
import numpy as np
from pathlib import Path


class IblNeuropixels2ShankRecordingSegment(BaseRecordingSegment):
    """Recording segment for a single IBL Neuropixels 2.0 shank."""

    def __init__(self, bin_file_path: Path, sampling_frequency: float, num_channels: int, dtype: np.dtype):
        BaseRecordingSegment.__init__(self, sampling_frequency=sampling_frequency)
        self.bin_file_path = bin_file_path
        self.num_channels = num_channels
        self.dtype = dtype
        self.bytes_per_sample = num_channels * dtype.itemsize
        self.file_size = bin_file_path.stat().st_size
        self._num_samples = self.file_size // self.bytes_per_sample

        # Memory-map the file for efficient access
        self._memmap = np.memmap(bin_file_path, dtype=dtype, mode="r")
        self._memmap = self._memmap.reshape(-1, num_channels)

    def get_num_samples(self) -> int:
        return self._num_samples

    def get_traces(self, start_frame: int = None, end_frame: int = None, channel_indices=None) -> np.ndarray:
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

    Parameters
    ----------
    bin_file_path : Path
        Path to the decompressed .bin file for this shank
    meta_file_path : Path, optional
        Path to the .meta file. If not provided, looks for .meta file with same stem as bin file.
    """

    extractor_name = "IblNeuropixels2Shank"
    mode = "file"
    name = "ibl_neuropixels2_shank"

    def __init__(self, bin_file_path: Path, meta_file_path: Path = None):
        bin_file_path = Path(bin_file_path)

        # Find meta file
        if meta_file_path is None:
            meta_file_path = bin_file_path.with_suffix(".meta")
        if not meta_file_path.exists():
            raise FileNotFoundError(f"Meta file not found: {meta_file_path}")

        # Parse metadata using neo's parser
        self.meta = read_meta_file(meta_file_path)

        # Extract parameters from meta
        sampling_frequency = float(self.meta["imSampRate"])
        num_channels = int(self.meta["nSavedChans"])
        dtype = np.dtype("int16")

        # Get gain for conversion to microvolts
        # NP2.0 uses imChan0apGain or defaults to 80
        gain = float(self.meta.get("imChan0apGain", 80.0))
        gain_to_uV = 1.0 / gain

        # Initialize base class
        channel_ids = np.arange(num_channels)
        BaseRecording.__init__(self, sampling_frequency=sampling_frequency, channel_ids=channel_ids, dtype=dtype)

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

        # Add probe geometry from probeinterface
        probe = probeinterface.read_spikeglx(meta_file_path)
        self.set_probe(probe, in_place=True)

        # Store kwargs for serialization
        self._kwargs = {
            "bin_file_path": str(bin_file_path),
            "meta_file_path": str(meta_file_path),
        }
```

---

## Component 2: IBL Per-Shank NWB Interface

**Status:** New component needed

**File:** `IBL-to-nwb/src/ibl_to_nwb/datainterfaces/_ibl_neuropixels2_shank_interface.py`

**Purpose:** Wrap the IBL shank extractor to write ElectricalSeries to NWB. IBL-specific because it handles the per-shank file organization.

```python
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import BaseRecordingExtractorInterface
from pathlib import Path


class IblNeuropixels2ShankInterface(BaseRecordingExtractorInterface):
    """
    Interface for a single IBL Neuropixels 2.0 shank.

    This interface is specific to IBL's data organization where each shank of a
    Neuropixels 2.0 multi-shank probe is stored in a separate file. The IBL pipeline
    splits the data during preprocessing for parallel processing.
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
        bin_file_path: Path,
        shank_name: str,  # e.g., "probe00a"
        verbose: bool = False,
    ):
        self.shank_name = shank_name
        self.bin_file_path = Path(bin_file_path)

        # Set es_key for unique ElectricalSeries naming
        es_key = f"ElectricalSeries{self._format_shank_name()}"

        super().__init__(
            bin_file_path=bin_file_path,
            verbose=verbose,
            es_key=es_key,
        )

    def _format_shank_name(self) -> str:
        """Convert 'probe00a' to 'Probe00ShankA'."""
        probe_num = self.shank_name[5:7]  # "00"
        shank_letter = self.shank_name[7].upper()  # "A"
        return f"Probe{probe_num}Shank{shank_letter}"

    def _get_physical_probe_name(self) -> str:
        """Get physical probe name: 'probe00a' -> 'Probe00'."""
        probe_num = self.shank_name[5:7]
        return f"Probe{probe_num}"

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        # Customize device (one per physical probe) and electrode group (one per shank)
        device_name = f"Neuropixels2{self._get_physical_probe_name()}"
        group_name = self._format_shank_name()

        # Get serial number from meta if available
        serial_number = self.recording_extractor.meta.get("imDatPrb_sn", "unknown")
        probe_type = self.recording_extractor.meta.get("imDatPrb_type", "24")

        metadata["Ecephys"]["Device"] = [{
            "name": device_name,
            "description": f"Neuropixels 2.0 4-shank probe (type {probe_type}), serial {serial_number}",
            "manufacturer": "IMEC",
        }]

        metadata["Ecephys"]["ElectrodeGroup"] = [{
            "name": group_name,
            "description": f"Shank {self.shank_name[-1].upper()} of Neuropixels 2.0 probe {self.shank_name[5:7]}",
            "location": "unknown",
            "device": device_name,
        }]

        return metadata
```

**Key considerations:**
- Each shank becomes a separate ElectricalSeries (e.g., `ElectricalSeriesProbe00ShankA`)
- Electrodes from all shanks share the same electrode table
- Device should be per physical probe (3 devices for 12 shanks)
- ElectrodeGroup should be per shank (12 groups total)

---

## Component 3: IBL Neuropixels 2.0 Converter

**Status:** New component needed

**File:** `IBL-to-nwb/src/ibl_to_nwb/converters/_ibl_neuropixels2_converter.py`

**Purpose:** Coordinate all shank interfaces, sync channels, and metadata. IBL-specific because it handles the per-shank data organization created by IBL's preprocessing pipeline.

```python
from neuroconv import ConverterPipe
from pathlib import Path
from one.api import ONE
from pynwb import NWBFile

from ..datainterfaces import IblNeuropixels2ShankInterface, IblNIDQInterface


class IblNeuropixels2Converter(ConverterPipe):
    """
    Converter for IBL Neuropixels 2.0 multi-shank recordings.

    This converter handles IBL's specific data organization where each shank of a
    Neuropixels 2.0 multi-shank probe is stored in a separate compressed file.
    Standard SpikeGLX recordings store all shanks in a single file, but IBL splits
    the data during preprocessing for parallel processing and storage efficiency.

    The converter:
    - Creates one interface per shank (up to 12 for 3 probes x 4 shanks)
    - Coordinates temporal alignment across all shanks
    - Manages shared NIDQ behavioral sync signals
    - Merges device metadata (one device per physical probe)
    """

    REVISION: str = "2025-05-06"

    def __init__(
        self,
        folder_path: Path,
        one: ONE,
        eid: str,
        probe_name_to_probe_id_dict: dict,  # Maps physical probe to insertion ID
    ):
        self.folder_path = Path(folder_path)
        self.one = one
        self.eid = eid
        self.probe_name_to_probe_id_dict = probe_name_to_probe_id_dict

        data_interfaces = {}

        # Discover all shank folders
        raw_ephys_folder = self.folder_path / "raw_ephys_data"
        shank_folders = sorted([
            f for f in raw_ephys_folder.iterdir()
            if f.is_dir() and f.name.startswith("probe")
        ])

        # Create interface for each shank
        for shank_folder in shank_folders:
            shank_name = shank_folder.name  # e.g., "probe00a"
            bin_files = list(shank_folder.glob("*.ap.bin"))

            if bin_files:
                bin_file = bin_files[0]
                interface = IblNeuropixels2ShankInterface(
                    bin_file_path=bin_file,
                    shank_name=shank_name,
                )
                key = f"{shank_name}.ap"
                data_interfaces[key] = interface

        # Add NIDQ interface if available
        if IblNIDQInterface.check_availability(one, eid)["available"]:
            nidq_interface = IblNIDQInterface(
                folder_path=str(self.folder_path),
                one=one,
                eid=eid,
            )
            data_interfaces["nidq"] = nidq_interface

        super().__init__(data_interfaces=list(data_interfaces.values()))
        self.data_interface_objects = data_interfaces

    def get_metadata(self) -> dict:
        """Aggregate metadata from all interfaces."""
        metadata = super().get_metadata()

        # Merge devices - deduplicate by physical probe
        # Each physical probe should have one device entry
        seen_devices = {}
        merged_devices = []
        for interface in self.data_interface_objects.values():
            if hasattr(interface, "get_metadata"):
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
        """Align timestamps across all shanks using SpikeSortingLoader."""
        # TODO: Implement using SpikeSortingLoader similar to IblSpikeGlxConverter
        # For each shank, get aligned timestamps from ONE API
        pass

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, **conversion_options) -> None:
        """Write all shank data to NWB file."""
        self.temporally_align_data_interfaces()

        for key, interface in self.data_interface_objects.items():
            interface_options = conversion_options.get(key, {})
            interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, **interface_options)
```

---

## Component Summary

| Component | Status | File | Description |
|-----------|--------|------|-------------|
| 0. Decompression | Existing (verify) | `utils/ephys_decompression.py` | Batch decompress .cbin to .bin |
| 1. Shank Extractor | New | `datainterfaces/_ibl_neuropixels2_shank_extractor.py` | `IblNeuropixels2ShankExtractor` class |
| 2. Shank Interface | New | `datainterfaces/_ibl_neuropixels2_shank_interface.py` | `IblNeuropixels2ShankInterface` class |
| 3. NP2 Converter | New | `converters/_ibl_neuropixels2_converter.py` | `IblNeuropixels2Converter` class |

---

## Data Exploration Findings (KM_038 Session)

Based on exploration of the development session at `/media/heberto/Expansion/ibl_cache/steinmetzlab/Subjects/KM_038/2025-05-19/001/`:

### LF Band Data

**YES** - .lf.cbin files are present in all per-shank folders alongside AP data:

```
probe00a/
├── _spikeglx_ephysData_g0_t0.imec0.ap.cbin  (10G)   - AP band @ 30 kHz
├── _spikeglx_ephysData_g0_t0.imec0.ap.meta
├── _spikeglx_ephysData_g0_t0.imec0.lf.cbin  (809M)  - LF band @ 2.5 kHz
├── _spikeglx_ephysData_g0_t0.imec0.lf.meta
├── _spikeglx_ephysData_g0_t0.imec0.sync.npy
├── _spikeglx_ephysData_g0_t0.imec0.timestamps.npy
├── _spikeglx_sync.channels.probe00a.npy
├── _spikeglx_sync.polarities.probe00a.npy
└── _spikeglx_sync.times.probe00a.npy
```

**Decision needed:** Do we include LF interfaces? They would add 12 more ElectricalSeries.

### Sync Channels

Sync data is stored at **multiple levels**:

1. **Per-shank sync files:**
   - `probe00a/_spikeglx_sync.{channels,polarities,times}.probe00a.npy`
   - `probe00a/_spikeglx_ephysData_g0_t0.imec0.sync.npy`

2. **Global sync files (raw_ephys_data/):**
   - `_spikeglx_sync.{channels,polarities,times}.npy`

### Meta File Contents

Key fields from `.ap.meta`:
- **imDatPrb_type:** Mixed types: 2013 (NP2014) for probe00/02, 24 (NP2010) for probe01
- **imSampRate:** 30000 Hz (AP), 2500 Hz (LF)
- **nSavedChans:** 97 channels (96 electrodes + 1 sync)
- **imChan0apGain:** 100
- **imDatPrb_sn:** Probe serial numbers
- **imSvyNShanks:** 4 (confirms 4-shank probes)
- **NP2.4_shank:** 0-3 (shank identifier)

### Probe Geometry

**ProbeInterface compatible:** Meta files contain:
- `snsGeomMap` - Full geometry specification
- `imroTbl` - IMRO table with channel configuration
- `snsChanMap` - Channel mapping

### NIDQ Data

**Present** in `raw_ephys_data/`:
- `_spikeglx_ephysData_g0_t0.nidq.cbin` (277 MB)
- `_spikeglx_ephysData_g0_t0.nidq.meta`
- `_spikeglx_ephysData_g0_t0.nidq.wiring.json`

NIDQ specs: 30002.8 Hz, 3 channels (2 analog + 1 digital)

---

## Resolved Questions

| Question | Answer |
|----------|--------|
| LF band data? | YES - present for all 12 shanks |
| Probe geometry? | YES - snsGeomMap and imroTbl present, probeinterface compatible |
| NIDQ data? | YES - present in raw_ephys_data/ root |
| Sync channels? | Multiple levels: per-shank .npy files + global files |
| Probe types? | Mixed: NP2014 (type 2013) and NP2010 (type 24) |

## Remaining Decisions

1. **Include LF data?** Would add 12 more ElectricalSeries (LF @ 2.5 kHz)
2. **Temporal alignment approach?** Need to verify SpikeSortingLoader works with per-shank organization
3. **Electrode table structure?** All shanks share one table with group_name per shank

---

## Next Steps

1. Verify decompression works with NP2.0 data structure (both AP and LF)
2. Test `probeinterface.read_spikeglx()` with NP2.0 per-shank .meta files
3. Implement `IblNeuropixels2ShankExtractor`
4. Implement `IblNeuropixels2ShankInterface`
5. Implement `IblNeuropixels2Converter`
6. Test with the KM_038 development session

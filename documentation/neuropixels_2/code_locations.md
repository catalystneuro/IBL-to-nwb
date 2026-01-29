# Code Locations for Neuropixels 2.0 NWB Conversion

This document maps the relevant code sections across the different libraries that can be used or referenced for building a Neuropixels 2.0 converter.

## Overview of Data Flow

```
.cbin (compressed) + .meta + .ch files
           ↓
    mtscomp.Reader() → decompresses on-the-fly or to disk
           ↓
    spikeglx.Reader → parses metadata, provides data access
           ↓
    SpikeInterface extractor → wraps neo/spikeglx readers
           ↓
    Neuroconv interface → converts to NWB format
```

---

## 1. Python-Neo: SpikeGLX RawIO

**Repository:** `/home/heberto/development/work_repos/python-neo`

**Main File:** `neo/rawio/spikeglxrawio.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `SpikeGLXRawIO` class | 71-386 | Main class inheriting from `BaseRawWithBufferApiIO` |
| `_parse_header()` | 127-332 | Header parsing for all streams |
| `scan_files()` | 388-412 | Recursively finds .meta/.bin pairs |
| `read_meta_file()` | 567-586 | Parses SpikeGLX .meta files |
| `extract_stream_info()` | 589-754 | Extracts channel info, gains, offsets |
| **NP2.0 Probe Types** | 636-647 | Handles types 21, 24, 2003, 2004, 2013, 2014 |
| Gain calculation (NP2.0) | 636-647 | Uses `imChan0apGain` or default 1/80.0 |
| Multi-shank support | 611-649 | Detects `imDatPrb_type` for NP2.4 (type 24) |

**Important:** Neo reads `.bin` files directly (uncompressed). For `.cbin` files, decompression is handled separately.

---

## 2. Neuroconv: SpikeGLX Interface

**Repository:** `/home/heberto/development/work_repos/neuroconv`

**Directory:** `src/neuroconv/datainterfaces/ecephys/spikeglx/`

### Main Interface
**File:** `spikeglxdatainterface.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `get_extractor_class()` | 34-39 | Returns `SpikeGLXRecordingExtractor` |
| `_initialize_extractor()` | 41-52 | Initializes with `folder_path`, `stream_id` |
| `__init__()` | 54-95 | Stream validation and parameter handling |
| Probe geometry | 116-145 | Extracts probe info with multi-shank support |
| `get_metadata()` | 181-240 | Sets up NWB ecephys metadata |
| `_get_device_metadata_from_probe()` | 272-324 | Extracts serial number, model, etc. |

### Multi-Stream Converter
**File:** `spikeglxconverter.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `get_streams()` | 45-65 | Discovers all available streams |
| `__init__()` | 67-139 | Orchestrates multiple interfaces (AP, LF, NIDQ) |

### NIDQ Interface
**File:** `spikeglxnidqinterface.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `__init__()` | 37-177 | Handles analog (XA/MA) and digital (XD) channels |
| `add_to_nwbfile()` | 438-507 | Writes analog/digital data to NWB |

### Sync Channel Interface
**File:** `spikeglxsyncchannelinterface.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `__init__()` | 66-133 | Validates and initializes sync channel |
| `add_to_nwbfile()` | 224-278 | Writes sync as TimeSeries |

---

## 3. SpikeInterface: Extractors

**Repository:** `/home/heberto/development/work_repos/spikeinterface`

### SpikeGLX Extractor (wraps Neo)
**File:** `src/spikeinterface/extractors/neoextractors/spikeglx.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `SpikeGLXRecordingExtractor` | 13-112 | Main recording extractor |
| Multi-shank handling | 91-96 | `set_probe(probe, group_mode="by_shank")` |
| Inter-sample shifts | 101 | Applied as channel property |

### Compressed Binary IBL Extractor (key for NP2.0!)
**File:** `src/spikeinterface/extractors/cbin_ibl.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `CompressedBinaryIblExtractor` | 14-126 | Handles .cbin with SpikeGLX .meta |
| mtscomp.Reader usage | 75-76 | `self._cbuffer = mtscomp.Reader()` |
| Multi-shank probe handling | 104-109 | Groups by shank via `probe.shank_ids` |
| `extract_stream_info()` | 151-221 | Channel info, gains, offsets from .meta |
| Data reading | 141 | `traces = self._cbuffer[start_frame:end_frame]` |

### Neo Base Extractor
**File:** `src/spikeinterface/extractors/neoextractors/neobaseextractor.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `_NeoBaseExtractor` | 20-68 | Base class for neo integration |
| `get_neo_io_reader()` | 42-68 | Creates neo.rawio instances dynamically |
| `NeoBaseRecordingExtractor` | 157-335 | Main recording implementation |
| `get_traces()` | 361-377 | Reads data via neo reader |

### Neuropixels Utilities
**File:** `src/spikeinterface/extractors/neuropixels_utils.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `get_neuropixels_sample_shifts_from_probe()` | 10-59 | Inter-sample shift calculation |
| NP2.0 cycle handling | 46-52 | 16 cycles vs NP1.0's 13 cycles |

---

## 4. IBL Libraries: Decompression and Data Access

**Directory:** `/home/heberto/development/ibl_conversion/`

### IBL-to-NWB Decompression Utility
**File:** `IBL-to-nwb/src/ibl_to_nwb/utils/ephys_decompression.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `decompress_ephys_cbins()` | 34-132 | Batch decompresses .cbin to .bin |
| File discovery | 75 | Recursively finds all .cbin files |
| Decompression call | 119 | `spikeglx.Reader().decompress_to_scratch()` |

### SpikeGLX Reader (IBL implementation)
**File:** `ibl-neuropixel/src/spikeglx.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `Reader` class | 32-247 | Main reader for .bin/.cbin files |
| `__init__()` | 54-141 | Initializes reader |
| `open()` | 142-184 | Handles mtscomp vs regular binary |
| mtscomp integration | 145-146 | `mtscomp.Reader()` instantiation |
| `is_mtscomp` property | 217-218 | Detects .cbin files |
| `decompress_file()` | 388-409 | Decompresses single file |
| `decompress_to_scratch()` | 411-439 | Decompresses to scratch directory |
| `compress_file()` | 372-380 | Compresses .bin to .cbin |

### BWM Conversion (alternative decompression)
**File:** `IBL-to-nwb/src/ibl_to_nwb/bwm_to_nwb.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `decompress_ephys_cbins()` | 288-320 | Alternative implementation |

---

## 5. Existing NP1.0 Conversion Pipeline (Reference Implementation)

The current NP1.0 conversion uses **batch decompression to disk** before reading. This is the preferred approach for NP2.0 as well.

### Raw Conversion Entry Point
**File:** `IBL-to-nwb/src/ibl_to_nwb/conversion/raw.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `convert_raw_session()` | 55-582 | Main conversion function |
| Decompression setup | 170-229 | Checks for existing .bin files, calls decompression |
| `decompress_ephys_cbins()` call | 218 | Decompresses .cbin to scratch folder |
| `IblSpikeGlxConverter` creation | 255-260 | Creates converter pointing to decompressed folder |

### Key Configuration Flags
From [convert_bwm_to_nwb.py](src/ibl_to_nwb/_scripts/convert_bwm_to_nwb.py):

```python
REDECOMPRESS_EPHYS = False  # Force regeneration of decompressed SpikeGLX binaries
```

### Decompression Flow (NP1.0)

```
source_folder (ONE cache)          target_folder (scratch disk)
├── raw_ephys_data/                ├── raw_ephys_data/
│   └── probe00/                   │   └── probe00/
│       ├── *.ap.cbin      ───────→│       ├── *.ap.bin  (decompressed)
│       ├── *.ap.meta              │       ├── *.ap.meta (copied)
│       └── *.ap.ch                │       └── (ch file not needed after)
```

### Decompression Implementation
**File:** `IBL-to-nwb/src/ibl_to_nwb/utils/ephys_decompression.py`

| Component | Lines | Description |
|-----------|-------|-------------|
| `decompress_ephys_cbins()` | 34-132 | Main decompression function |
| Find .cbin files | 75 | `list(source_folder.rglob("*.cbin"))` |
| Skip if exists | 90 | `if not target_bin_no_uuid.exists()` |
| Decompression call | 119 | `spikeglx.Reader().decompress_to_scratch()` |
| UUID removal | 124-131 | Cleans filenames for compatibility |

---

## 6. Key Insights for NP2.0 Converter Design

### Per-Shank File Organization
Unlike NP1.0 where all shanks are in one file, NP2.0 data is split:
```
raw_ephys_data/
├── probe00a/   → shank a of physical probe 0 (imec0)
├── probe00b/   → shank b of physical probe 0 (imec0)
├── probe00c/   → shank c of physical probe 0 (imec0)
├── probe00d/   → shank d of physical probe 0 (imec0)
├── probe01a/   → shank a of physical probe 1 (imec1)
...
```

### Recommended Approach (Batch Decompression to Disk)

This matches the NP1.0 pipeline and provides:
- Reusable decompressed data across conversion runs
- Simpler interface (standard SpikeGLX reader after decompression)
- Compatible with existing neuroconv interfaces

**Decompression Flow for NP2.0:**

```
source_folder (ONE cache)          target_folder (scratch disk)
├── raw_ephys_data/                ├── raw_ephys_data/
│   ├── probe00a/                  │   ├── probe00a/
│   │   ├── *.ap.cbin    ─────────→│   │   ├── *.ap.bin
│   │   ├── *.ap.meta              │   │   └── *.ap.meta
│   ├── probe00b/                  │   ├── probe00b/
│   │   ├── *.ap.cbin    ─────────→│   │   ├── *.ap.bin
│   │   ├── *.ap.meta              │   │   └── *.ap.meta
│   ... (12 shank folders)         │   ... (12 shank folders)
```

### Implementation Steps

1. **Extend `decompress_ephys_cbins()`** to handle per-shank folders
   - The current implementation should work as-is (uses `rglob("*.cbin")`)
   - Verify it correctly preserves the probe00a/, probe00b/ folder structure

2. **Create per-shank interfaces** after decompression:
   - One `SpikeGLXRecordingInterface` per shank folder
   - Each shank becomes a separate ElectricalSeries in NWB

3. **Metadata parsing** - reuse from Neo:
   - `neo.rawio.spikeglxrawio.read_meta_file()` (line 567-586)
   - `neo.rawio.spikeglxrawio.extract_stream_info()` (line 589-754)

4. **Probe geometry** - use probeinterface:
   - `probeinterface.read_spikeglx()` handles NP2.0 geometry

### Multi-Shank Probe Detection

In .meta files, look for:
- `imDatPrb_type = 24` → NP2.4 (4-shank)
- `imDatPrb_type = 21` → NP2.0 single-shank

---

## Quick Reference: Most Important Files

| Purpose | File Path |
|---------|-----------|
| **NP1.0 conversion (reference)** | `IBL-to-nwb/src/ibl_to_nwb/conversion/raw.py` |
| **Decompression utility** | `IBL-to-nwb/src/ibl_to_nwb/utils/ephys_decompression.py` |
| IBL spikeglx.Reader | `ibl-neuropixel/src/spikeglx.py` |
| Parsing .meta files (Neo) | `python-neo/neo/rawio/spikeglxrawio.py` |
| NWB interface template | `neuroconv/.../spikeglx/spikeglxdatainterface.py` |
| NWB converter template | `neuroconv/.../spikeglx/spikeglxconverter.py` |

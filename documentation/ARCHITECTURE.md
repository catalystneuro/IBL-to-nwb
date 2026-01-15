# IBL-to-NWB Architecture

This document describes the overall system design and how components fit together.

## System Overview

IBL-to-NWB converts IBL experimental data to NWB format using **NeuroConv**, a flexible data conversion framework. The system is organized around the concept of **Interfaces** (data readers) and **Converters** (orchestrators).

### High-Level Flow

```
IBL Data (ONE API)
    ↓
  [Interface 1]  [Interface 2]  [Interface 3]
    ↓             ↓             ↓
  [Converter] ← orchestrates all interfaces
    ↓
  NWB File (Standardized Output)
```

## Two-Tier Architecture

### Tier 1: Data Interfaces

**Location**: `src/ibl_to_nwb/datainterfaces/`

Each interface is a specialized reader for a single data modality:

```python
class ExampleInterface(BaseIBLDataInterface):
    """Reads one data type (e.g., pose estimation)"""

    def get_metadata(self):
        """Describe the data being converted"""
        return {...}

    def get_data_requirements(self):
        """List exact files/datasets needed"""
        return {...}

    def check_availability(self, one, eid):
        """Check if data exists without downloading"""
        return {...}

    def download_data(self, one, eid, base_path):
        """Download data to local cache"""
        pass

    def add_to_nwbfile(self, nwbfile, metadata):
        """Read data and write to NWB file"""
        pass
```

**Key responsibilities:**
- Declare what data it needs (`get_data_requirements()`)
- Check if data is available (`check_availability()`)
- Download data efficiently (`download_data()`)
- Convert to NWB format (`add_to_nwbfile()`)

**Examples:**
- `IblSortingInterface` - Spike sorting data
- `BrainwideMapTrialsInterface` - Behavioral trials
- `IblPoseEstimationInterface` - Video pose estimation
- `IblNIDQInterface` - Synchronization signals

### Tier 2: Converters

**Location**: `src/ibl_to_nwb/converters/`

Converters orchestrate multiple interfaces to create a complete NWB file:

```python
class BrainwideMapConverter(IblConverter):
    """Coordinates all interfaces for a session"""

    def __init__(self, eid, one, stub_test=False):
        # Initialize all interfaces
        self.interfaces = [
            IblSortingInterface(...),
            BrainwideMapTrialsInterface(...),
            IblPoseEstimationInterface(...),
            # ... more interfaces
        ]

    def convert(self, output_path):
        # Run conversion: interfaces → NWB
        for interface in self.interfaces:
            interface.add_to_nwbfile(nwbfile, metadata)
        # Write to disk
        nwbfile.write(output_path)
```

**Key responsibilities:**
- Initialize interfaces for a session
- Manage metadata across interfaces
- Coordinate data availability checking
- Orchestrate conversion to NWB

**Main converters:**
- `BrainwideMapConverter` - Full session conversion (spike sorting + behavior + video)
- `IblSpikeGlxConverter` - Complex ephys processing (SpikeGLX + probe localization)

## Base Interface Pattern

All interfaces inherit from **`BaseIBLDataInterface`**, enforcing a consistent API:

```
BaseIBLDataInterface
├── get_metadata()           # Static: what's in the data
├── get_data_requirements()  # Static: what files needed
├── check_availability()     # Read-only availability check
├── download_data()          # Download to local cache
└── add_to_nwbfile()        # Convert to NWB
```

**Why this pattern?**
- **Explicit contracts** - Each interface declares what it needs
- **Reusability** - Interfaces can be used in different converters
- **Testability** - Isolated, independent units
- **Provenance** - Clear tracking of data sources
- **Fail-fast** - Early detection of missing data

## Conversion Flow

### Entry Points

The pipeline has two main conversion functions:

```python
# Raw conversion: electrophysiology and raw videos
convert_raw_session(eid, one, stub_test=False, base_path=None)
    # Reads: SpikeGLX ephys, raw videos, synchronization signals
    # Outputs: sub-{subject}_ses-{eid}_desc-raw_ecephys.nwb

# Processed conversion: spike sorting and behavior
convert_processed_session(eid, one, stub_test=False, base_path=None)
    # Reads: Spike sorting, trials, pose, pupil, wheel, licks
    # Outputs: sub-{subject}_ses-{eid}_desc-processed_behavior+ecephys.nwb
```

### Typical Workflow

```
User calls convert_raw_session() or convert_processed_session()
    ↓
Converter created with ONE API instance
    ↓
All interfaces initialized
    ↓
Interface.check_availability() for all interfaces
    ↓ (if available)
Interface.download_data() to local cache
    ↓ (in parallel if configured)
Interface.add_to_nwbfile() for all interfaces
    ↓ (sequentially to shared NWBFile)
Write NWBFile to disk
    ↓
Optional: Upload to DANDI
```

## Data Organization

### ONE API Structure

IBL data is organized hierarchically in the ONE database:

```
ONE
├── Ephys Data
│   ├── raw_ephys_data/
│   │   ├── probe00/
│   │   │   ├── *.ap.cbin        # Action potential band
│   │   │   └── *.lf.cbin        # Local field potential
│   │   └── _spikeglx_*          # Synchronization signals
│   ├── alf/
│   │   ├── probe00/
│   │   │   ├── spikes.times.npy # Spike timing
│   │   │   └── clusters.metrics.pqt
│   │   └── probe01/ (if multi-probe)
│   └── raw_behavior_data/
│       ├── _iblrig_*            # Raw behavior files
│       └── _ibl_*               # Processed behavior
└── Session Metadata
    ├── subject info
    ├── lab info
    └── experiment protocol
```

### Local Cache Structure

After download, data is organized:

```
base_path/
├── session_data/
│   ├── raw_ephys_data/
│   ├── alf/
│   └── raw_behavior_data/
└── nwbfiles/
    ├── sub-{subject}_ses-{eid}_desc-raw_ecephys.nwb
    └── sub-{subject}_ses-{eid}_desc-processed_behavior+ecephys.nwb
```

## Key Design Patterns

### 1. Explicit Requirements

Each interface explicitly declares what data it needs:

```python
def get_data_requirements(self):
    return {
        'trials.intervals.npy': 'alf/',
        'trials.choice.npy': 'alf/',
        'trials.feedback_times.npy': 'alf/',
    }
```

**Benefit:** Automated dependency analysis, predictable downloads.

### 2. Quality Control

Interfaces check data quality and availability:

```python
def check_availability(self, one, eid):
    # Video QC check
    if video_qc_status in ['CRITICAL', 'FAIL']:
        return {
            "available": False,
            "reason": "Video QC failed"
        }

    # File existence check
    if not files_exist:
        return {
            "available": False,
            "reason": "Required files missing"
        }

    return {"available": True}
```

**Benefit:** Graceful degradation, clear error messages.

### 3. Revisions System

Data is versioned for reproducibility:

```python
class IblPoseEstimationInterface(BaseIBLDataInterface):
    REVISION = "2025-05-06"  # Fixed version for reproducibility
```

**Benefit:** Reproducible science, easy to update data pipelines.

### 4. Synchronization

Multi-system timing is handled by ONE API and brainbox:

```python
# Spike times (probe local time)
spike_times_samples = spikes.times

# Convert to session time
from brainbox.io.one import SpikeSortingLoader
ssl = SpikeSortingLoader(one, eid, probe_name)
spike_times_session = ssl.samples2times(spike_times_samples)
```

See [documentation/ibl_concepts/ibl_synchronization.md](ibl_concepts/ibl_synchronization.md) for details.

## Important Abstractions

### Metadata

Metadata flows through the system:

```python
# Session-level metadata
metadata = {
    'NWBFile': {
        'session_description': '...',
        'identifier': eid,
        'session_start_time': session_start,
        ...
    },
    'Icephys': { ... },
    'Behavior': { ... },
}

# Interface-specific metadata merged in
metadata = converter.get_metadata()  # Combines all interfaces
```

### Epochs vs Trials

The NWB file distinguishes between:
- **Epochs** - Time periods of experimental phases (task, passive, etc.)
- **Trials** - Individual behavioral trials with columns for outcomes, etc.

See [documentation/conversion/trials_interface.md](conversion/trials_interface.md).

### Electrode Assignment

Spike units are linked to electrodes:

```
Unit (from spike sorting)
    ↓ (linked via electrode)
Electrode (on Neuropixels probe)
    ↓ (located at)
Brain Region (from histology alignment)
```

## Extension System

IBL-specific data uses custom NWB extensions:

- **ndx-ibl** - Core IBL data types (motor cortex, etc.)
- **ndx-ibl-bwm** - Brain-Wide Map specific types

These are automatically loaded and used by the conversion pipeline.

## Error Handling

The pipeline uses **fail-fast** error handling:

```
Check availability
    ↓ (if not available)
Raise informative exception
    ↓
User sees clear error message
    ↓
Fix data issue or skip interface
    ↓
Re-run conversion
```

**No silent failures** - If data can't be converted, you know immediately why.

## File Operations

### Downloading

Data is downloaded via ONE API on-demand:

```python
one.load_dataset(eid, 'alf/trials.intervals.npy')
# Downloads from Alyx database to local cache
```

Optional decompression for large files:

```python
# Ephys data is stored compressed (.cbin)
# Decompressed on-the-fly during conversion
from ibl_to_nwb.utils.ephys_decompression import decompress_cbin
```

### Writing

NWB files are written using PyNWB:

```python
from pynwb import NWBFile, NWBHDF5IO

nwbfile = NWBFile(...)
io = NWBHDF5IO(filename, mode='w')
io.write(nwbfile)
io.close()
```

Large continuous data uses compression:

```python
# 30 kHz recording for 1 hour → ~50 GB uncompressed
# Compressed to ~5 GB in NWB with gzip encoding
```

## Utilities

Common operations are modularized:

**Atlas Operations** (`utils/atlas.py`):
```python
from ibl_to_nwb.utils.atlas import get_brain_region_for_coordinate
region = get_brain_region_for_coordinate(xyz_microns)
```

**Electrode Setup** (`utils/electrodes.py`):
```python
from ibl_to_nwb.utils.electrodes import get_probe_electrodes
electrodes_table = get_probe_electrodes(probe_type='3B')
```

**Ephys Decompression** (`utils/ephys_decompression.py`):
```python
from ibl_to_nwb.utils.ephys_decompression import decompress_cbin
decompress_cbin(input_bin, output_bin)
```

## Related Documentation

For deeper dives into specific systems:

- **[Synchronization](ibl_concepts/ibl_synchronization.md)** - How multi-system timing works
- **[Conversion Modalities](conversion/conversion_modalities.md)** - Detailed description of each data type
- **[Brain Atlas](ibl_concepts/brain_atlas_hierarchy_guide.md)** - Understanding brain region organization
- **[Passive Task](ibl_concepts/ibl_passive_task.md)** - Passive stimulus protocol
- **[Revisions](conversion/revisions.md)** - Data versioning system

## Testing and Development

### Stub Mode

For rapid iteration, use stub test mode:

```python
convert_raw_session(eid, one, stub_test=True)
# Downloads minimal data, creates small NWB file for testing
```

### Local Testing

Test individual interfaces:

```python
interface = ExampleInterface(one, eid)
assert interface.check_availability()["available"]
metadata = interface.get_metadata()
# ... inspect results
```

### Debugging

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check NWB output:

```python
from pynwb import NWBHDF5IO

with NWBHDF5IO('file.nwb', 'r') as io:
    nwbfile = io.read()
    print(nwbfile)  # Inspect structure
```

## Performance Considerations

### Memory

Large files (30 kHz ephys for 2 hours) require careful handling:

```python
# Don't load entire file into memory
for chunk in read_in_chunks(data_path, chunk_size=1_000_000):
    process(chunk)  # Stream processing

# Use lazy loading in NWB
data = io.read().processing['ephys']['continuous']
# Data not loaded until accessed
```

### Parallel Processing

AWS deployment launches one EC2 instance per session:

- Each instance processes one session independently
- No shared state between instances
- Easy to restart failed sessions

See [documentation/dandi_and_aws/aws_infrastructure.md](dandi_and_aws/aws_infrastructure.md).

### Caching

ONE API caches downloaded data locally:

```bash
# Cache location (system-dependent)
~/.one/  # Linux/macOS
C:\Users\{username}\.one\  # Windows
```

See [documentation/ibl_concepts/one_cache_mismatch_issue.md](ibl_concepts/one_cache_mismatch_issue.md).

---

**Next:** Read [GETTING_STARTED.md](GETTING_STARTED.md) for installation and quick start, or dive into specific documentation in the subdirectories.

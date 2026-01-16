# Conversion Overview

This document explains how data conversions work in IBL-to-NWB and provides an overview of the conversion pipeline.

## Entry Points

The pipeline has two main conversion functions:

### Raw Conversion

```python
from ibl_to_nwb.conversion import convert_raw_session

nwbfile_path = convert_raw_session(
    eid="session-uuid",           # Session ID
    one=one,                       # ONE API instance
    stub_test=False,               # Quick test mode
    base_path="/path/to/data",     # Output location
    overwrite=False,               # Overwrite existing files
    redecompress_ephys=False       # Decompress SpikeGLX data
)
```

**Produces**: `sub-{subject}_ses-{eid}_desc-raw_ecephys.nwb`

**Contains**:
- Raw electrophysiology (SpikeGLX AP/LF bands)
- Raw video streams (3 cameras)
- Synchronization signals (NIDQ)
- Probe locations and electrode information
- Session metadata and epochs

**Location**: `src/ibl_to_nwb/conversion/raw.py`

### Processed Conversion

```python
from ibl_to_nwb.conversion import convert_processed_session

nwbfile_path = convert_processed_session(
    eid="session-uuid",           # Session ID
    one=one,                       # ONE API instance
    stub_test=False,               # Quick test mode
    base_path="/path/to/data"      # Output location
)
```

**Produces**: `sub-{subject}_ses-{eid}_desc-processed_behavior+ecephys.nwb`

**Contains**:
- Spike sorting (units with quality metrics)
- Behavioral trials (choices, rewards, timing)
- Wheel movements
- Lick times
- Pose estimation (video)
- Pupil tracking
- Motion energy
- Passive stimulus events
- Brain region assignments

**Location**: `src/ibl_to_nwb/conversion/processed.py`

## Conversion Pipeline Stages

### Stage 1: Session Metadata

```
↓ Load session info from Alyx REST API
├─ Subject information (species, ID, genotype)
├─ Lab and institution
├─ Experiment protocol
└─ Session timing and timezone
```

### Stage 2: Interface Initialization

```
↓ Create converter with all interfaces
├─ IblSortingInterface (spike sorting)
├─ BrainwideMapTrialsInterface (behavioral trials)
├─ WheelInterface (wheel movement)
├─ IblPoseEstimationInterface (pose tracking)
├─ PupilTrackingInterface (pupil size)
├─ RoiMotionEnergyInterface (motion energy)
├─ IblNIDQInterface (sync signals)
├─ RawVideoInterface (video streams)
└─ ... (more interfaces as needed)
```

### Stage 3: Availability Checking

Each interface checks if its data is available:

```python
for interface in interfaces:
    availability = interface.check_availability(one, eid)
    if not availability["available"]:
        logger.warning(f"Skipping {interface}: {availability['reason']}")
        continue
    # Proceed with this interface
```

**Check includes**:
- File existence in ONE database
- Quality control (video QC, histology quality)
- Revision availability

**No downloads yet** - this is metadata-only checking.

### Stage 4: Data Download

```python
for interface in interfaces:
    if interface.check_availability(one, eid)["available"]:
        interface.download_data(one, eid, base_path)
```

**What happens**:
- ONE API downloads data to local cache
- Large files (ephys) optionally decompressed
- Progress tracking and error reporting

**Efficient downloading**:
- Only downloads required files (declared in `get_data_requirements()`)
- Uses ONE's caching (don't re-download if already local)
- Can decompress large files in parallel

### Stage 5: Conversion to NWB

```python
# Create empty NWBFile
nwbfile = NWBFile(
    session_description="...",
    identifier=eid,
    session_start_time=session_start_time,
    # ... more metadata
)

# Each interface adds its data
for interface in interfaces:
    if interface.check_availability(one, eid)["available"]:
        interface.add_to_nwbfile(nwbfile, metadata)

# Write to disk
io = NWBHDF5IO(output_path, mode='w')
io.write(nwbfile)
io.close()
```

### Stage 6: Upload (Optional)

```bash
# Validate NWB file
dandi validate file.nwb

# Upload to DANDI
dandi upload dandiset/
```

## Data Requirements

Each interface declares exactly what data it needs via `get_data_requirements()`. This declaration is the **single source of truth** that drives both availability checking and downloading:

```python
class ExampleInterface(BaseIBLDataInterface):
    REVISION = "2025-05-06"  # Fixed version for reproducibility

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        return {
            "exact_files_options": {
                "standard": [
                    "alf/probe00/spikes.times.npy",
                    "alf/probe00/spikes.clusters.npy",
                    "alf/probe00/clusters.metrics.pqt",
                ],
            },
        }
```

The conversion pipeline uses this declaration in sequence:

1. **`check_availability()`** - Reads requirements, queries ONE API to verify files exist (no download)
2. **`download_data()`** - Reads requirements, downloads files using the class `REVISION`
3. **`add_to_nwbfile()`** - Loads the same files from cache and converts to NWB

**Format alternatives**: Some interfaces support multiple file formats (e.g., `bwm_format` vs `legacy_format`). The system tries each option until finding one where all files exist.

See [ibl_data_interface_design.md](ibl_data_interface_design.md) for the complete specification of the requirements format.

## Quality Control Integration

Quality checks are integrated at multiple levels:

### Session Level

```python
# Check QC fixtures (precomputed at project start)
bwm_qc_data = load_fixture('bwm_qc.json')
histology_qc_data = load_fixture('bwm_histology_qc.pqt')
```

### Interface Level

```python
class IblPoseEstimationInterface(BaseIBLDataInterface):
    def check_availability(self, one, eid, camera_name):
        # Video QC check
        video_qc = bwm_qc_data[eid][camera_name]
        if video_qc in ['CRITICAL', 'FAIL']:
            return {
                "available": False,
                "reason": f"Video QC failed: {video_qc}"
            }
        # File existence check
        return {"available": True}
```

### Conversion Level

```python
# Interface can filter data during conversion
# E.g., apply likelihood threshold to pose data
pose_data[pose_data['likelihood'] < 0.9] = NaN
```

See [conversion_modalities.md](conversion_modalities.md) for detailed QC by modality.

## Stub Testing

For rapid development/testing without downloading large files:

```python
# Download only metadata, skip large ephys/video
nwbfile_path = convert_raw_session(
    eid="session-uuid",
    one=one,
    stub_test=True    # ← Quick test mode
)
```

**What stub_test does**:
- Skips large continuous data (ephys, video)
- Uses cached local data if available
- Creates minimal NWB file (~10 MB instead of 10 GB)
- ~5 minutes instead of 1-2 hours

**Good for**:
- Testing interface integration
- Debugging metadata issues
- CI/CD testing
- AWS infrastructure testing

## Multi-Probe Sessions

Some sessions have 2+ probes:

```
Session
├─ probe00 (16 electrodes, VIS)
└─ probe01 (64 electrodes, TH)

↓ Conversion

NWB File
├─ electrodes table (80 total electrodes)
├─ units table (550 units from probe00 + 450 from probe01)
└─ icephys processing module
    ├─ raw spike data (both probes)
    └─ spike times (both probes, same session time)
```

**Handling**:
- Each probe is processed independently
- Data from all probes merged in single NWB file
- Unit IDs made globally unique (probe ID encoded)
- All synchronized to session master time (NIDQ)

## Revision System

Interfaces use **fixed revisions** for reproducibility:

```python
class IblSortingInterface(BaseIBLDataInterface):
    REVISION = "2025-05-06"  # Brain-Wide Map standard
```

**Why fixed?**
- Ensures all 459 sessions use identical data versions
- Makes future updates explicit
- Reproducible science

See [revisions.md](revisions.md) for details.

## Error Handling

The pipeline uses **fail-fast** error handling:

```
Check data availability
    ↓ (if missing)
Skip interface + log warning
    ↓ (optional interface)
Continue conversion
    ↓ (if required interface)
Raise informative exception
    ↓
User sees clear error message
```

**Example**:
```
WARNING: Pose estimation data not found for leftCamera (QC: CRITICAL)
WARNING: Skipping IblPoseEstimationInterface
WARNING: Motion energy data not found
INFO: Conversion continuing with available data
INFO: NWB file written with 18/22 modalities
```

No silent failures - you always know what's included.

## Memory Management

Large files require careful handling:

```python
# Continuous data (30 kHz × 384 channels × 7200 seconds = 6.5 GB)
# Streamed to disk, not loaded in memory

# Spike waveforms (80 spikes × 384 channels × 82 samples = 8 MB per unit)
# Loaded per-unit, not all at once
```

**Strategies**:
- Streaming write to NWB (HDF5 chunking)
- Lazy loading (data not read until accessed)
- Parallel processing (multiple probes)

## Performance Tips

### 1. Use Stub Test First

```bash
# 5 minutes to test interface
python -c "from ibl_to_nwb.conversion import convert_raw_session; \
  convert_raw_session(eid='xxx', one=one, stub_test=True)"
```

### 2. Local Caching

```python
# ONE caches data locally (~/.one/)
# Second conversion much faster than first
```

### 3. Parallel Processing

For full dataset (459 sessions):
- AWS EC2 instances (one session per instance)
- 2-4 hours per session
- ~$0.42/hour per instance
- Total cost: ~$600 for full dataset

See [documentation/dandi_and_aws/aws_infrastructure.md](../dandi_and_aws/aws_infrastructure.md).

## Testing Conversions

### Unit Testing

```python
# Test individual interface
from ibl_to_nwb.datainterfaces import IblSortingInterface

interface = IblSortingInterface(eid=eid, pname='probe00', one=one)
assert interface.check_availability()["available"]
metadata = interface.get_metadata()
```

### Integration Testing

```bash
# Test single session conversion
python src/ibl_to_nwb/_scripts/convert_single_bwm_to_nwb.py <session-eid>
```

### End-to-End Testing

```bash
# Test conversion script (batch mode)
python src/ibl_to_nwb/_scripts/convert_bwm_to_nwb.py

# Validate NWB
dandi validate /path/to/file.nwb
```

## Extending the Pipeline

### Adding a New Interface

1. **Create interface class**:
```python
from ibl_to_nwb.datainterfaces import BaseIBLDataInterface

class MyNewInterface(BaseIBLDataInterface):
    REVISION = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        return {
            "exact_files_options": {
                "standard": ["alf/my_data.npy"],
            },
        }

    # check_availability() and download_data() use base class defaults
    # Override only if you need custom logic (e.g., QC checks)

    def add_to_nwbfile(self, nwbfile, metadata):
        pass  # Load data and add to NWB
```

2. **Add to converter**:
```python
# In src/ibl_to_nwb/converters/brainwide_map_converter.py
self.interfaces = [
    # ... existing interfaces
    MyNewInterface(eid, one),  # Add your interface
]
```

3. **Document in conversion_modalities.md**

4. **Add tests**

See [ibl_data_interface_design.md](ibl_data_interface_design.md) for the complete interface contract specification.

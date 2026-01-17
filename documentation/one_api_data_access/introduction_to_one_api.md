# ONE API Data Access Guide

This section documents all methods for loading IBL experimental data using the ONE API and ibllib utilities. Use this guide to choose the right approach for your data access needs.

## Quick Reference

```python
from one.api import ONE
one = ONE()  # Initialize ONE API (required for all data access)
```

**New to IBL data?** Start with the [ALF Data Structure](../ibl_data_organization/alf_data_structure.md) guide to understand how IBL organizes and names files.

## Data Access Methods

IBL data can be accessed at three levels, from lowest to highest:

### 1. Direct ONE API Methods

The fundamental methods for loading IBL data. Most interfaces use these directly.

| Method | Purpose | Return type |
|--------|---------|-------------|
| `one.load_dataset()` | Load a single file | numpy array (or pandas DataFrame for `.pqt` files) |
| `one.load_object()` | Load all files for an ALF object | dict of arrays |
| `one.alyx.rest()` | Query Alyx database directly | JSON/dict |

**`one.load_dataset()`** - Load a single data file:
```python
# Load a single array
timestamps = one.load_dataset(eid, 'wheel.timestamps', collection='alf')
position = one.load_dataset(eid, 'wheel.position', collection='alf')

# With revision
licks = one.load_dataset(eid, 'licks.times', collection='alf', revision='2024-05-06')
```

**`one.load_object()`** - Load all attributes of an ALF object as a dict:
```python
# Load all wheel files at once (position, timestamps)
wheel = one.load_object(eid, 'wheel', collection='alf')
# Returns: {'position': array, 'timestamps': array}

# Load camera object
left_camera = one.load_object(eid, 'leftCamera', collection='alf',
                               attribute=['dlc', 'times'])
```

**Pros**: Simple, direct, no dependencies beyond ONE API, full control over what's loaded
**Cons**: No automatic processing, must handle file organization manually, no convenience features

### 2. High-Level Loaders (brainbox)

Convenience classes that wrap ONE API calls with automatic processing.

| Loader | Module | Data Types | Return type |
|--------|--------|------------|-------------|
| [SessionLoader](session_loader.md) | `brainbox.io.one` | trials, wheel, pose, motion energy, pupil | pandas DataFrame |
| [SpikeSortingLoader](spike_sorting_loader.md) | `brainbox.io.one` | spikes, clusters, channels, raw waveforms | dict of numpy arrays |
| [EphysSessionLoader](ephys_session_loader.md) | `brainbox.io.one` | All behavioral + all probes | dict of DataFrames |

**Pros**: Automatic processing (filtering, interpolation, thresholding), pandas output, handles complexity
**Cons**: Less control, may do processing you don't need, higher-level abstraction

### 3. Raw Data Loaders (ibllib)

For accessing unprocessed source files before IBL's standard processing.

| Module | Data Types | Use Case |
|--------|------------|----------|
| [Raw data loaders](raw_data_loaders.md) | PyBpod, camera, encoder, DAQ | Custom pipelines, debugging |
| [Video utilities](video_data.md) | Video frames, metadata | Frame extraction |

**Pros**: Access to original unprocessed data, full control
**Cons**: Requires understanding of raw file formats, manual timestamp alignment

## Comparison Summary

| Method | Processing | Complexity | When to Use |
|--------|------------|------------|-------------|
| `one.load_dataset()` | None | Low | Single file, simple data |
| `one.load_object()` | None | Low | Multiple related files, no processing needed |
| SessionLoader | Interpolation, filtering, thresholding | Medium | Behavioral data needing processing |
| SpikeSortingLoader | Spike sorter selection, histology alignment | Medium | Ephys data with brain regions |
| Raw loaders | None | High | Debugging, custom pipelines |

## Decision Guide for NWB Conversion

**Which loader should your DataInterface use?**

- **Behavioral interfaces** (trials, wheel, pose, licks): Use [SessionLoader](session_loader.md) - provides pre-processed DataFrames ready for NWB
- **Spike sorting interfaces**: Use [SpikeSortingLoader](spike_sorting_loader.md) - handles spike sorter selection, histology alignment, and channel localization
- **Raw ephys interfaces** (SpikeGLX binary): Use SpikeSortingLoader's `raw_electrophysiology()` for streaming access
- **Custom interfaces requiring raw timestamps**: Use [raw data loaders](raw_data_loaders.md) when you need data before synchronization
- **Video-related interfaces**: Use [video utilities](video_data.md) for frame extraction

**What does IBL-to-NWB use?**

| Interface | Data Loading Method | Rationale |
|-----------|---------------------|-----------|
| **BrainwideMapTrialsInterface** | `SessionLoader.load_trials()` | SessionLoader aggregates trial columns from multiple files into a single DataFrame. Direct ONE would require manually loading and merging ~20 separate trial attribute files. |
| **IblPoseEstimationInterface** | `SessionLoader.load_pose()` | SessionLoader provides likelihood thresholding and consistent timestamp handling across camera views. Direct ONE would require manual filtering of low-confidence points. |
| **IblSortingInterface** | `SpikeSortingLoader.load_spike_sorting()` | SpikeSortingLoader handles spike sorter selection (pykilosort vs iblsorter), histology alignment priority, and channel-to-brain-region mapping. No simpler alternative exists for this complexity. |
| **IblAnatomicalLocalizationInterface** | `SpikeSortingLoader` + AllenAtlas | Requires SpikeSortingLoader for channel locations with histology alignment, plus atlas for region hierarchy lookups. No alternative. |
| **WheelInterface** | Direct ONE: `one.load_object()` | Stores raw wheel position for NWB. Alternative: `SessionLoader.load_wheel()` provides interpolation and filtering, but NWB users may prefer raw data to apply their own processing. |
| **LickInterface** | Direct ONE: `one.load_dataset()` | Simple timestamp array. No SessionLoader method exists for licks. No alternative needed. |
| **PupilTrackingInterface** | Direct ONE: `one.load_object()` | Loads full eye tracking data (position, diameter, etc.). Alternative: `SessionLoader.load_pupil()` only returns pupil diameter, not full tracking data needed for NWB. |
| **RoiMotionEnergyInterface** | Direct ONE: `one.load_object()` | Simple time series. Alternative: `SessionLoader.load_motion_energy()` exists but adds no processing - just wraps the same ONE call. |
| **RawVideoInterface** | Direct ONE: `one.load_object()` | Raw video file metadata. SessionLoader doesn't handle raw videos. No alternative. |
| **PassiveIntervalsInterface** | Direct ONE: `one.load_dataset()` | Passive protocol intervals. Not covered by SessionLoader. No alternative. |
| **PassiveReplayStimInterface** | Direct ONE: `one.load_dataset()` | Passive stimulus replay data. Not covered by SessionLoader. No alternative. |
| **SessionEpochsInterface** | Direct ONE: `one.load_dataset()` | Session epoch boundaries (metadata). Not covered by any loader. No alternative. |
| **IblNIDQInterface** | Direct ONE: `one.load_dataset()` | Raw NIDQ analog data. This is acquisition data, not processed behavioral data. No alternative. |
| **ProbeTrajectoryInterface** | Alyx REST: `one.alyx.rest()` | Probe trajectory metadata from Alyx database. Not file-based data. No alternative. |

## Common Initialization Patterns

### ONE API Setup

```python
from one.api import ONE

# Default (downloads data as needed)
one = ONE()

# Local mode (use existing cache only)
one = ONE(mode='local')

# Specify cache directory
one = ONE(cache_dir='/path/to/cache')
```

### Session Identification

```python
# By experiment ID (UUID)
eid = "your-session-uuid"

# Find sessions by subject/date
eids = one.search(subject='subject_name', date='2023-01-15')

# Get session info
info = one.get_details(eid)
```

### Revision Handling

All high-level loaders support the `revision` parameter for reproducible data access:

```python
from brainbox.io.one import SessionLoader

# Use specific data revision
loader = SessionLoader(one=one, eid=eid, revision="2024-05-06")
```

## Related Documentation

- [ALF Data Structure](../ibl_data_organization/alf_data_structure.md) - Understanding IBL's file naming conventions
- [Brain Atlas Hierarchy](../ibl_science/brain_atlas_hierarchy_guide.md) - Understanding brain region mappings
- [IBL Synchronization](../ibl_science/synchronization.md) - Multi-clock alignment system
- [Conversion Overview](../conversion/conversion_overview.md) - How data flows into NWB format

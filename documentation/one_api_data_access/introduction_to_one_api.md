# ONE API Data Access Guide

This section documents all methods for loading IBL experimental data using the ONE API and ibllib utilities. Use this guide to choose the right approach for your data access needs.

## Quick Reference

```python
from one.api import ONE
one = ONE()  # Initialize ONE API (required for all data access)
```

**New to IBL data?** Start with the [ALF Data Structure](../ibl_data_organization/alf_data_structure.md) guide to understand how IBL organizes and names files.

## Data Access Methods

| Method | Level | Processing | Returns | Best For |
|--------|-------|------------|---------|----------|
| `one.load_dataset()` | Direct ONE | None | numpy array / DataFrame | Single file, simple data |
| `one.load_object()` | Direct ONE | None | dict of arrays | Multiple related files |
| `one.alyx.rest()` | Direct ONE | None | JSON/dict | Database queries |
| [SessionLoader](session_loader.md) | brainbox | Interpolation, filtering, thresholding | DataFrame | Behavioral data |
| [SpikeSortingLoader](spike_sorting_loader.md) | brainbox | Sorter selection, histology alignment | dict of arrays | Ephys with brain regions |
| [EphysSessionLoader](ephys_session_loader.md) | brainbox | Combined behavioral + ephys | dict of DataFrames | Full session analysis |
| [Raw data loaders](raw_data_loaders.md) | ibllib | None | Various | Custom pipelines, debugging |
| [Video utilities](video_data.md) | ibllib | None | Frames, metadata | Frame extraction |

### Direct ONE API Examples

```python
# Load a single array
timestamps = one.load_dataset(eid, 'wheel.timestamps', collection='alf')

# With revision
licks = one.load_dataset(eid, 'licks.times', collection='alf', revision='2024-05-06')

# Load all wheel files at once
wheel = one.load_object(eid, 'wheel', collection='alf')
# Returns: {'position': array, 'timestamps': array}
```

## IBL-to-NWB Interface Mapping

| Interface | Loading Method | Why This Method |
|-----------|----------------|-----------------|
| BrainwideMapTrialsInterface | `SessionLoader.load_trials()` | Aggregates ~20 trial attribute files into one DataFrame |
| IblPoseEstimationInterface | `SessionLoader.load_pose()` | Provides likelihood thresholding across camera views |
| IblSortingInterface | `SpikeSortingLoader` | Handles sorter selection and histology alignment |
| IblAnatomicalLocalizationInterface | `SpikeSortingLoader` + AllenAtlas | Channel locations with region hierarchy |
| WheelInterface | `one.load_object()` | Raw data preferred; users apply own processing |
| LickInterface | `one.load_dataset()` | Simple timestamp array |
| PupilTrackingInterface | `one.load_object()` | Full eye tracking (SessionLoader only returns diameter) |
| RoiMotionEnergyInterface | `one.load_object()` | Simple time series |
| RawVideoInterface | `one.load_object()` | Raw video metadata |
| PassiveIntervalsInterface | `one.load_dataset()` | Not covered by SessionLoader |
| PassiveReplayStimInterface | `one.load_dataset()` | Not covered by SessionLoader |
| SessionEpochsInterface | `one.load_dataset()` | Session metadata |
| IblNIDQInterface | `one.load_dataset()` | Raw acquisition data |
| ProbeTrajectoryInterface | `one.alyx.rest()` | Database metadata, not file-based |

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

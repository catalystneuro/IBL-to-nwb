# ONE API Data Access Guide

This section documents all methods for loading IBL experimental data using the ONE API and ibllib utilities. Use this guide to choose the right loader for your analysis task.

## Quick Reference

```python
from one.api import ONE
one = ONE()  # Initialize ONE API (required for all loaders)
```

**New to IBL data?** Start with the [ALF Data Structure](alf_data_structure.md) guide to understand how IBL organizes and names files.

## Loader Comparison

| Loader | Module | Data Types | Best For |
|--------|--------|------------|----------|
| [SessionLoader](session_loader.md) | `brainbox.io.one` | trials, wheel, pose, motion energy, pupil | Behavioral analysis |
| [SpikeSortingLoader](spike_sorting_loader.md) | `brainbox.io.one` | spikes, clusters, channels, raw waveforms | Single-probe ephys |
| [EphysSessionLoader](ephys_session_loader.md) | `brainbox.io.one` | All behavioral + all probes | Combined analysis |
| [Raw data loaders](raw_data_loaders.md) | `ibllib.io.raw_data_loaders` | PyBpod, camera, encoder, DAQ | Custom pipelines |
| [Video utilities](video_data.md) | `ibllib.io.video` | Video frames, metadata | Frame extraction |

## Pros and Cons

| Loader | Pros | Cons |
|--------|------|------|
| **SessionLoader** | Unified interface, automatic processing, pandas output, lazy loading | No ephys data, single session at a time |
| **SpikeSortingLoader** | Auto spike sorter selection, histology alignment, streaming support | Single probe, must manage separately from behavior |
| **EphysSessionLoader** | Single object for all data (behavior + ephys) | Higher memory usage, slower initialization |
| **Raw data loaders** | Direct file access, no processing overhead, full control | Manual timestamp alignment, no convenience features |
| **Video utilities** | Memory-efficient streaming, frame-by-frame access | Network latency for remote access |

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

- [ALF Data Structure](alf_data_structure.md) - Understanding IBL's file naming conventions
- [Brain Atlas Hierarchy](../ibl_concepts/brain_atlas_hierarchy_guide.md) - Understanding brain region mappings
- [IBL Synchronization](../ibl_concepts/ibl_synchronization.md) - Multi-clock alignment system
- [Conversion Overview](../conversion/conversion_overview.md) - How data flows into NWB format

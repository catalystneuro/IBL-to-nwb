# NWB Conversion

This section documents the IBL-to-NWB conversion pipeline.

## Architecture

IBL-to-NWB converts IBL experimental data to NWB format using **NeuroConv**, a flexible data conversion framework. The system is organized around **Interfaces** (data readers) and **Converters** (orchestrators).

```
IBL Data (ONE API)
    ↓
  [Interface 1]  [Interface 2]  [Interface 3]
    ↓             ↓             ↓
  [Converter] ← orchestrates all interfaces
    ↓
  NWB File (Standardized Output)
```

### Data Interfaces

**Location**: `src/ibl_to_nwb/datainterfaces/`

Each interface is a specialized reader for a single data modality. All inherit from `BaseIBLDataInterface` which enforces a consistent API:

- `get_data_requirements()` - Declare what files needed (source of truth)
- `check_availability()` - Read-only check without downloading
- `download_data()` - Download to local cache
- `add_to_nwbfile()` - Convert data and write to NWB

**Examples**: `IblSortingInterface` (spike sorting), `BrainwideMapTrialsInterface` (behavioral trials), `IblPoseEstimationInterface` (video pose estimation)

### Converters

**Location**: `src/ibl_to_nwb/converters/`

Converters orchestrate multiple interfaces to create a complete NWB file. Main converters:
- `BrainwideMapConverter` - Full session conversion (spike sorting + behavior + video)
- `IblSpikeGlxConverter` - Complex ephys processing (SpikeGLX + probe localization)

## Entry Points

**Raw conversion** (`src/ibl_to_nwb/conversion/raw.py`):
```python
from ibl_to_nwb.conversion import convert_raw_session
convert_raw_session(eid, one, stub_test=False, base_path=None)
```
Produces: `sub-{subject}_ses-{eid}_desc-raw_ecephys.nwb`
Contains: Raw electrophysiology (SpikeGLX), raw videos, sync signals, probe info

**Processed conversion** (`src/ibl_to_nwb/conversion/processed.py`):
```python
from ibl_to_nwb.conversion import convert_processed_session
convert_processed_session(eid, one, stub_test=False, base_path=None)
```
Produces: `sub-{subject}_ses-{eid}_desc-processed_behavior+ecephys.nwb`
Contains: Spike sorting, trials, wheel, licks, pose, pupil, motion energy, brain regions

## Stub Testing

For rapid development without downloading large files:
```python
convert_raw_session(eid, one, stub_test=True)  # ~5 min instead of 1-2 hours
```

## Documents in This Section

- [conversion_overview.md](conversion_overview.md) - Detailed pipeline stages, data requirements flow, QC integration
- [conversion_modalities.md](conversion_modalities.md) - Specific data modalities (behavioral, sensory, ephys) and their interfaces
- [ibl_data_interface_design.md](ibl_data_interface_design.md) - Interface contract specification and `get_data_requirements()` format
- [sorting_interface.md](sorting_interface.md) - Spike sorting interface implementation details
- [trials_interface.md](trials_interface.md) - Behavioral trials interface details

## Related Documentation

- [IBL Science](../ibl_science/) - Brain atlas, synchronization, experimental concepts
- [IBL Data Organization](../ibl_data_organization/) - ALF naming, revisions system
- [ONE API Data Access](../one_api_data_access/) - SessionLoader, SpikeSortingLoader, data access methods
- [DANDI & AWS](../dandi_and_aws/) - Upload to DANDI, distributed processing

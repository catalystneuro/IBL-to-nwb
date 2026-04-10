# NWB Conversion

This section documents how to convert IBL data to NWB format using the IBL-to-NWB pipeline.

## Architecture

IBL-to-NWB uses **NeuroConv**, a flexible data conversion framework. The system is organized around **Interfaces** (data readers) and **Converters** (orchestrators):

```
IBL Data (ONE API)
    ↓
  [Interface 1]  [Interface 2]  [Interface 3]
    ↓             ↓             ↓
  [Converter] ← orchestrates all interfaces
    ↓
  NWB File (Standardized Output)
```

- **Interfaces** (`src/ibl_to_nwb/datainterfaces/`) - Specialized readers for individual data modalities (spike sorting, trials, pose, etc.)
- **Converters** (`src/ibl_to_nwb/converters/`) - Orchestrate multiple interfaces to create complete NWB files

## Documents in This Section

- [conversion_overview.md](conversion_overview.md) - How to run conversions: scripts, Python API, pipeline stages, QC integration
- [conversion_modalities.md](conversion_modalities.md) - Available data modalities (behavioral, sensory, ephys) and their interfaces
- [ibl_data_interface_design.md](ibl_data_interface_design.md) - Interface contract specification for writing new interfaces
- [sorting_interface.md](sorting_interface.md) - Spike sorting interface implementation details
- [trials_interface.md](trials_interface.md) - Behavioral trials interface details

## Related Sections

- [IBL Science](../ibl_science/) - Brain atlas, synchronization, experimental concepts
- [IBL Data Organization](../ibl_data_organization/) - ALF naming, revisions system
- [ONE API Data Access](../one_api_data_access/) - Data loading methods
- [DANDI & AWS](../dandi_and_aws/) - Upload to DANDI, distributed processing

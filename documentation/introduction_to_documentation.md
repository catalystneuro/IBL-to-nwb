# Documentation Guide

IBL-to-NWB is a data conversion pipeline that transforms International Brain Laboratory (IBL) experimental data into Neurodata Without Borders (NWB) format. This documentation is organized into six sections by topic.

## Getting Started

**New to the project?** Start here:
1. [conversion/introduction_to_conversion.md](conversion/introduction_to_conversion.md) - System overview: Interfaces, Converters, and the NeuroConv framework
2. [conversion/conversion_overview.md](conversion/conversion_overview.md) - How data flows through the conversion pipeline

## Documentation Sections

### [IBL Science](ibl_science/)
Experimental and scientific foundations of IBL data.

- [introduction_to_ibl_science.md](ibl_science/introduction_to_ibl_science.md) - Section overview
- [brain_atlas_hierarchy_guide.md](ibl_science/brain_atlas_hierarchy_guide.md) - Brain region mappings (Allen CCF, Beryl, Cosmos)
- [probe_insertion_and_localization.md](ibl_science/probe_insertion_and_localization.md) - Histology quality and electrode coordinates
- [synchronization.md](ibl_science/synchronization.md) - Multi-clock alignment system
- [wheel_data.md](ibl_science/wheel_data.md) - Rotary encoder wheel behavior
- [passive_task.md](ibl_science/passive_task.md) - Passive replay protocol
- [audio_stimuli.md](ibl_science/audio_stimuli.md) - Go cues and audio timing

### [IBL Data Organization](ibl_data_organization/)
How IBL structures and versions data.

- [introduction_to_data_organization.md](ibl_data_organization/introduction_to_data_organization.md) - Section overview
- [alf_data_structure.md](ibl_data_organization/alf_data_structure.md) - ALF naming convention
- [revisions_system.md](ibl_data_organization/revisions_system.md) - Data versioning and revision tags

### [ONE API Data Access](one_api_data_access/)
Loading IBL data using the ONE API and ibllib utilities.

- [introduction_to_one_api.md](one_api_data_access/introduction_to_one_api.md) - Section overview and loader comparison
- [session_loader.md](one_api_data_access/session_loader.md) - Loading behavioral data
- [spike_sorting_loader.md](one_api_data_access/spike_sorting_loader.md) - Loading ephys data
- [ephys_session_loader.md](one_api_data_access/ephys_session_loader.md) - Loading all data at once
- [raw_data_loaders.md](one_api_data_access/raw_data_loaders.md) - Raw data access
- [video_data.md](one_api_data_access/video_data.md) - Video frame extraction
- [one_api_revision_behavior.md](one_api_data_access/one_api_revision_behavior.md) - How API methods handle revisions

### [NWB Conversion](conversion/)
Converting IBL data to NWB format.

- [introduction_to_conversion.md](conversion/introduction_to_conversion.md) - Architecture overview
- [conversion_overview.md](conversion/conversion_overview.md) - Pipeline stages and workflows
- [conversion_modalities.md](conversion/conversion_modalities.md) - Available data modalities
- [ibl_data_interface_design.md](conversion/ibl_data_interface_design.md) - Interface contract specification
- [sorting_interface.md](conversion/sorting_interface.md) - Spike sorting interface details
- [trials_interface.md](conversion/trials_interface.md) - Behavioral trials interface details

### [DANDI & AWS](dandi_and_aws/)
Cloud infrastructure for uploads and distributed processing.

- [introduction_to_infrastructure.md](dandi_and_aws/introduction_to_infrastructure.md) - Section overview
- [aws_infrastructure.md](dandi_and_aws/aws_infrastructure.md) - Running conversions on AWS EC2
- [dandi_file_patterns.md](dandi_and_aws/dandi_file_patterns.md) - DANDI file naming conventions

### [Development](development/)
Tools, debugging, and technical deep dives.

- [introduction_to_development.md](development/introduction_to_development.md) - Section overview
- [troubleshooting.md](development/troubleshooting.md) - Common issues and solutions
- [nidq_timing_details.md](development/nidq_timing_details.md) - NIDQ synchronization details
- [pose_video_widget.md](development/pose_video_widget.md) - Pose visualization tool
- [probe_slice_visualization_guide.md](development/probe_slice_visualization_guide.md) - Probe trajectory visualization
- [insertion_and_localization_status_nwb.md](development/insertion_and_localization_status_nwb.md) - NWB representation details

## Quick Reference

| Task | Document |
|------|----------|
| Install and run first conversion | [README.md](../README.md) |
| Understand conversion architecture | [introduction_to_conversion.md](conversion/introduction_to_conversion.md) |
| Find brain region for electrode | [brain_atlas_hierarchy_guide.md](ibl_science/brain_atlas_hierarchy_guide.md) |
| Load spike sorting data | [spike_sorting_loader.md](one_api_data_access/spike_sorting_loader.md) |
| Understand ALF file names | [alf_data_structure.md](ibl_data_organization/alf_data_structure.md) |
| Run distributed conversions | [aws_infrastructure.md](dandi_and_aws/aws_infrastructure.md) |
| Debug timing issues | [nidq_timing_details.md](development/nidq_timing_details.md) |

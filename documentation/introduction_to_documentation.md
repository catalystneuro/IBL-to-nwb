# Documentation Guide

IBL-to-NWB is a data conversion pipeline that transforms International Brain Laboratory (IBL) experimental data into Neurodata Without Borders (NWB) format. This documentation is organized into six sections by topic.

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
- [roi_motion_energy.md](ibl_science/roi_motion_energy.md) - Motion energy from video ROIs
- [pupil_tracking.md](ibl_science/pupil_tracking.md) - Pupil diameter tracking from video
- [lick_detection.md](ibl_science/lick_detection.md) - Lick event detection from pose estimation

### [IBL Data Organization](ibl_data_organization/)
How IBL structures and versions data.

- [introduction_to_data_organization.md](ibl_data_organization/introduction_to_data_organization.md) - Section overview
- [alf_data_structure.md](ibl_data_organization/alf_data_structure.md) - ALF naming convention
- [revisions_system.md](ibl_data_organization/revisions_system.md) - Data versioning and revision tags
- [waveform_data.md](ibl_data_organization/waveform_data.md) - Waveform data format

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
- [path_handling.md](conversion/path_handling.md) - File path handling and data requirements

### [DANDI & AWS](dandi_and_aws/)
Cloud infrastructure for uploads and distributed processing.

- [introduction_to_infrastructure.md](dandi_and_aws/introduction_to_infrastructure.md) - Section overview
- [AWS README](../src/ibl_to_nwb/_aws/README.md) - Running conversions on AWS EC2
- [dandi_file_patterns.md](dandi_and_aws/dandi_file_patterns.md) - DANDI file naming conventions

### [Development](development/)
Tools, debugging, and technical deep dives.

- [introduction_to_development.md](development/introduction_to_development.md) - Section overview
- [lock_files.md](development/lock_files.md) - Reproducing the conversion environment
- [nidq_timing_details.md](development/nidq_timing_details.md) - NIDQ synchronization details
- [probe_slice_visualization_guide.md](development/probe_slice_visualization_guide.md) - Probe trajectory visualization
- [one_api_bug_with_caching.md](development/one_api_bug_with_caching.md) - Known ONE API caching issues
- [hdmf_experimental_namespace_bug.md](development/hdmf_experimental_namespace_bug.md) - HDMF experimental namespace issue
- [waveform_sampling_rate_bug.md](development/waveform_sampling_rate_bug.md) - Waveform sampling rate bug
- [steinmetz_trouble_sessions_patch.md](development/steinmetz_trouble_sessions_patch.md) - Steinmetz session patches
- [witten_trouble_session_patch.md](development/witten_trouble_session_patch.md) - Witten session patches

### [Neuropixels 2](neuropixels_2/)
Neuropixels 2.0 multi-shank conversion.

- [neuropixels_2.md](neuropixels_2/neuropixels_2.md) - NP2 conversion overview, caveats, and how to run
- [neuropixels_2.ipynb](https://github.com/catalystneuro/IBL-to-nwb/blob/main/notebooks/neuropixels_2.ipynb) - Full walkthrough notebook (rendered on GitHub)

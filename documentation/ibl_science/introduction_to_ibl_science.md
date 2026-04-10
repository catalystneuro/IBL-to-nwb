# IBL Science

This section documents the scientific and experimental foundations of IBL data. Understanding these concepts helps you interpret the data correctly, whether you're analyzing NWB files or working on the conversion pipeline.

## Overview

The International Brain Laboratory (IBL) is a collaboration studying the neural basis of decision-making. The experiment uses a standardized behavioral task across multiple labs, with Neuropixels recordings synchronized to visual stimuli, audio cues, and behavioral responses.

## Documents in This Section

### Brain Anatomy

- [Brain Atlas Hierarchy Guide](brain_atlas_hierarchy_guide.md) - The Allen CCF hierarchy, Beryl and Cosmos mappings, and how to work with brain region labels
- [Probe Insertion and Localization](probe_insertion_and_localization.md) - How probes are inserted, histology quality levels, and coordinate systems for electrode positions

### Behavioral Task

- [Wheel Data](wheel_data.md) - The rotary encoder wheel used for behavioral responses
- [Passive Task](passive_task.md) - The passive replay protocol run after the main task
- [Audio Stimuli](audio_stimuli.md) - Go cues, error tones, and audio stimulus timing

### Video-Derived Behavioral Metrics

- [ROI Motion Energy](roi_motion_energy.md) - Scalar movement metric from video regions, used to separate movement-related from task-related neural activity
- [Pupil Tracking](pupil_tracking.md) - Pupil diameter measurements indicating arousal and cognitive state
- [Lick Detection](lick_detection.md) - Lick event timestamps from tongue pose estimation

### Technical Infrastructure

- [Synchronization](synchronization.md) - The multi-clock system that aligns neural recordings, video, and behavior across independent devices

## Key Concepts

### The IBL Task

IBL uses a **two-alternative forced-choice (2AFC) task**:
1. Mouse fixates on center position (wheel still)
2. Visual grating appears on left or right
3. Mouse turns wheel to bring grating to center
4. Correct responses rewarded with water

### Brain-Wide Map Project

The Brain-Wide Map (BWM) dataset includes 459 sessions from multiple labs, targeting brain regions across the entire mouse brain. This is the primary dataset being converted to NWB format.

### Histology Quality

Probe localization quality varies by session:
- **Resolved**: Best quality - histology verified with automated tools
- **Aligned**: Good quality - manually aligned to histology
- **Traced**: Lower quality - probe track traced but not aligned
- **None**: No histology available

## Related Sections

- [IBL Data Organization](../ibl_data_organization/introduction_to_data_organization.md) - How data is structured (ALF, revisions)
- [ONE API Data Access](../one_api_data_access/introduction_to_one_api.md) - How to load this data
- [NWB Conversion](../conversion/introduction_to_conversion.md) - Converting to NWB format

# IBL Data Organization

This section documents how IBL organizes and versions experimental data. Understanding these concepts is essential for working with IBL data, whether you're loading it through the ONE API or converting it to NWB format.

## Overview

IBL uses a structured system for organizing data:

1. **ALF (Alyx File) naming convention** - A hierarchical file naming pattern that encodes metadata directly in file paths
2. **Revisions** - Version control for processed data, enabling reproducible science
3. **Collections** - Logical groupings of related files (e.g., `alf/`, `raw_ephys_data/`)

## Documents in This Section

- [ALF Data Structure](alf_data_structure.md) - The foundational naming convention: how files are named, what each component means, and how to parse ALF paths
- [Revisions System](revisions_system.md) - How IBL versions processed data and what revision tags mean for data reproducibility

## How This Relates to Other Sections

- **ONE API Data Access** - Uses ALF naming to load data; see [introduction_to_one_api.md](../one_api_data_access/introduction_to_one_api.md) for loading patterns
- **IBL Science** - Explains the experimental context that produces this data; see [introduction_to_ibl_science.md](../ibl_science/introduction_to_ibl_science.md)
- **NWB Conversion** - Converts ALF-organized data to NWB format; see [introduction_to_conversion.md](../conversion/introduction_to_conversion.md)

## Key Concepts

### ALF Naming Pattern

```
subject/date/number/collection/(#revision#/)?_namespace_object.attribute.extension
```

Example: `KS014/2022-03-21/001/alf/#2024-05-06#/_ibl_trials.choice.npy`

### Revisions

Revisions are ISO-date tags (e.g., `#2024-05-06#`) that mark specific versions of processed data:
- **Spike sorting** is 100% tagged with `#2024-05-06#` for Brain-Wide Map
- **Behavioral data** (trials, wheel) is mostly untagged
- The ONE API's `load_object()` uses smart fallback to find the best available version

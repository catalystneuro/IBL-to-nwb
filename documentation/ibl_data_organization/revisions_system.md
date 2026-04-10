# IBL Data Revisions System

## Overview

IBL uses **revisions** (ISO dates like `"2024-05-06"`) to track dataset versions. Revisions enable reproducible science by allowing researchers to reference specific versions of processed data.

## How Revisions Work

### Revision Format

Revisions are encoded as directory names in the file path, enclosed in pound signs:

```
alf/#2024-05-06#/spikes.times.npy
     └──revision──┘
```

- Format: `#revision_name#/`
- Common formats: dates (`#2024-05-06#`), versions (`#v1.0.0#`), algorithm names (`#kilosort_3.0#`)
- Revisions are ordered lexicographically

### Brain-Wide Map Revision

The standard revision for Brain-Wide Map data is **`2024-05-06`** (also written as `2025-05-06` in some contexts).

## What Data Has Revision Tags?

Not all IBL data is tagged with revisions. Tags are added when data is **corrected or reprocessed**, not when originally created.

| Data Type | Has Tags? | Typical Tag | Prevalence | Notes |
|-----------|-----------|-------------|------------|-------|
| **Spike sorting** (`spikes.*`, `clusters.*`) | Yes | `#2024-05-06#` | 100% | All BWM sessions consistently tagged |
| **Channels/Histology** (`channels.*`) | Yes | `#2024-05-06#` | 100% | Tied to spike sorting version |
| **Trials** | Mostly No | `#2024-02-20#` (rare) | ~few % | Most files untagged |
| **Wheel** | Mixed | `#2024-05-06#` | ~13% | Some sessions have tags |
| **Licks** | No | None | 0% | No tags found |
| **Passive periods** | No | None | 0% | No tags found |
| **Pose estimation** | Mixed | `#2022-01-28#` (DLC) | Varies | DLC has tags, Lightning Pose may not |
| **Videos** | No | None | 0% | Despite timestamp corrections |

### Why The Inconsistency?

**Key Principle:** Revision tags are added when files are **corrected/reprocessed**, not when originally created.

| Scenario | Gets Revision Tag? | Example |
|----------|-------------------|---------|
| **Full dataset reprocessing** | Yes | Spike sorting 2024-05-06: ALL sessions tagged |
| **Targeted corrections** | Yes (only corrected sessions) | Wheel polarity fixes: ~62 sessions (~13%) tagged |
| **Original uncorrected data** | No | Most wheel data: remains untagged |
| **In-place updates** | No | Some corrections replace files without new tags |

**Why wheel data is inconsistent:**
- Sessions that needed polarity corrections got `#2024-05-06#` tags
- Sessions that were already correct remain untagged
- **Both represent current/correct data**, just with different tagging history

## Practical Implications

### When to Filter by Revision

| Data Type | Can Filter by Revision? | Reason |
|-----------|------------------------|--------|
| Spike sorting | Yes | 100% consistently tagged |
| Behavioral data | No | Would exclude most valid data |
| Video/pose | No | Inconsistent tagging |

### Pattern for Code

Only data types that were **universally reprocessed** can use revision filtering. For mixed data:
- Use smart fallback: try with revision, fall back to latest available
- This matches the ONE API's `load_object()` behavior

## Example: Session File Distribution

Investigation of session `c7bd79c9-c47e-4ea5-aea3-74dda991b48e`:

```
Files by revision tag:
  2021-12-10:   2 files
  2022-01-28:   9 files  (DLC pose estimation)
  2022-10-31:   1 file
  2023-04-20:   1 file
  2024-02-20:   1 file   (one trials file)
  2024-05-06:  70 files  (SPIKE SORTING + CHANNELS)
  2025-06-01:   2 files
  2025-06-18:   2 files

PLUS: 173 files with NO revision tag
```

## Related Documentation

- [ALF Data Structure](alf_data_structure.md) - How revisions fit into file paths
- [ONE API Revision Behavior](../one_api_data_access/one_api_revision_behavior.md) - How API methods handle revisions
- [Conversion Overview](../conversion/conversion_overview.md) - How revisions are used in NWB conversion

# ONE API Revision Behavior

This document explains how different ONE API methods handle the `revision` parameter. Understanding these differences is critical for writing correct data loading code.

## Quick Reference

| Method | Behavior | Use Case |
|--------|----------|----------|
| `list_datasets()` | **STRICT FILTER** | Check what tagged data exists |
| `load_dataset()` | **SMART FALLBACK** | Load single file |
| `load_object()` | **SMART FALLBACK** | Load multi-file object |
| `SessionLoader` | **SMART FALLBACK** | Load behavioral data |
| `SpikeSortingLoader` | **SMART FALLBACK** | Load ephys data |

## Detailed Behavior by Method

### `one.list_datasets(eid, revision="2024-05-06")`

**Behavior:** **STRICT FILTERING** - Only returns datasets with exact matching revision tag

```python
datasets = one.list_datasets(eid, revision="2024-05-06")
# Returns ONLY files with #2024-05-06# tag in their path
# Excludes files with different tags or no tags
```

**Use case:** Discovering what specific revision data exists

**Problem:** Excludes all data without that exact tag - most behavioral data!

### `one.load_dataset(eid, dataset, revision="2024-05-06")`

**Behavior:** **SMART FALLBACK** - Tries exact match, falls back to latest

From ONE documentation:
> "The dataset revision (typically an ISO date). If no exact match, the previous revision (ordered lexicographically) is returned."

```python
# Even if 'trials.intervals.npy' doesn't have #2024-05-06# tag,
# this will successfully load the latest available version
data = one.load_dataset(eid, 'alf/trials.intervals.npy', revision="2024-05-06")
```

### `one.load_object(eid, obj="trials", revision="2024-05-06")`

**Behavior:** **SMART FALLBACK** - Same as `load_dataset()`

```python
# Loads 'trials' object even if files don't have #2024-05-06# tags
# Falls back to latest available revision
trials = one.load_object(eid, 'trials', collection='alf', revision="2024-05-06")
```

## High-Level Loaders

### `SessionLoader` (brainbox.io.one)

**Behavior:** Uses `one.load_object()` internally - **SMART FALLBACK**

```python
from brainbox.io.one import SessionLoader
sl = SessionLoader(one=one, eid=eid)

# Internally calls one.load_object() with revision handling
trials = sl.load_trials(revision="2024-05-06")  # Falls back if needed
wheel = sl.load_wheel(revision="2024-05-06")    # Falls back if needed
```

### `SpikeSortingLoader` (brainbox.io.one)

**Behavior:** Uses `one.load_object()` internally - **SMART FALLBACK**

```python
from brainbox.io.one import SpikeSortingLoader

# Pass revision in constructor
ssl = SpikeSortingLoader(pid=pid, eid=eid, pname=pname, one=one, revision="2024-05-06")

# Or pass when loading
ssl = SpikeSortingLoader(pid=pid, eid=eid, pname=pname, one=one)
spikes, clusters, channels = ssl.load_spike_sorting(revision="2024-05-06")
```

The fallback behavior means it works even if some files don't have the exact revision tag.

## The Inconsistency Problem

### Why This Matters for `check_availability()`

The inconsistency between `list_datasets()` (strict) and loading methods (smart fallback) causes problems:

```python
# In check_availability() - using list_datasets()
datasets = one.list_datasets(eid, revision="2024-05-06")  # STRICT - might be empty!

# In download_data() - using SessionLoader
trials = SessionLoader.load_trials(revision="2024-05-06")  # SMART - succeeds!
```

**Result:** `check_availability()` might report data as missing even though `download_data()` can successfully load it!

### Example: What `list_datasets()` Returns

If we call:
```python
one.list_datasets(eid, revision="2024-05-06")
```

We get:
- Spike sorting files (70 files with `#2024-05-06#` tag)
- Trials files (most have no tag - **excluded!**)
- Wheel files (no tags - **excluded!**)
- Video files (no tags - **excluded!**)

## Solution Strategies

### Option 1: No Revision Filtering in `check_availability()`

```python
# In base class check_availability()
available_datasets = one.list_datasets(eid)  # No revision parameter
```

**Pros:** Works for all data types, matches `load_object` behavior
**Cons:** Can't verify specific revision exists before download

### Option 2: Different REVISION per Interface

```python
# Interfaces with tagged data
IblSortingInterface.REVISION = "2024-05-06"

# Interfaces with untagged data
BrainwideMapTrialsInterface.REVISION = None
WheelInterface.REVISION = None
```

**Pros:** Semantically correct
**Cons:** Requires determining REVISION for each interface

### Option 3: Try-Both Strategy (Recommended)

```python
def check_availability(cls, one, eid, revision=None, **kwargs):
    requirements = cls.get_data_requirements(**kwargs)

    if revision is None:
        revision = cls.REVISION

    # Try with revision first (if specified)
    available_datasets = []
    if revision is not None:
        available_datasets = one.list_datasets(eid, revision=revision)

    # If no datasets found with revision, try without filtering
    if len(available_datasets) == 0:
        available_datasets = one.list_datasets(eid)

    # ... rest of matching logic
```

**Pros:**
- Mimics `load_object()` smart fallback behavior
- Works for all data types (universally tagged or mixed)
- Single logical approach for all interfaces

**Cons:**
- Potentially two API calls per session

## Recommendation

Use the **try-both strategy** because:

1. **Matches download behavior:** Since `SessionLoader`, `SpikeSortingLoader`, and `load_object()` all use smart fallback, `check_availability()` should too
2. **Handles all cases:**
   - Spike sorting (100% tagged) - Found with revision filter
   - Wheel (13% tagged) - Found with fallback
   - Trials (mostly untagged) - Found with fallback
3. **Keeps REVISION meaningful:** Can still document which revision was processed

## Related Documentation

- [Revisions System](../ibl_data_organization/revisions_system.md) - What revisions are and how data is tagged
- [Session Loader](session_loader.md) - High-level behavioral data loading
- [Spike Sorting Loader](spike_sorting_loader.md) - High-level ephys data loading

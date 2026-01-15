# Understanding ONE API Revisions in IBL Data

## Overview

The ONE API uses **revisions** (ISO dates like `"2024-05-06"`) to track dataset versions. However, understanding how revisions work requires distinguishing between the API behavior and the actual data organization.

## How ONE API Handles Revisions

### Overview of Revision Behavior

Different ONE API methods handle the `revision` parameter differently:

| Method | Behavior | Use Case |
|--------|----------|----------|
| `list_datasets()` | **STRICT FILTER** | Check availability |
| `load_dataset()` | **SMART FALLBACK** | Load single file |
| `load_object()` | **SMART FALLBACK** | Load multi-file object |

### Detailed Behavior by Method

#### 1. `one.list_datasets(eid, revision="2024-05-06")`

**Behavior:** **STRICT FILTERING** - Only returns datasets with exact matching revision tag

```python
datasets = one.list_datasets(eid, revision="2024-05-06")
# Returns ONLY files with #2024-05-06# tag in their path
# Excludes files with different tags or no tags
```

**Use case:** Discovering what specific revision data exists
**Problem:** Excludes all data without that exact tag

#### 2. `one.load_dataset(eid, dataset, revision="2024-05-06")`

**Behavior:** **SMART FALLBACK** - Tries exact match, falls back to latest

**From ONE documentation:**
> "The dataset revision (typically an ISO date). If no exact match, the previous revision (ordered lexicographically) is returned."

```python
# Even if 'trials.intervals.npy' doesn't have #2024-05-06# tag,
# this will successfully load the latest available version
data = one.load_dataset(eid, 'alf/trials.intervals.npy', revision="2024-05-06")
```

#### 3. `one.load_object(eid, obj="trials", revision="2024-05-06")`

**Behavior:** **SMART FALLBACK** - Same as `load_dataset()`

```python
# Loads 'trials' object even if files don't have #2024-05-06# tags
# Falls back to latest available revision
trials = one.load_object(eid, 'trials', collection='alf', revision="2024-05-06")
```

### IBL-Specific Loaders

#### 4. `SessionLoader` (brainbox.io.one)

**Behavior:** Uses `one.load_object()` internally → **SMART FALLBACK**

```python
from brainbox.io.one import SessionLoader
sl = SessionLoader(one=one, eid=eid)

# Internally calls one.load_object() with revision handling
trials = sl.load_trials(revision="2024-05-06")  # Falls back if needed
wheel = sl.load_wheel(revision="2024-05-06")    # Falls back if needed
```

**Key Point:** `SessionLoader` accepts `revision` parameter and passes it to `load_object()`, so it has smart fallback behavior.

#### 5. `SpikeSortingLoader` (brainbox.io.one)

**Behavior:** Uses `one.load_object()` internally → **SMART FALLBACK**

```python
from brainbox.io.one import SpikeSortingLoader

# Pass revision in constructor
ssl = SpikeSortingLoader(pid=pid, eid=eid, pname=pname, one=one, revision="2024-05-06")

# Or pass when loading
ssl = SpikeSortingLoader(pid=pid, eid=eid, pname=pname, one=one)
spikes, clusters, channels = ssl.load_spike_sorting(revision="2024-05-06")
```

**Key Point:** `SpikeSortingLoader` stores `revision` as instance attribute and uses it for all `one.load_object()` calls. The fallback behavior means it works even if some files don't have the exact revision.

### Why This Matters for check_availability()

The inconsistency causes problems:

```python
# In check_availability() - using list_datasets()
datasets = one.list_datasets(eid, revision="2024-05-06")  # STRICT - might be empty!

# In download_data() - using SessionLoader
trials = SessionLoader.load_trials(revision="2024-05-06")  # SMART - succeeds!
```

**Result:** `check_availability()` might report data as missing even though `download_data()` can successfully load it!

## Actual IBL Data Organization

### Investigation of Session `c7bd79c9-c47e-4ea5-aea3-74dda991b48e`

When examining actual files, we found:

```
Files by revision tag:
  2021-12-10:   2 files
  2022-01-28:   9 files  (DLC pose estimation)
  2022-10-31:   1 file
  2023-04-20:   1 file
  2024-02-20:   1 file   (one trials file)
  2024-05-06:  70 files  (SPIKE SORTING + CHANNELS!)
  2025-06-01:   2 files
  2025-06-18:   2 files

PLUS: 173 files with NO revision tag (empty string '')
```

### What Data Has Revision Tags?

| Data Type | Has Tags? | Typical Tag | Prevalence | Notes |
|-----------|-----------|-------------|------------|-------|
| **Spike sorting** (`spikes.*`, `clusters.*`) | ✓ YES | `#2024-05-06#` | 100% | All BWM sessions consistently tagged |
| **Channels/Histology** (`channels.*`) | ✓ YES | `#2024-05-06#` | 100% | Tied to spike sorting version |
| **Trials** | ✗ MOSTLY NO | `#2024-02-20#` (rare) | ~few % | Most files untagged |
| **Wheel** | ⚠️ **MIXED** | `#2024-05-06#` | **~13%** | **Some files in some sessions!** |
| **Licks** | ✗ NO | None | 0% | No tags found |
| **Passive periods** | ✗ NO | None | 0% | No tags found |
| **Pose estimation** | ✓ MIXED | `#2022-01-28#` (DLC) | Varies | DLC has tags, Lightning Pose may not |
| **Videos** | ✗ NO | None | 0% | Despite 2024-02-15 timestamp corrections |

### Updated Finding: Wheel Data DOES Have Revision Tags!

**From sampling 23 sessions (every 20th from 459 total):**
- 3 sessions (13%) have SOME wheel files with `#2024-05-06#` tags
- 20 sessions (87%) have NO wheel revision tags

**Example from session `283ecb4c-e529-409c-9f0a-8ea5191dcf50`:**
```
✓ alf/#2024-05-06#/_ibl_wheel.position.npy         (TAGGED)
✓ alf/#2024-05-06#/_ibl_wheelMoves.peakAmplitude.npy (TAGGED)
✗ alf/_ibl_wheel.timestamps.npy                     (NOT TAGGED)
✗ alf/_ibl_wheelMoves.intervals.npy                 (NOT TAGGED)
```

**Key Insight:** Even within a single session, wheel data is a **mix** of tagged and untagged files!

## Why The Confusion?

### The Revision Tagging Pattern: Corrections Get Tags

**Key Principle:** Revision tags are added when files are **corrected/reprocessed**, not when originally created.

| Scenario | Gets Revision Tag? | Example |
|----------|-------------------|---------|
| **Full dataset reprocessing** | ✓ YES | Spike sorting 2024-05-15: ALL sessions tagged |
| **Targeted corrections** | ✓ YES (only corrected sessions) | Wheel polarity fixes: ~62 sessions (~13%) tagged |
| **Original uncorrected data** | ✗ NO | Most wheel data: remains untagged |
| **In-place updates** | ✗ NO | Some corrections replace files without new tags |

**Why wheel data is inconsistent:**
- Sessions that needed polarity corrections → Files got `#2024-05-06#` tags
- Sessions that were already correct → Files remain untagged
- **Both represent current/correct data**, just with different tagging history

### Implications for Code

1. **Spike sorting (100% tagged):** Can safely filter by `revision="2024-05-06"`
2. **Wheel (13% tagged):** CANNOT filter by revision - would exclude 87% of valid data
3. **Trials (mostly untagged):** CANNOT filter by revision - would exclude most data
4. **Pattern:** Only data types that were **universally reprocessed** can use revision filtering

## The Problem This Creates

### For `check_availability()`

If we call:
```python
one.list_datasets(eid, revision="2024-05-06")
```

We get:
- ✓ Spike sorting files (70 files with #2024-05-06# tag)
- ✗ Trials files (most have no tag → excluded!)
- ✗ Wheel files (no tags → excluded!)
- ✗ Video files (no tags → excluded!)

**Result:** The diagnose script reports everything as missing except spike sorting!

### For `download_data()` and Loading

If we call:
```python
one.load_object(eid, obj="trials", revision="2024-05-06")
```

ONE's smart fallback handles this:
- Tries to find trials with `#2024-05-06#` tag
- Doesn't find it
- Falls back to latest available version
- **Successfully loads the data!**

## Solution Options

### Option 1: No Revision Filtering in check_availability() (CURRENT)

```python
# In base class check_availability()
available_datasets = one.list_datasets(eid)  # No revision parameter
```

**Pros:**
- Works for all data types
- Matches load_object behavior (gets latest)
- Simple and consistent

**Cons:**
- Can't verify specific revision exists before download
- REVISION class attribute becomes purely documentary

### Option 2: Different REVISION per Interface

```python
# Interfaces with tagged data
IblSortingInterface.REVISION = "2024-05-06"
IblAnatomicalLocalizationInterface.REVISION = "2024-05-06"

# Interfaces with untagged data
BrainwideMapTrialsInterface.REVISION = None
WheelInterface.REVISION = None
LickInterface.REVISION = None
# etc.
```

**Pros:**
- Semantically correct
- Base class logic remains simple
- Clear which data is versioned

**Cons:**
- Requires determining REVISION for each interface
- May vary by session (some might have tags, others not)

### Option 3: Try-Both Strategy

```python
# Try with revision first, fall back to unfiltered if needed
def check_availability(cls, one, eid, revision=None, **kwargs):
    requirements = cls.get_data_requirements(**kwargs)

    if revision is None:
        revision = cls.REVISION

    # Try with revision first (if specified)
    available_datasets = []
    if revision is not None:
        available_datasets = one.list_datasets(eid, revision=revision)

    # If no datasets found with revision, try without filtering
    # This handles cases where data exists but isn't tagged with this specific revision
    if len(available_datasets) == 0:
        available_datasets = one.list_datasets(eid)  # Get all latest versions

    # ... rest of matching logic
```

**Pros:**
- **Mimics `load_object()` smart fallback behavior**
- Works for all data types (universally tagged or mixed)
- Can still detect when specific revision exists
- Single logical approach for all interfaces

**Cons:**
- Potentially two API calls per session (but only when revision filtering returns empty)
- Slightly more complex logic
- Can't distinguish "no data exists" from "wrong revision" (but doesn't matter since fallback succeeds)

## Recommendation

**For BWM conversion:** Use **Option 3** (try-both strategy).

**Reasoning:**

1. **Matches download behavior:** Since `SessionLoader`, `SpikeSortingLoader`, and `load_object()` all use smart fallback, `check_availability()` should too
2. **Handles all cases:**
   - Spike sorting (100% tagged) → Found with revision filter ✓
   - Wheel (13% tagged) → Found with fallback ✓
   - Trials (mostly untagged) → Found with fallback ✓
3. **Keeps REVISION meaningful:** Can still be used to document/verify which revision was processed
4. **Fail-safe:** If revision doesn't exist, still finds available data

**The REVISION class attribute means:**
- "Try to use this revision for consistency"
- "But if it doesn't exist, use whatever is available"
- Matches ONE API's own philosophy

## Testing Across Sessions

To verify this holds across the BWM dataset, we should:

1. ✓ Test check_availability() on 10-20 random BWM sessions
2. ✓ Verify spike sorting consistently has #2024-05-06# tags
3. ✓ Confirm behavioral data mostly lacks revision tags
4. ✓ Ensure wheel polarity fixes are present without explicit tags

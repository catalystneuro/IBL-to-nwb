# IBL Revisions System Documentation

## Overview

The IBL (International Brain Laboratory) uses a **revision system** to version datasets over time. Revisions allow the lab to maintain multiple versions of the same dataset, enabling data corrections, reprocessing, and improvements while preserving data provenance.

## What are Revisions?

Revisions are **date-based snapshots** of datasets that capture the state of data processing at a specific point in time. They enable:

- **Data versioning**: Multiple versions of the same dataset can coexist
- **Quality improvements**: Reprocessed data with better algorithms
- **Bug fixes**: Corrected datasets while preserving original versions
- **Reproducibility**: Scientists can specify exact dataset versions used in analyses

## Revision Format

Revisions follow a **YYYY-MM-DD** date format:
- `2024-05-06` - May 6th, 2024 revision
- `2025-05-06` - May 6th, 2025 revision
- `2025-Q3` - Quarter-based releases

## Directory Structure

Revisions are stored in special directories using the `#revision#` pattern:

```
alf/
├── probe00/
│   ├── spikes.times.npy              # Latest/default version
│   ├── clusters.depths.npy           # Latest/default version
│   ├── #2024-05-06#/                 # Specific revision folder
│   │   ├── spikes.times.npy          # 2024-05-06 version
│   │   ├── clusters.depths.npy       # 2024-05-06 version
│   │   └── clusters.metrics.pqt      # 2024-05-06 version
│   └── #2025-05-06#/                 # Newer revision folder
│       ├── spikes.times.npy          # 2025-05-06 version
│       └── clusters.depths.npy       # 2025-05-06 version
```

## Working with Revisions

### 1. Listing Available Revisions

```python
from one.api import ONE

one = ONE()
eid = "your-session-id"

# Get all available revisions for a session
revisions = one.list_revisions(eid)
print(f"Available revisions: {revisions}")
# Output: ['2024-05-06', '2025-05-06', '2025-Q3']

# Get the latest revision
latest_revision = revisions[-1] if revisions else None
print(f"Latest revision: {latest_revision}")
```

### 2. Loading Data with Specific Revisions

```python
# Load data from a specific revision
revision = "2024-05-06"
spikes, clusters, channels = ssl.load_spike_sorting(revision=revision)

# Load data from latest revision (default behavior)
spikes, clusters, channels = ssl.load_spike_sorting()  # Uses latest

# Load specific datasets with revision
trials = one.load_object(eid, 'trials', revision=revision)
wheel = one.load_dataset(eid, 'wheel.position.npy', revision=revision)
```

### 3. Loading Data without Specifying Revision

```python
# When no revision is specified, ONE loads the latest available version
spikes, clusters, channels = ssl.load_spike_sorting()

# This is equivalent to:
revisions = one.list_revisions(eid)
latest_revision = revisions[-1] if revisions else None
spikes, clusters, channels = ssl.load_spike_sorting(revision=latest_revision)
```

## Major Revision Examples in IBL

### 2024-05-15: Spike-sorting Re-run

**Purpose**: Applied latest spike sorting algorithms across entire BWM dataset

**Changes**:
- Improved spike detection algorithms
- Better noise rejection
- More consistent processing across all sessions
- Increased total units: **621,733 putative neurons**
- Quality units: **75,708 passing QC**

**Impact**: This revision provides state-of-the-art spike sorting with consistent methodology across the full dataset.

### 2025-Q3: Enhanced Processing

**Purpose**: Added new data types and improved existing processing

**Changes**:
- Enhanced pose estimation using Lightning Pose
- Added spontaneous passive intervals
- Neuropixel saturation interval datasets
- Improved video timestamping

### Data Quality Fixes

**Audio Sync Patches**: For sessions where audio wasn't properly wired to FPGA, revisions were created with recovered audio TTLs using bpod2fpga interpolation.

**Video Timestamp Corrections**: Corrected video timestamps where possible, removed uncorrectable data.

## Revision Use Cases

### 1. Reproducible Research

```python
# For published research, always specify the exact revision used
REVISION_USED_IN_PAPER = "2024-05-06"
spikes, clusters, channels = ssl.load_spike_sorting(revision=REVISION_USED_IN_PAPER)

# Document this in your methods section:
# "Data was analyzed using IBL revision 2024-05-06"
```

### 2. Comparing Processing Versions

```python
# Compare spike sorting between two revisions
old_spikes, old_clusters, _ = ssl.load_spike_sorting(revision="2023-12-01")
new_spikes, new_clusters, _ = ssl.load_spike_sorting(revision="2024-05-06")

print(f"Old version: {len(old_spikes['times'])} spikes, {len(old_clusters['depths'])} clusters")
print(f"New version: {len(new_spikes['times'])} spikes, {len(new_clusters['depths'])} clusters")
```

### 3. Quality Control and Validation

```python
# Load latest data for analysis
latest_data = ssl.load_spike_sorting()

# But validate against a known-good revision
reference_data = ssl.load_spike_sorting(revision="2024-05-06")

# Compare key metrics to ensure data integrity
```

## Best Practices

### For Data Analysis

1. **Always specify revisions** for published research
2. **Document the revision** used in your methods
3. **Check for newer revisions** before starting major analyses
4. **Use latest revision** for exploratory analysis
5. **Validate against known revisions** for quality control

### For Code Development

```python
# Good: Explicit revision for reproducibility
def load_session_data(eid, revision="2024-05-06"):
    return ssl.load_spike_sorting(revision=revision)

# Better: Allow revision parameter with sensible default
def load_session_data(eid, revision=None):
    if revision is None:
        revisions = one.list_revisions(eid)
        revision = revisions[-1] if revisions else None
    return ssl.load_spike_sorting(revision=revision)
```

## Revision Selection Logic

The system follows this priority order:

1. **Explicit revision specified**: Use exactly what user requests
2. **No revision specified**: Use latest available revision
3. **Revision doesn't exist**: Fallback to default (latest) or raise error

## Important Notes

### Protected Datasets

Some datasets are **protected** and won't be overwritten:
- Critical datasets marked as protected maintain their revision
- Re-processing creates new revisions rather than overwriting protected ones

### Revision Inheritance

Not all files may exist in every revision:
- If a file doesn't exist in the requested revision, the system may fall back to the latest available version
- This ensures backward compatibility while providing version control

### Performance Considerations

- **Caching**: ONE caches revision information for performance
- **Storage**: Each revision requires additional storage space
- **Loading**: Specifying revisions may require additional database queries

## Summary

The IBL revision system provides robust data versioning that enables:
- **Reproducible science** through exact dataset specification
- **Quality improvements** without losing previous versions
- **Data provenance** tracking through timestamped revisions
- **Backward compatibility** for existing analyses

Always consider which revision is appropriate for your analysis and document it clearly for reproducibility.
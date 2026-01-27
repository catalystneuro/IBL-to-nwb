# Waveform Data: IBL Storage and Organization

This document explains how spike waveform data is stored in IBL.

## Summary

IBL stores two types of waveform templates:
- **Spike sorting templates** (`clusters.waveforms`) - templates from the sorting algorithm
- **Raw waveform means** (`waveforms.templates`) - median of actual spikes from preprocessed raw data

**For NWB conversion**: Use `waveforms.templates` since NWB `units.waveform_mean` stores actual mean waveforms from recorded data, not algorithm templates.

**Key differences**:
- `clusters.waveforms`: (units, time, channels) - 82 time × 32 channels
- `waveforms.templates`: (units, channels, time) - nc channels (~40-60) × 128 time
- Different axis order requires transposition for analysis
- Variable channel count (nc) depends on probe geometry

---

## 1. Waveform Template Types

### 1.1 Spike Sorting Templates (clusters.waveforms)

**Files**: `clusters.waveforms.npy` and `templates.waveforms.npy` (identical)

**Structure**:
- Shape: (n_clusters, 82, 32)
- Axis order: (units, time, channels)
- Channel mapping: `clusters.waveformsChannels.npy` (n_clusters, 32)

**Purpose**: Templates used by Kilosort/PyKilosort for spike detection and classification.

**Limitation**: Derived from spike sorting algorithm, may contain sorting artifacts.

**Access**:
```python
ssl.load_spike_sorting_object('clusters',
    dataset_types=['clusters.waveforms', 'clusters.waveformsChannels'])
```

### 1.2 Raw Waveform Means (waveforms.templates)

**File**: `waveforms.templates.npy`

**Structure**:
- Shape: (n_clusters, nc, 128) where nc is typically 40-60
- Axis order: (units, channels, time) - each row is a channel trace
- Channel mapping: `waveforms.channels.npz` (n_waveforms, nc) - per-waveform

**Purpose**: Mean waveforms computed from actual pre-processed raw data.

**Data source**: Median of approximately 250 spike waveforms extracted from continuous recording.

**Preprocessing**: Phase correction, bad channel interpolation, high-pass filter (300Hz), common average reference.

**Why use for NWB**:
- NWB `units.waveform_mean` stores actual mean waveforms, not algorithm templates
- Computed from real recorded spikes with standard preprocessing
- Longer temporal window (128 vs 82 samples, 4.27ms vs 2.73ms)
- Not biased by sorting algorithm's template matching

**Access**:
```python
waveforms_data = ssl.load_spike_sorting_object('waveforms')
templates = waveforms_data['templates']  # Shape: (n_clusters, nc, 128)
```

### 1.3 Channel Count (nc)

The number of channels (nc) in `waveforms.templates` varies by session:
- Determined by `make_channel_index(geometry, radius=200.0)`
- Includes all channels within 200 μm of peak channel
- Typically 40-60 channels
- Varies by probe geometry and unit location

---

## 2. The Missing Link: Mapping Templates to Channels

### The Problem

IBL provides `waveforms.templates` (one per cluster) but does NOT provide a direct cluster→channels mapping. To use the templates, we must infer which channels each template represents.

### Available Metadata Files

#### waveforms.table.pqt (The Bridge)

**Purpose**: Links individual waveforms to clusters

**Structure**:
- Shape: (n_waveforms, 5) - typically ~114,000 rows for 448 clusters
- Columns:
  - `cluster`: Cluster ID (0 to n_clusters-1)
  - `sample`: Time sample in recording where spike occurred
  - `peak_channel`: Channel with maximum amplitude
  - `index`: Global waveform index in `waveforms.traces.npy`
  - `index_within_clusters`: Index within cluster (0 to ~255)

**Key insight**: Each cluster has approximately 250-256 individual waveforms

**Example data**:
```
   cluster    sample  peak_channel  index  index_within_clusters
0       0   1234567            42      0                      0
1       0   2345678            42      1                      1
...
255     0   9876543            42    255                    255
256     1   1111111            38    256                      0
```

**What it tells us**:
- Which waveforms belong to which cluster
- When each spike occurred
- The peak channel for each spike
- How to index into `waveforms.traces.npy` and `waveforms.channels.npz`

**What it does NOT tell us**:
- Which channels are used in `waveforms.templates` for each cluster

---

#### waveforms.channels.npz (Per-Waveform Channel IDs)

**Purpose**: Specifies which channels are included in each individual waveform

**Structure**:
- Shape: (n_waveforms, nc) - one row per waveform
- Contains channel indices (0-383) for Neuropixels channels
- Corresponds to columns in `waveforms.traces.npy`

**Key insight**: This is per-waveform granularity, NOT per-cluster

**Example data**:
```
Waveform 0 (cluster 0): [10, 11, 12, 13, ..., 48, 49]  # 40 channels
Waveform 1 (cluster 0): [10, 11, 12, 13, ..., 48, 49]  # Same channels
Waveform 2 (cluster 0): [9, 10, 11, 12, ..., 47, 48]   # Slightly different!
...
Waveform 256 (cluster 1): [35, 36, 37, 38, ..., 73, 74]  # Different cluster
```

**Why channel sets vary within a cluster**:
- Spikes detected at slightly different times may use different channels
- Different local field potentials affect channel selection
- Drift in recording may shift optimal channels
- Some waveforms may use more/fewer channels based on amplitude

**What it tells us**:
- Exact channel IDs for each row in each individual waveform
- Channel variability within a cluster (typically 30-43 unique channel sets per cluster)

**What it does NOT tell us**:
- Which channel set to use for `waveforms.templates` (the cluster-level template)

---

### The Inference Solution

Since IBL does NOT provide direct cluster→channels mapping for templates, we must infer:

**Strategy**: Voting/Consensus across individual waveforms

1. Use `waveforms.table.pqt` to find all waveforms belonging to a cluster
2. Use `waveforms.channels.npz` to get channel sets for those waveforms
3. Find the most common (mode) channel set across all waveforms
4. Use this as the representative channel set for the cluster's template

**Example**:
```python
import pandas as pd
import numpy as np

# Load metadata
table = pd.read_parquet('waveforms.table.pqt')
channels = np.load('waveforms.channels.npz')['channels']

# Get waveforms for cluster_id
cluster_waveforms = table[table['cluster'] == cluster_id]
wf_indices = cluster_waveforms.index.tolist()

# Get channel sets used by this cluster (typically ~256 waveforms)
channel_sets = channels[wf_indices]  # Shape: (256, 40)

# Find most common channel set using voting
unique_sets, counts = np.unique(channel_sets, axis=0, return_counts=True)
most_common_idx = np.argmax(counts)
cluster_channels = unique_sets[most_common_idx]  # Shape: (40,)
```

**Result**: Per-cluster channel mapping array of shape (n_clusters, nc)

**Implementation**: See `_infer_cluster_channels()` in [src/ibl_to_nwb/datainterfaces/_ibl_sorting_extractor.py](src/ibl_to_nwb/datainterfaces/_ibl_sorting_extractor.py) (lines 258-322)

---

## 4. Supporting Files

### waveforms.traces.npy
- **Purpose**: Individual spike waveforms extracted from continuous recording
- **Shape**: (n_waveforms, nc, 128) - typically ~114,000 individual waveforms
- **Content**: Each waveform is 128 time samples across nc channels (~40)
- **Relationship**: `waveforms.templates` is the median of traces belonging to each cluster
- **Size**: Large (~1-2 GB per probe)
- **Usage**: Used to compute `waveforms.templates`, not directly loaded in conversion

---

## 5. Data Summary

| File | Shape | Granularity | Purpose |
|------|-------|-------------|---------|
| `waveforms.templates.npy` | (n_clusters, nc, 128) | **Per-cluster** | Mean waveforms (what we convert to NWB) |
| `waveforms.channels.npz` | (n_waveforms, nc) | **Per-waveform** | Which channels each individual waveform uses |
| `waveforms.table.pqt` | (n_waveforms, 5) | **Per-waveform** | Maps individual waveforms → clusters |
| `waveforms.traces.npy` | (n_waveforms, nc, 128) | **Per-waveform** | Raw individual waveforms (~256 per cluster) |
| `clusters.waveforms.npy` | (n_clusters, 82, 32) | **Per-cluster** | Spike sorting algorithm templates |
| `clusters.waveformsChannels.npy` | (n_clusters, 32) | **Per-cluster** | Direct channel mapping (32 channels) |

**Key distinction**:
- **Per-cluster files** (`waveforms.templates`, `clusters.waveforms`) have one entry per unit
- **Per-waveform files** (`waveforms.channels`, `waveforms.table`, `waveforms.traces`) have ~256 entries per unit
- **The gap**: `waveforms.templates` is per-cluster, but `waveforms.channels` is per-waveform
- **The solution**: Use `waveforms.table.pqt` to bridge the gap via voting/consensus

---

## 6. NWB Conversion: Channel Reordering for Electrode Alignment

### Background

IBL's `waveforms.templates` has variable channel counts per unit, padded to uniform shape:
- **Real channels**: IDs 0-383 (actual electrode data from Neuropixels probe)
- **Padding channels**: Channel ID 384 with NaN values (used to make array uniform across units)

Example: A unit with 21 real channels is stored as:
- Shape: (21 real channels, 128 time samples) → padded to → (40 channels, 128 time samples)
- Channel IDs: [0, 1, 2, ..., 20, 384, 384, ..., 384]
- Waveform values: [real data...] + [NaN, NaN, ..., NaN]

### Problem

NWB requires clear alignment between `units.waveform_mean` and `units.electrodes`:
- All waveforms must have the same shape (NWB requirement)
- Each waveform channel should correspond to an electrode
- Padding channels (ID 384) have no real electrode (probe only has channels 0-383)

### Solution: Channel Reordering

The conversion code reorders channels to put real channels first, padding last:

**Before reordering** (IBL storage):
```
Channel IDs: [0, 1, 2, ..., 20, 384, 384, ..., 384]
Waveform shape: (128 time, 40 channels)
```

**After reordering** (NWB storage):
```
Channel IDs: [0, 1, 2, ..., 20, 384, 384, ..., 384]  (already ordered in this example)
Waveform shape: (128 time, 40 channels)
Electrodes: [0, 1, 2, ..., 20]  (21 entries, only real channels)
```

**Result**:
- `waveform_mean[:, 0:21]` → maps to `electrodes[0:21]` (clear 1:1 correspondence)
- `waveform_mean[:, 21:40]` → padding (all NaN, no electrode mapping)

### Implementation

See code in:
- `src/ibl_to_nwb/datainterfaces/_ibl_sorting_extractor.py` (lines 210-248)
- `src/ibl_to_nwb/datainterfaces/_ibl_sorting_interface.py` (lines 366-378)

### Usage Example

```python
# Access waveform for unit with clear electrode mapping
unit = nwbfile.units[unit_id]
waveform = unit['waveform_mean']  # Shape: (128, 40)
electrodes = unit['electrodes']   # Length: 21 (only real channels)

# Direct mapping for real channels
for i in range(len(electrodes)):
    channel_waveform = waveform[:, i]  # Corresponds to electrodes[i]
    electrode_depth = electrodes[i]['rel_y']
    # ... analyze waveform at this depth

# Padding channels (no electrode mapping)
n_padding = waveform.shape[1] - len(electrodes)  # 40 - 21 = 19
# waveform[:, 21:40] is all NaN (padding)
```

---

## Appendix: When to Use Each Template Type

### Use waveforms.templates for:
- Characterizing neuron waveform shapes
- Scientific analysis of neural properties
- Publication figures

### Use clusters.waveforms for:
- Assessing spike sorting quality
- Understanding sorting algorithm behavior
- Comparing with sorter outputs
- Backwards compatibility

---

## References

- **IBL source code**: `ibl-neuropixel/src/ibldsp/waveform_extraction.py` (lines 295-472)
- **IBL documentation**: https://docs.internationalbrainlab.org/loading_examples/loading_spike_waveforms.html

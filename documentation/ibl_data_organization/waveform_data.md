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

## 2. Mapping Templates to Channels

### The Problem

IBL provides `waveforms.templates` (one per cluster) but does NOT provide a direct cluster→channels mapping file. To use the templates, we must determine which channels each template represents.

### Solution: Geometric Reconstruction

IBL recommended using **geometric reconstruction** rather than loading additional metadata files. This approach:
1. Uses `clusters['channels']` - the peak channel for each cluster (already loaded with spike sorting)
2. Uses probe geometry (x, y coordinates) to compute which channels are within 200μm radius

This is the same logic IBL uses during waveform extraction (`ibldsp.waveform_extraction`), making it both efficient and correct.

**Implementation**:
```python
from ibldsp.utils import make_channel_index

# Get probe geometry from electrodes table (rel_x, rel_y in micrometers)
# Note: channels["x"] and channels["y"] are brain atlas coordinates in meters, NOT probe geometry
probe_geometry = np.c_[electrodes['rel_x'], electrodes['rel_y']]  # (384, 2) in micrometers
channel_lookup = make_channel_index(probe_geometry, radius=200.0, pad_val=384)

# Index by peak channel to get channels for each cluster
peak_channels = clusters['channels']  # (n_clusters,)
cluster_channels = channel_lookup[peak_channels]  # (n_clusters, nc)
```

**How it works**:
1. `make_channel_index()` precomputes, for each of the 384 channels, which other channels are within 200μm
2. Indexing with peak channels gives the exact channel set used during extraction
3. Channels outside the probe (padding) are marked with 384

**Important**: Use `rel_x` and `rel_y` from the electrodes table (probe-relative positions in micrometers), NOT `channels["x"]` and `channels["y"]` which are brain atlas coordinates in meters.

**Advantages over loading waveforms.channels.npz**:
- No additional file downloads needed
- Deterministic (no voting/consensus required)
- Matches IBL's extraction logic exactly
- More efficient

**Implementation**: See `_compute_waveform_channels_and_reorder()` in [_ibl_sorting_interface.py](../../src/ibl_to_nwb/datainterfaces/_ibl_sorting_interface.py)

---

### Alternative: Metadata-Based Inference (Not Used)

For reference, IBL also provides per-waveform metadata that could theoretically be used:

#### waveforms.table.pqt
- Links individual waveforms (~256 per cluster) to clusters
- Contains: cluster ID, sample time, peak_channel, index

#### waveforms.channels.npz
- Per-waveform channel IDs (n_waveforms, nc)
- Shows which channels each individual waveform uses

However, this approach requires:
1. Loading two additional files
2. Voting/consensus to select representative channel set per cluster
3. Handling variability (clusters can have 30-43 unique channel sets)

The geometric reconstruction method is preferred as it's simpler, more efficient, and recommended by IBL.

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
- **The gap**: `waveforms.templates` is per-cluster, but channel mapping metadata is per-waveform
- **The solution**: Use geometric reconstruction with `clusters['channels']` and `make_channel_index()`

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

See `_compute_waveform_channels_and_reorder()` in:
- `src/ibl_to_nwb/datainterfaces/_ibl_sorting_interface.py`

This method:
1. Gets probe geometry (`rel_x`, `rel_y`) from the electrodes table
2. Uses `make_channel_index()` to find channels within 200μm of each unit's peak channel
3. Reorders waveforms so real channels come first (sorted by depth), padding last
4. Links only the real electrodes to each unit

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

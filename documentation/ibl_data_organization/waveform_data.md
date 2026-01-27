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

## 2. Channel Mapping for waveforms.templates

**File**: `waveforms.channels.npz`

**Structure**:
- Shape: (n_waveforms, nc) - per-waveform, not per-cluster
- Contains channel indices for each individual waveform in `waveforms.traces.npy`
- Each cluster typically uses 30-43 different channel sets across its waveforms

**Mapping Strategy**:
1. Load `waveforms.table.pqt` to identify which waveforms belong to each cluster
2. Load `waveforms.channels.npz` to get channel sets for all waveforms
3. For each cluster, find the most frequently used channel set among its waveforms
4. Use this as the representative channel set for that cluster's template

**Example**:
```python
# Get waveforms for cluster_id
cluster_waveforms = table[table['cluster'] == cluster_id]
wf_indices = cluster_waveforms.index.tolist()

# Get channel sets used by this cluster
channel_sets = traces_channels[wf_indices]

# Find most common channel set
unique_sets, counts = np.unique(channel_sets, axis=0, return_counts=True)
most_common_idx = np.argmax(counts)
cluster_channels = unique_sets[most_common_idx]  # Shape: (nc,)
```

**Result**: Per-cluster channel mapping array of shape (n_clusters, nc)

---

## 4. Supporting Files

### waveforms.traces.npy
- Individual spike waveforms (up to 256 per cluster)
- Shape: (n_waveforms, nc, 128)
- Used to compute `waveforms.templates` (median of these)
- Large size (~1-2 GB per probe)

### waveforms.table.pqt
- Metadata linking waveforms to clusters
- Columns: sample, cluster, peak_channel, waveform_index, index_within_clusters
- Required for inferring template channel mapping

---

## 5. Data Summary

| File | Shape | Axis Order | Purpose |
|------|-------|------------|---------|
| `waveforms.templates.npy` | (n_clusters, nc, 128) | (units, channels, time) | Mean waveforms |
| `waveforms.channels.npz` | (n_waveforms, nc) | - | Channel indices (per-waveform) |
| `waveforms.table.pqt` | (n_waveforms, 6) | - | Waveform metadata |
| `waveforms.traces.npy` | (n_waveforms, nc, 128) | (waveforms, channels, time) | Individual waveforms |
| `clusters.waveforms.npy` | (n_clusters, 82, 32) | (units, time, channels) | Sorting templates |
| `clusters.waveformsChannels.npy` | (n_clusters, 32) | - | Channel indices (per-cluster) |

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

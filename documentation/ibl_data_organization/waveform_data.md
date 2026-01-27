# Waveform Data: IBL Storage, NWB Conversion, and Visualization

This document explains how spike waveform data is stored in IBL, how we convert it to NWB format, and how to correctly visualize it.

## Summary

The waveform data is stored with channels ordered by **proximity to the maximum amplitude channel**, not by depth on the probe. This is intentional in the IBL data format and is preserved in NWB conversion. When visualizing waveforms, users must reorder channels by electrode depth if they want to see the spatial relationship along the probe.

---

## 1. IBL Waveform Data Types

IBL stores **three types** of waveform-related data:

### 1.1 Waveform Templates (Mean Waveforms)

**Source file**: `clusters.waveforms.npy`
- Shape: `(n_clusters, 82, 32)` - 82 time samples, 32 channels
- Content: **Templates** - the average waveform across all spikes per cluster
- **This is what we convert to NWB** as `waveform_mean`

**Note**: IBL also stores `templates.waveforms.npy` which is **IDENTICAL** to `clusters.waveforms.npy`. We use `clusters.waveforms` as the canonical source following IBL convention.

**Terminology clarification**: Despite the filename `clusters.waveforms`, these are **templates** (mean waveforms averaged across all spikes), NOT individual spike waveforms. The naming is an IBL convention.

### 1.2 Waveform Channel Mapping
V
**Source file**: `clusters.waveformsChannels.npy`
- Shape: `(n_clusters, 32)`
- Content: Maps each of the 32 waveform columns to actual probe channel numbers
- Channel 0 is always the maximum amplitude channel

### 1.3 Raw Waveforms (Sampled)

**Source file**: `waveforms.traces.npy`
- Shape: `(n_clusters, 256, 40, 128)` - 256 waveforms per cluster, 40 samples, 128 channels
- Content: Up to 256 randomly selected raw spike waveforms per cluster
- **NOT included in NWB conversion** due to size (~2.3 GB per probe)

These raw waveforms use different preprocessing than templates and are useful for:
- Signal-to-noise assessment by stacking
- Waveform variability analysis
- Quality control visualization

To load raw waveforms directly from IBL:
```python
from brainbox.io.one import SpikeSortingLoader

ssl = SpikeSortingLoader(eid=session_id, one=one, pname=probe_name)
spikes, clusters, channels = ssl.load_spike_sorting()
raw_waveforms = ssl.raw_waveforms(return_waveforms=True)
```

### 1.4 Summary: IBL Waveform Data Sources

| Data Source | File | Shape | Channels | Order | Access Method |
|-------------|------|-------|----------|-------|---------------|
| **Cluster templates** | `clusters.waveforms.npy` | `(n_clusters, 82, 32)` | 32 | Proximity | `ssl.load_spike_sorting_object('clusters', dataset_types=['clusters.waveforms'])` |
| **Templates (identical)** | `templates.waveforms.npy` | `(n_clusters, 82, 32)` | 32 | Proximity | Same as above |
| **Waveforms object templates** | `waveforms.templates.npy` | `(n_clusters, 40, 128)` | 128 | Depth | `ssl.load_spike_sorting_object('waveforms')['templates']` |
| **Raw waveforms** | `waveforms.traces.npy` | `(n_clusters, 256, 40, 128)` | 128 | Depth | `ssl.raw_waveforms(return_waveforms=True)` |
| **Channel mapping** | `clusters.waveformsChannels.npy` | `(n_clusters, 32)` | - | - | `ssl.load_spike_sorting_object('clusters', dataset_types=['clusters.waveformsChannels'])` |

**Key differences:**

| Property | `clusters.waveforms` | `waveforms.templates` |
|----------|---------------------|----------------------|
| **Channels** | 32 (neighborhood) | 128 (wider neighborhood) |
| **Time samples** | 82 | 40 |
| **Channel order** | By proximity to max | By depth on probe |
| **Visualization** | Requires reordering by `rel_y` | Direct plotting works |
| **Used in NWB** | Yes | No |

**Channel counts explained**: Neuropixel 1.0 probes have 384 channels total, but spike signals are spatially localized (~100-200 μm from soma). Storing all 384 channels would waste space since most would contain only noise. Both 32 and 128 represent **channel neighborhoods** around the peak channel:
- **32 channels**: Tight neighborhood (~150 μm radius), captures core signal
- **128 channels**: Wider neighborhood (~500 μm), useful for spatial visualization

**Why we store `clusters.waveforms` directly to NWB `waveform_mean`:**
- Higher time resolution (82 samples / 2.73 ms vs 40 samples / 1.33 ms)
- Smaller size (32 vs 128 channels)
- Centered on max amplitude channel (most relevant for the unit)
- Matches NWB `waveform_mean` convention (templates centered on primary electrode)

---

## 2. Channel Ordering in IBL

**Key finding**: The 32 waveform channels are ordered by **proximity to the maximum amplitude channel**, NOT by depth.

Example for a cluster with max channel 22:
```
waveform_channels: [22, 23, 20, 24, 26, 18, 21, 25, 27, 19, 16, 28, ...]
                    ^-- max channel always at position 0
                        ^-- nearest neighbors follow
```

This means:
- Column 0 of the waveform **always** corresponds to the channel with maximum amplitude
- Subsequent columns contain progressively more distant channels
- The ordering is NOT sorted by channel number or depth

This can be verified by examining raw IBL data:
```python
from one.api import ONE
from brainbox.io.one import SpikeSortingLoader

one = ONE()
ssl = SpikeSortingLoader(eid=session_id, one=one, pname=probe_name)
additional = ssl.load_spike_sorting_object(
    'clusters',
    dataset_types=['clusters.waveformsChannels', 'clusters.channels'],
)

# For ALL clusters, max_channel is at position 0 in waveformsChannels
for cluster_idx in range(len(additional['channels'])):
    max_ch = additional['channels'][cluster_idx]
    wf_channels = additional['waveformsChannels'][cluster_idx]
    assert wf_channels[0] == max_ch  # Always true!
```

---

## 3. NWB Conversion

### How We Store Waveforms

In NWB, waveform templates are stored in the units table as `waveform_mean`:
- Shape: `(num_units, 82, 32)`
- Units: microvolts (converted from Volts in IBL)
- Column ordering: **preserved from IBL** (proximity order)

Each unit also has an `electrodes` column (DynamicTableRegion) that lists the 32 electrode indices corresponding to each waveform column. These electrode indices are stored in the **same proximity order** as the waveform channels.

### What's in the NWB File

For each unit, you can access:
- `unit["waveform_mean"]`: (82, 32) array of waveform amplitudes in microvolts
- `unit["electrodes"]`: DataFrame with electrode info for each channel
- `unit["max_electrode"]`: Single electrode row for max amplitude channel

The electrode indices in `unit["electrodes"]` are in proximity order, matching the waveform columns.

For more details on the NWB units table and all available columns, see [Sorting Interface Documentation](../conversion/sorting_interface.md).

---

## 4. Extracting Data from NWB

### Basic Access
```python
from pynwb import NWBHDF5IO

io = NWBHDF5IO("file.nwb", mode="r")
nwbfile = io.read()

units_df = nwbfile.units.to_dataframe()

# For a single unit
unit = units_df.iloc[0]
waveform = unit["waveform_mean"]  # (82, 32) array
electrodes = unit["electrodes"]   # DataFrame with electrode info
```

### Getting Electrode Depths
```python
# Electrode depths for sorting/visualization
electrode_depths = unit["electrodes"]["rel_y"].values
# This gives depths in proximity order (matching waveform columns)
```

### Reordering by Depth
If you need waveforms ordered by depth (bottom to top of probe):
```python
depths = unit["electrodes"]["rel_y"].values
sort_order = np.argsort(depths)
waveform_by_depth = waveform[:, sort_order]
depths_sorted = depths[sort_order]
```

---

## 5. Visualization

### Issue: Why Max Channel Appears at Bottom

When plotting waveforms without reordering, the maximum amplitude channel appears at position 0 (bottom of the plot). This is because IBL stores channels in proximity order, and the max channel is always first.

### Solution: Sort by Electrode Depth

Pass electrode depths to visualization functions to sort channels by depth:

```python
electrode_depths = unit["electrodes"]["rel_y"].values
plot_waveform_wiggle(waveform, electrode_depths=electrode_depths, ax=ax)
```

### Expected Result

After sorting by depth:
- Y-axis shows actual depth from probe tip (in um)
- Max amplitude channel appears in the middle of the plot (where the unit is located)
- Waveforms spread above and below the max channel location
- This matches the spatial spread of the signal along the probe

---

## 6. Key Points

1. **Templates vs raw waveforms**: `clusters.waveforms` contains templates (mean waveforms), not individual spike waveforms
2. **Identical files**: `templates.waveforms.npy` = `clusters.waveforms.npy` (we use clusters.waveforms)
3. **Raw waveforms available**: `waveforms.traces.npy` has 256 sampled raw waveforms per cluster (not in NWB)
4. **IBL stores waveforms in proximity order**: Max channel at position 0, neighbors following
5. **NWB preserves this ordering**: Both waveform data and electrode indices maintain proximity order
6. **For visualization by depth**: Must reorder using electrode `rel_y` values
7. **Electrode mapping is correct**: `unit["electrodes"]` gives correct electrode info for each waveform column

---

## References

- [IBL Spike Waveforms Documentation](https://docs.internationalbrainlab.org/loading_examples/loading_spike_waveforms.html)
- [Sorting Interface Documentation](../conversion/sorting_interface.md) - NWB units table details
- IBL `brainbox.io.one.SpikeSortingLoader` for loading raw data

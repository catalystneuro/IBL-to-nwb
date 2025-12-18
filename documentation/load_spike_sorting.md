# load_spike_sorting() Return Values Documentation

## Overview

The `sorting_loader.load_spike_sorting()` method returns three objects containing spike sorting data from IBL (International Brain Laboratory) electrophysiology recordings:

```python
spikes, clusters, channels = sorting_loader.load_spike_sorting()
```

## Return Values

### 1. `spikes` - Spike Data Dictionary

**Data Type**: `dict` (loaded via `alfio.load_object`)

**Description**: Contains spike-by-spike information for all detected action potentials.

| Key | Data Type | Shape | Source File | Description |
|-----|-----------|-------|-------------|-------------|
| `times` | `numpy.ndarray` (float64) | `(n_spikes,)` | `spikes.times.npy` | Spike timestamps in seconds relative to session start |
| `clusters` | `numpy.ndarray` (int64) | `(n_spikes,)` | `spikes.clusters.npy` | Cluster ID for each spike (which neuron fired) |
| `amps` | `numpy.ndarray` (float64) | `(n_spikes,)` | `spikes.amps.npy` | Spike amplitude in microvolts |
| `depths` | `numpy.ndarray` (float64) | `(n_spikes,)` | `spikes.depths.npy` | Depth along probe in micrometers from tip |

**Example Usage**:
```python
print(f"Total spikes: {len(spikes['times'])}")
print(f"First spike at: {spikes['times'][0]:.3f} seconds")
print(f"Spike amplitudes range: {spikes['amps'].min():.1f} to {spikes['amps'].max():.1f} μV")
```

### 2. `clusters` - Cluster/Unit Data Dictionary

**Data Type**: `dict` (loaded via `alfio.load_object`)

**Description**: Contains information about each sorted unit/cluster (putative neurons).

| Key | Data Type | Shape | Source File | Description |
|-----|-----------|-------|-------------|-------------|
| `channels` | `numpy.ndarray` (int64) | `(n_clusters,)` | `clusters.channels.npy` | Primary channel for each cluster |
| `depths` | `numpy.ndarray` (float64) | `(n_clusters,)` | `clusters.depths.npy` | Depth of cluster along probe in micrometers |
| `metrics` | `dict` | varies | `clusters.metrics.pqt` | Quality metrics for each cluster (see below) |
| `uuids` | `numpy.ndarray` (str) | `(n_clusters,)` | `clusters.uuids.npy` | Unique identifiers for clusters |

**Cluster Metrics** (`clusters['metrics']`):
| Metric | Description |
|--------|-------------|
| `slidingRP_viol` | Sliding refractory period violations |
| `presence_ratio` | Fraction of session where unit is active |
| `amplitude_cutoff` | Estimate of missing spikes due to amplitude threshold |
| `firing_rate` | Average firing rate in Hz |
| `isi_viol` | Inter-spike interval violations |
| `label` | Quality label (0=noise, 1=mua, 2=good, 3=unsorted) |

**Example Usage**:
```python
good_units = clusters['metrics']['label'] == 2  # Good units only
print(f"Good units: {good_units.sum()} / {len(clusters['channels'])}")
print(f"Firing rates: {clusters['metrics']['firing_rate'][good_units].mean():.2f} Hz")
```

### 3. `channels` - Channel/Electrode Data

**Data Type**: `dict` or `Bunch` object

**Description**: Contains information about electrode channels and their anatomical locations.

| Key | Data Type | Shape | Source File(s) | Description |
|-----|-----------|-------|---------------|-------------|
| `x` | `numpy.ndarray` (float64) | `(n_channels,)` | `channels.mlapdv.npy` | ML coordinate in meters (medial-lateral) |
| `y` | `numpy.ndarray` (float64) | `(n_channels,)` | `channels.mlapdv.npy` | AP coordinate in meters (anterior-posterior) |
| `z` | `numpy.ndarray` (float64) | `(n_channels,)` | `channels.mlapdv.npy` | DV coordinate in meters (dorsal-ventral) |
| `atlas_id` | `numpy.ndarray` (int) | `(n_channels,)` | `channels.brainLocationIds_ccf_2017.npy` | Allen Brain Atlas region ID |
| `acronym` | `numpy.ndarray` (str) | `(n_channels,)` | Derived from `atlas_id` + brain atlas | Brain region acronym (e.g., 'VISp', 'CA1') |
| `axial_um` | `numpy.ndarray` (float64) | `(n_channels,)` | `channels.localCoordinates.npy` | Distance along probe axis in micrometers |
| `lateral_um` | `numpy.ndarray` (float64) | `(n_channels,)` | `channels.localCoordinates.npy` | Lateral offset from probe axis in micrometers |
| `rawInd` | `numpy.ndarray` (int) | `(n_channels,)` | Generated during loading | Raw channel indices from recording |

**Coordinate System**:
- **x**: Medial-lateral (positive = rightward)
- **y**: Anterior-posterior (positive = forward)
- **z**: Dorsal-ventral (positive = upward)
- **axial_um**: Distance from probe tip (0 = tip, increasing = toward brain surface)

**Example Usage**:
```python
print(f"Channels span: {channels['axial_um'].min():.0f} to {channels['axial_um'].max():.0f} μm")
unique_regions = np.unique(channels['acronym'])
print(f"Brain regions sampled: {', '.join(unique_regions)}")

# Find channels in visual cortex
vis_channels = [i for i, region in enumerate(channels['acronym']) if 'VIS' in region]
print(f"Visual cortex channels: {len(vis_channels)}")
```

## Data Relationships

- **Spike → Cluster**: `spikes['clusters'][i]` gives the cluster ID for spike `i`
- **Cluster → Channel**: `clusters['channels'][j]` gives the primary channel for cluster `j`
- **Channel → Location**: `channels['acronym'][k]` gives the brain region for channel `k`

## File Locations

The files are loaded from specific collections in the IBL database:

**Typical collection path**: `alf/probeXX/spike_sorter_name/`
- `probeXX` = probe name (e.g., `probe00`, `probe01`)
- `spike_sorter_name` = algorithm used (e.g., `pykilosort`, `iblsorter`)

**Example full paths**:
- `alf/probe00/pykilosort/spikes.times.npy`
- `alf/probe00/pykilosort/clusters.metrics.pqt`
- `alf/probe00/channels.localCoordinates.npy`

**Alternative sources**:
- `electrodeSites.*` files may be used instead of `channels.*` if available
- Histology alignments may come from different collections (e.g., `alf/probe00/` vs spike sorting collection)

## Notes

- All arrays are aligned by index (spike 0 corresponds to `spikes['times'][0]`, `spikes['clusters'][0]`, etc.)
- Channel coordinates are in CCF (Common Coordinate Framework) space
- Spike times are in seconds from session start
- Depths and coordinates may come from histological alignment when available
- Missing data is handled gracefully (empty dictionaries returned if no data found)
- The `channels` object is reformatted from raw ALF files by `_channels_alf2bunch()` function
# SpikeSortingLoader Documentation

## Overview

The `SpikeSortingLoader` is a comprehensive data loading class for spike sorting data from IBL (International Brain Laboratory) experiments. It provides a unified interface for loading, processing, and visualizing electrophysiology data from Neuropixel probes.

## Purpose and Functionality

The SpikeSortingLoader serves as a central hub for accessing spike sorting results, raw electrophysiology data, and associated metadata. It handles various data sources and formats, manages data downloads, and provides tools for data visualization and analysis.

### Key Features:
- Load spike sorting data (spikes, clusters, channels) from different spike sorters
- Access raw electrophysiology data (AP and LF bands)
- Handle channel location mapping and histology alignment
- Provide time synchronization between probe and session clocks
- Support both local and remote data access via ONE API

## Initialization

The loader can be instantiated in several ways:

```python
# With Alyx database probe ID
SpikeSortingLoader(pid=pid, one=one)

# With session ID and probe name
SpikeSortingLoader(eid=eid, pname='probe00', one=one)

# From local session path
SpikeSortingLoader(session_path=session_path, pname='probe00')
```

## Core Data Loading Methods

### `load_spike_sorting(spike_sorter='iblsorter', **kwargs)`

**Purpose:** Main method to load spikes, clusters, and channels data

**Parameters:**
- `spike_sorter`: Spike sorting algorithm ('iblsorter', 'pykilosort', etc.)
- `good_units`: If True, loads only good quality units
- `namespace`: Load manually curated data with specific namespace

**Returns:** Tuple of `(spikes, clusters, channels)`

```python
from one.api import ONE
from brainbox.io.one import SpikeSortingLoader

one = ONE()
ssl = SpikeSortingLoader(eid=eid, pname='probe00', one=one)

# Load all spike sorting data
spikes, clusters, channels = ssl.load_spike_sorting()
```

#### Return Value Details

This section provides detailed documentation of the three dictionaries returned by `load_spike_sorting()`.

##### 1. `spikes` - Spike Data Dictionary

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

##### 2. `clusters` - Cluster/Unit Data Dictionary

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

##### 3. `channels` - Channel/Electrode Data

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

#### Data Relationships

- **Spike → Cluster**: `spikes['clusters'][i]` gives the cluster ID for spike `i`
- **Cluster → Channel**: `clusters['channels'][j]` gives the primary channel for cluster `j`
- **Channel → Location**: `channels['acronym'][k]` gives the brain region for channel `k`

#### File Locations

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

#### Notes

- All arrays are aligned by index (spike 0 corresponds to `spikes['times'][0]`, `spikes['clusters'][0]`, etc.)
- Channel coordinates are in CCF (Common Coordinate Framework) space
- Spike times are in seconds from session start
- Depths and coordinates may come from histological alignment when available
- Missing data is handled gracefully (empty dictionaries returned if no data found)
- The `channels` object is reformatted from raw ALF files by `_channels_alf2bunch()` function

---

### `load_channels(**kwargs)`

**Purpose:** Load channel location information with histology alignment

**Features:** Automatically selects best available histology (resolved > aligned > traced)

**Returns:** Bunch object with channel coordinates and brain region information

The `load_channels` method returns a comprehensive dictionary containing channel location information from multiple coordinate systems and data sources. The returned keys include:

| Key | Description | Source/Reference |
|-----|-------------|------------------|
| `x` | Medial-lateral coordinate in meters (CCF atlas space) | Converted from `mlapdv[:, 0] / 1e6` in `_channels_alf2bunch()` (line 125) |
| `y` | Anterior-posterior coordinate in meters (CCF atlas space) | Converted from `mlapdv[:, 1] / 1e6` in `_channels_alf2bunch()` (line 126) |
| `z` | Dorsal-ventral coordinate in meters (CCF atlas space) | Converted from `mlapdv[:, 2] / 1e6` in `_channels_alf2bunch()` (line 127) |
| `acronym` | Brain region acronym (e.g., 'VISp', 'CA1') | Derived from `atlas_id` using brain atlas regions mapping (line 138) |
| `atlas_id` | Brain region ID in CCF 2017 atlas (non-lateralized) | From `brainLocationIds_ccf_2017` dataset (line 129) |
| `axial_um` | Depth position along probe axis in micrometers | From `localCoordinates[:, 1]` - probe's y-axis (line 130) |
| `lateral_um` | Lateral position on probe face in micrometers | From `localCoordinates[:, 0]` - probe's x-axis (line 131) |
| `labels` | Channel labels or identifiers | From electrodeSites or channels ALF objects (carried over in line 136) |
| `rawInd` | Raw channel indices for electrode sites | Generated as `np.arange()` when electrodeSites data is used (line 847) |

**Additional keys may include:**
- Any other keys present in the underlying `electrodeSites` or `channels` ALF objects are passed through
- Custom keys from specific spike sorting algorithms or manual annotations

**Coordinate Systems:**
- **CCF coordinates** (`x`, `y`, `z`): Allen Common Coordinate Framework in meters, representing physical brain locations
- **Probe coordinates** (`axial_um`, `lateral_um`): Local coordinates on the Neuropixel probe in micrometers
- **Atlas regions** (`atlas_id`, `acronym`): Brain region assignments based on histological alignment

### `load_spike_sorting_object(obj, **kwargs)`

**Purpose:** Load individual ALF objects (spikes, clusters, or channels)

**Parameters:**
- `obj`: Object type ('spikes', 'clusters', 'channels')

**Returns:** Loaded ALF object data

## Other Data Access Methods

### Raw Data Access Methods

#### `raw_electrophysiology(stream=True, band='ap', **kwargs)`

**Purpose:** Access raw electrophysiology data

**Parameters:**
- `stream`: If True, returns streaming reader; if False, downloads and returns file reader
- `band`: 'ap' for action potential band, 'lf' for local field potential

**Returns:** Streamer or spikeglx.Reader object

#### `raw_waveforms(**kwargs)`

**Purpose:** Access extracted spike waveforms

**Returns:** WaveformsLoader object for waveform analysis

### Time Synchronization Methods

#### `samples2times(values, direction='forward', band='ap')`

**Purpose:** Convert between ephys samples and session time

**Parameters:**
- `values`: Sample indices or times to convert
- `direction`: 'forward' (samples to time) or 'reverse' (time to samples)
- `band`: 'ap' or 'lf' for different sampling rates

**Returns:** Converted timestamps

#### `timesprobe2times(values, direction='forward')`

**Purpose:** Convert between probe time and session time

**Returns:** Synchronized timestamps

### Utility and Analysis Methods

#### `compute_metrics(spikes, clusters=None)` (Static)

**Purpose:** Calculate quality metrics for spike clusters

**Returns:** DataFrame with cluster quality metrics

#### `merge_clusters(spikes, clusters, channels, **kwargs)` (Static)

**Purpose:** Merge cluster data with channel location and quality metrics

**Returns:** Enhanced clusters dictionary with histology and metrics

#### `get_version(spike_sorter=None)`

**Purpose:** Get the version information of the spike sorting

**Returns:** Version string

### Download Methods

#### `download_spike_sorting(objects=None, **kwargs)`

**Purpose:** Download spike sorting data to local disk

**Parameters:**
- `objects`: List of objects to download (['spikes', 'clusters', 'channels'])

#### `download_raw_electrophysiology(band='ap')`

**Purpose:** Download raw electrophysiology files

**Returns:** List of downloaded file paths

## Data Sources and Hierarchy

The loader automatically selects the best available data source based on this hierarchy:

### Spike Sorting Priority:
1. pykilosort (preferred)
2. iblsorter
3. Shortest collection name (fallback)

### Channel Location Priority:
1. **alf**: Final aligned version (highest quality)
2. **resolved**: Agreed-upon alignments
3. **aligned**: Pending review alignments
4. **traced**: Basic histology trace (lowest quality)

## Complete Example Usage

```python
from one.api import ONE
from brainbox.io.one import SpikeSortingLoader
import numpy as np

one = ONE()
ssl = SpikeSortingLoader(eid='your_session_eid', pname='probe00', one=one)

# Load all spike sorting data
spikes, clusters, channels = ssl.load_spike_sorting()

# Load just channel information
channels = ssl.load_channels()

# Access raw data
sr = ssl.raw_electrophysiology(stream=True, band='ap')

# Convert spike times to session time
spike_times_session = ssl.samples2times(spikes['times'])

# Get good units
good_units = clusters['metrics']['label'] == 2
print(f"Good units: {good_units.sum()}")

# Analyze specific unit
unit_id = 0
unit_spikes = spikes['times'][spikes['clusters'] == unit_id]
unit_channel = clusters['channels'][unit_id]
unit_brain_region = channels['acronym'][unit_channel]
print(f"Unit {unit_id} is in {unit_brain_region}")
```

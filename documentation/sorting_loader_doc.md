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

## Most Useful Methods

### Core Data Loading Methods

#### `load_spike_sorting(spike_sorter='iblsorter', **kwargs)`
**Purpose:** Main method to load spikes, clusters, and channels data
**Parameters:**
- `spike_sorter`: Spike sorting algorithm ('iblsorter', 'pykilosort', etc.)
- `good_units`: If True, loads only good quality units
- `namespace`: Load manually curated data with specific namespace
**Returns:** Tuple of (spikes, clusters, channels) dictionaries

#### `load_channels(**kwargs)`
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

#### `load_spike_sorting_object(obj, **kwargs)`
**Purpose:** Load individual ALF objects (spikes, clusters, or channels)
**Parameters:**
- `obj`: Object type ('spikes', 'clusters', 'channels')
**Returns:** Loaded ALF object data

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

## Example Usage

```python
from one.api import ONE
from brainbox.io.one import SpikeSortingLoader

one = ONE()
ssl = SpikeSortingLoader(eid=eid, pname='probe00', one=one)

# Load all spike sorting data
spikes, clusters, channels = ssl.load_spike_sorting()

# Load just channel information
channels = ssl.load_channels()

# Access raw data
sr = ssl.raw_electrophysiology(stream=True, band='ap')

# Convert spike times to session time
spike_times_session = ssl.samples2times(spikes['times'])
```
# ALF (Alyx File) Data Structure

The ALF naming convention is the foundation of IBL's data organization system. Understanding ALF is essential for working with IBL data, whether accessing it through ONE API or converting it to NWB format.

## Overview

ALF files follow a hierarchical naming pattern that combines folder structure with filename conventions. The complete pattern is:

```
(lab/Subjects/)?subject/YYYY-MM-DD/NNN/(collection/)?(#revision#/)?_namespace_object.attribute(_timescale)?(.extra)*.extension
```

This structured naming enables:
- Automatic metadata extraction from file paths
- Relational data modeling through naming conventions
- Version control through revisions
- Modality separation through collections

## Session Path (Folder Structure)

The folder hierarchy identifies the experimental session:

```
cortexlab/Subjects/KS014/2022-03-21/001/
└── lab ──────────┘ └────subject─────┘ └──date──┘ └─number─┘
```

| Component | Format | Description |
|-----------|--------|-------------|
| `lab/Subjects/` | Optional | Multi-lab organization prefix |
| `subject` | Alphanumeric (`.`, `-` allowed) | Subject identifier |
| `YYYY-MM-DD` | ISO date | Experiment date |
| `NNN` | 1-3 digits | Session number (can be zero-padded: `001`, `002`) |

## Collections

Collections are optional subdirectories that group related data by modality, device, or processing stage:

```
session_path/
├── alf/                    # Standard processed data
│   ├── probe00/           # Per-probe spike sorting
│   └── probe01/
├── raw_ephys_data/        # Raw electrophysiology
│   └── probe00/
├── raw_video_data/        # Raw video files
├── raw_behavior_data/     # Raw behavioral data
└── raw_passive_data/      # Raw passive stimulus data
```

**Common IBL collections:**

| Collection | Contents |
|------------|----------|
| `alf/` | Standard processed ALF files |
| `alf/probe00/`, `alf/probe01/` | Per-probe spike sorting results |
| `raw_ephys_data/` | SpikeGLX raw binary files |
| `raw_video_data/` | Camera video files |
| `raw_behavior_data/` | PyBpod task data |
| `raw_passive_data/` | Passive replay stimulus data |

Collections can be nested with slashes: `alf/widefield/`, `raw_ephys_data/probe00/`

## Revisions

Revisions provide version control for processed data, enclosed in pound signs:

```
alf/#2025-05-06#/spikes.times.npy
     └──revision──┘
```

**Key behaviors:**
- Format: `#revision_name#/`
- Revisions are ordered lexicographically
- If a specific revision isn't found, ONE returns the most recent previous revision
- Common formats: dates (`#2025-05-06#`), versions (`#v1.0.0#`), algorithm names (`#kilosort_3.0#`)

**Brain-Wide Map default revision:** `2025-05-06`

## Filename Components

The filename itself follows the pattern: `_namespace_object.attribute(_timescale)?(.extra)*.extension`

### Namespace (Optional Prefix)

Namespaces identify data sources or processing pipelines, surrounded by underscores:

```
_ibl_trials.choice.npy
└─namespace─┘
```

| Namespace | Source |
|-----------|--------|
| `_ibl_` | IBL standard processed data |
| `_iblrig_` | IBL rig acquisition data |
| `_spikeglx_` | SpikeGLX electrophysiology |
| `_phy_` | Phy spike sorter output |
| `_kilosort_` | Kilosort spike sorter output |
| `_iblmic_` | IBL microphone data |

**Note:** Namespace cannot contain internal underscores (`_name_space_` is invalid).

### Object (Required)

The object represents the core data concept - think of it as a table name where all files with the same object have the same number of rows:

```
trials.choice.npy
└─object─┘
```

**Naming conventions:**
- Use pluralized Haskell/camelCase: `trials`, `spikes`, `clusters`, `wheelMoves`
- All files sharing an object must have the same row count

**Common IBL objects:**

| Object | Description | Row meaning |
|--------|-------------|-------------|
| `trials` | Behavioral trials | One row per trial |
| `spikes` | Spike events | One row per spike |
| `clusters` | Spike clusters/units | One row per cluster |
| `channels` | Recording channels | One row per channel |
| `wheel` | Wheel position samples | One row per sample |
| `wheelMoves` | Wheel movements | One row per movement |
| `leftCamera`, `rightCamera`, `bodyCamera` | Video frames | One row per frame |

### Attribute (Required)

The attribute describes what property of the object is stored:

```
spikes.times.npy
       └─attribute─┘
```

**Reserved attributes with special meaning:**

| Attribute | Format | Description |
|-----------|--------|-------------|
| `times` | 1D array | Discrete event times (seconds, universal timescale) |
| `intervals` | Nx2 array | Start and end times (columns: start, end) |
| `timestamps` | Variable | Continuous timeseries timestamps |

**Common attributes:**

| Attribute | Used with | Description |
|-----------|-----------|-------------|
| `times` | spikes, trials (events) | Event timestamps |
| `intervals` | trials, wheelMoves | Start/end time pairs |
| `clusters` | spikes | Cluster assignment (index into `clusters.*`) |
| `depths` | clusters, channels | Recording depth |
| `amps`, `amplitudes` | spikes, clusters | Spike amplitudes |
| `position` | wheel | Position values |
| `choice` | trials | Subject's choice |
| `feedbackType` | trials | Reward/punishment indicator |

### Timescale (Optional Suffix)

When times are relative to a non-universal clock, add a timescale suffix after an underscore:

```
trials.goCue_times_bpod.npy
              └─timescale─┘
```

| Timescale | Clock source |
|-----------|--------------|
| `_ephysClock` | Electrophysiology recording |
| `_bpod` | Bpod behavior controller |
| `_nidaq` | National Instruments DAQ |

**Default:** No suffix means universal session time (synchronized).

### Extra Parts (Optional)

Additional dot-separated components between attribute and extension serve informational purposes:

```
trials.intervals.a976e418-c8b8-4d24-be47-d05120b18341.npy
                └──────────────extra (UUID)──────────────┘
```

**Uses:**
- UUIDs for unique identification
- File hashes
- Part numbers for multi-part files

**Concatenation rule:** Files with same object/attribute/extension but different extra parts should be concatenated in lexicographical order.

### Extension (Required)

The file extension indicates the data format:

| Extension | Format | Best for |
|-----------|--------|----------|
| `.npy` | NumPy binary | Numeric arrays (preferred) |
| `.pqt` | Parquet | Tabular data with mixed types |
| `.tsv` | Tab-separated | Text data (avoids comma issues) |
| `.csv` | Comma-separated | Simple text data |
| `.bin` | Raw binary | Large continuous data (requires metadata) |
| `.cbin` | Compressed binary | Compressed ephys data |
| `.json` | JSON | Structured metadata |
| `.mp4`, `.avi` | Video | Video recordings |

## Complete Examples

### Spike Sorting Data

```
alf/#2025-05-06#/probe00/spikes.times.npy      # Spike times (seconds)
alf/#2025-05-06#/probe00/spikes.clusters.npy   # Cluster assignment per spike
alf/#2025-05-06#/probe00/spikes.amps.npy       # Spike amplitudes
alf/#2025-05-06#/probe00/spikes.depths.npy     # Spike depths

alf/#2025-05-06#/probe00/clusters.channels.npy # Peak channel per cluster
alf/#2025-05-06#/probe00/clusters.depths.npy   # Cluster depths
alf/#2025-05-06#/probe00/clusters.metrics.pqt  # Quality metrics table
```

**Relational pattern:** `spikes.clusters.npy` contains indices into `clusters.*` files.

### Trial Data

```
alf/_ibl_trials.intervals.npy          # Trial start/end times (Nx2)
alf/_ibl_trials.choice.npy             # Subject choice (-1=left, 1=right, 0=no-go)
alf/_ibl_trials.feedbackType.npy       # Reward (+1) or punishment (-1)
alf/_ibl_trials.contrastLeft.npy       # Left stimulus contrast
alf/_ibl_trials.contrastRight.npy      # Right stimulus contrast
alf/_ibl_trials.goCue_times.npy        # Go cue event times
alf/_ibl_trials.feedback_times.npy     # Feedback delivery times
alf/_ibl_trials.stimOn_times.npy       # Stimulus onset times
```

### Wheel Data

```
alf/wheel.position.npy       # Wheel position (radians)
alf/wheel.timestamps.npy     # Position timestamps
alf/wheelMoves.intervals.npy # Movement start/end times (Nx2)
alf/wheelMoves.peakAmplitude.npy # Movement peak amplitudes
```

### Video and Pose Data

```
raw_video_data/_iblrig_leftCamera.raw.mp4           # Raw video
alf/_ibl_leftCamera.times.npy                       # Frame timestamps
alf/_ibl_leftCamera.dlc.pqt                         # DeepLabCut pose estimates
alf/_ibl_leftCamera.features.pqt                    # Extracted features
alf/_ibl_leftCamera.ROIMotionEnergy.npy             # Motion energy time series
```

### Raw Electrophysiology

```
raw_ephys_data/probe00/_spikeglx_ephysData_g0_t0.imec0.ap.cbin  # Action potential band
raw_ephys_data/probe00/_spikeglx_ephysData_g0_t0.imec0.ap.ch    # Companion header
raw_ephys_data/probe00/_spikeglx_ephysData_g0_t0.imec0.lf.cbin  # Local field potential
raw_ephys_data/probe00/_spikeglx_ephysData_g0_t0.imec0.lf.ch    # Companion header
```

## Accessing ALF Data with ONE API

### Loading by Dataset Name

```python
from one.api import ONE
one = ONE()

# Load single dataset
spike_times = one.load_dataset(eid, 'spikes.times.npy', collection='alf/probe00')

# Load with revision
spike_times = one.load_dataset(eid, 'spikes.times.npy',
                                collection='alf/probe00',
                                revision='2025-05-06')
```

### Loading Object (All Attributes)

```python
# Load all attributes of an object as a dictionary
spikes = one.load_object(eid, 'spikes', collection='alf/probe00')
# Returns: {'times': array, 'clusters': array, 'amps': array, ...}

# Load specific attributes only
spikes = one.load_object(eid, 'spikes', collection='alf/probe00',
                         attribute=['times', 'clusters'])
```

### Listing Available Datasets

```python
# List all datasets for a session
datasets = one.list_datasets(eid)

# Filter by collection
datasets = one.list_datasets(eid, collection='alf/probe00')

# Filter by object
datasets = one.list_datasets(eid, filename='spikes.*')
```

### Path Utilities

```python
from one.alf.path import ALFPath

# Parse ALF path
path = ALFPath('/data/lab/Subjects/mouse/2023-01-15/001/alf/spikes.times.npy')
print(path.subject)      # 'mouse'
print(path.session_date) # datetime(2023, 1, 15)
print(path.object)       # 'spikes'
print(path.attribute)    # 'times'
print(path.extension)    # 'npy'
```

## Validation Rules

1. **Required components:** Object, attribute, and extension are mandatory
2. **Row consistency:** All files with the same object must have the same number of rows
3. **Reserved attributes:** `times` for discrete events, `intervals` for time ranges, `timestamps` for continuous series
4. **Namespace format:** Must not contain internal underscores
5. **Character restrictions:** Object and attribute use alphanumeric characters in camelCase

## Relational Data Modeling

ALF uses naming conventions to express relationships between objects:

```
spikes.clusters.npy  →  Links to: clusters.*
                        (values are indices into cluster files)

clusters.channels.npy → Links to: channels.*
                        (values are indices into channel files)
```

**Pattern:** When an attribute name matches another object name, the values are indices into that object's files.

## Related Documentation

- [Session Loader](session_loader.md) - High-level data loading
- [Spike Sorting Loader](spike_sorting_loader.md) - Ephys data access
- [IBL Synchronization](../ibl_concepts/ibl_synchronization.md) - Multi-clock alignment

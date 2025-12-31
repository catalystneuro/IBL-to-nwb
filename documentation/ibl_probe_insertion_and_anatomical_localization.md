# IBL Probe Insertion Documentation

## Overview

**Probe insertion** is the cornerstone experimental technique of the IBL Brain Wide Map project, involving the systematic implantation of **Neuropixels probes** into mouse brains to record neural activity across virtually all brain regions. Each insertion represents a unique recording session where a silicon probe records from hundreds of neurons simultaneously.

## Scientific Purpose

### Brain Wide Map Strategy
- **Systematic sampling**: Record from all major brain areas using a standardized grid system
- **Cross-laboratory replication**: Each target brain area recorded in at least 2 laboratories
- **Single-spike resolution**: Capture individual neuron activity across the entire brain
- **Decision-making focus**: Study neural basis of perceptual decision-making during behavior

### Why Probe Insertions Matter
- **Cell-type specificity**: Record from individual neurons vs. population signals
- **Temporal precision**: Millisecond timing resolution for spike trains
- **Spatial coverage**: Sample from multiple brain regions simultaneously
- **Anatomical precision**: Know exact location of each recorded neuron

## Experimental Procedure

### 1. Pre-surgical Planning

**Target Selection**:
- **Coordinate system**: Allen Brain Atlas Common Coordinate Framework (CCF)
- **Grid-based sampling**: Systematic coverage of brain areas
- **Stereotactic coordinates**: ML (medial-lateral), AP (anterior-posterior), DV (dorsal-ventral)

**Probe Selection**:
- **Neuropixels 1.0**: 384 channels, 3.84 mm long shank
- **Channel layout**: 384 recording sites distributed along probe length
- **Spatial resolution**: 20 um spacing between recording sites

### 2. Surgical Insertion

**Procedure**:
1. **Anesthesia**: Isoflurane anesthesia throughout procedure
2. **Craniotomy**: Small opening above target brain region
3. **Dura removal**: Access to brain tissue
4. **Probe advancement**: Slow insertion using micromanipulator
5. **Settling time**: 30+ minutes for tissue stabilization

**Critical Parameters**:
- **Insertion angle**: Typically vertical or with slight angle
- **Insertion speed**: ~10 um/s to minimize tissue damage
- **Target depth**: Variable based on brain region of interest
- **Brain surface detection**: Electrical impedance changes mark entry

### 3. Recording Session

**Timeline**:
- **Pre-task baseline**: 5-10 minutes spontaneous activity
- **Behavioral task**: 1-2 hours of decision-making behavior
- **Passive stimulation**: 10-20 minutes of sensory stimuli
- **Post-task recording**: Additional spontaneous activity

**Data Acquisition**:
- **Sampling rate**: 30 kHz for action potentials (AP band)
- **Filtering**: 300 Hz - 10 kHz bandpass for spikes
- **LFP recording**: 2.5 kHz sampling, 0.5-300 Hz bandpass
- **Synchronization**: All data streams precisely time-aligned

## IBL Data Extraction and APIs

### Core Concept: Probe Insertion ID (PID)

**What is a PID?**
- **Unique identifier**: Each probe insertion has a UUID (e.g., `'da8dfec1-d265-44e8-84ce-6ae9c109b8bd'`)
- **Database key**: Links all data from a specific probe insertion
- **Cross-reference**: Connects anatomical, electrophysiological, and behavioral data

**Relationship to Other IDs**:
- **Session ID (EID)**: Multiple probes can be inserted in one session
- **Probe name**: Human-readable name (e.g., 'probe00', 'probe01')

### 1. Finding Probe Insertions

#### Search by Brain Region
```python
from one.api import ONE
one = ONE()

# Find all insertions in visual cortex
insertions_vis = one.search_insertions(atlas_acronym='VIS', project='brainwide')

# Find all insertions in thalamus
insertions_th = one.search_insertions(atlas_acronym='TH', project='brainwide')

# Find insertions with specific datasets
insertions_spikes = one.search_insertions(datasets='spikes.times.npy', project='brainwide')
```

#### Get Insertions for a Session
```python
# Get all probe insertions for a specific session
eid = '4ecb5d24-f5cc-402c-be28-9d0f7cb14b3a'
insertions = one.alyx.rest('insertions', 'list', session=eid)

# Extract probe information
for ins in insertions:
    print(f"Probe: {ins['name']}, PID: {ins['id']}")
    print(f"Target: {ins['json'].get('target', 'Unknown')}")
```

#### Convert Between IDs
```python
# Convert PID to session EID and probe name
pid = 'da8dfec1-d265-44e8-84ce-6ae9c109b8bd'
eid, probe_name = one.pid2eid(pid)

print(f"Session: {eid}")
print(f"Probe: {probe_name}")
```

### 2. Loading Probe Data

#### Using SpikeSortingLoader
```python
from brainbox.io.one import SpikeSortingLoader
from iblatlas.atlas import AllenAtlas

# Initialize loader with PID
ssl = SpikeSortingLoader(pid=pid, one=one, atlas=AllenAtlas())

# Load spike sorting data
spikes, clusters, channels = ssl.load_spike_sorting()

# Alternative: Initialize with EID and probe name
ssl = SpikeSortingLoader(eid=eid, pname=probe_name, one=one)
```

#### Using SessionLoader for Multi-probe Sessions
```python
from brainbox.io.one import SessionLoaderEphys

# Load all probes for a session
session_loader = SessionLoaderEphys(one=one, eid=eid)
session_loader.load_spike_sorting()

# Access individual probes
for probe_name, probe_data in session_loader.ephys.items():
    spikes = probe_data['spikes']
    clusters = probe_data['clusters']
```

### 3. Probe Metadata and Trajectory Information

#### Basic Insertion Information
```python
# Get detailed insertion information
insertion = one.alyx.rest('insertions', 'list', session=eid, name=probe_name)[0]

print(f"Insertion ID: {insertion['id']}")
print(f"Probe name: {insertion['name']}")
print(f"Target region: {insertion['json'].get('target')}")
print(f"Depth: {insertion['json'].get('depth_um')} um")
```

#### Trajectory and Alignment Data
```python
# Get probe trajectory information
trajectories = one.alyx.rest('trajectories', 'list',
                           probe_insertion=pid,
                           provenance='Ephys aligned histology track')

if trajectories:
    traj = trajectories[0]
    print(f"Trajectory ID: {traj['id']}")
    print(f"Provenance: {traj['provenance']}")
    print(f"Coordinates: {traj['x']}, {traj['y']}, {traj['z']}")
    print(f"Angles: {traj['theta']}, {traj['phi']}")
```

## Probe Insertion Variables and Meanings

### 1. Insertion Object Variables

#### Core Identification
| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | UUID | Unique probe insertion identifier | `'da8dfec1-d265-44e8-84ce-6ae9c109b8bd'` |
| `name` | str | Human-readable probe name | `'probe00'`, `'probe01'` |
| `session` | UUID | Parent session identifier | Link to experimental session |


#### JSON Field Contents
```python
insertion['json'] = {
    'target': 'Target brain region',
    'depth_um': 4000,  # Insertion depth in micrometers
    'xyz_picks': [[x1, y1, z1], [x2, y2, z2]],  # Histology trace points
    'extended_qc': {
        'alignment_resolved': True/False,  # Final alignment complete
        'alignment_stored': True/False,    # Alignment saved to database
        'tracing_exists': True/False,      # Histology tracing available
        'alignment_count': 3               # Number of alignment attempts
    }
}
```

### 2. Channel Location Variables

When loading channels via `ssl.load_spike_sorting()`:

#### Spatial Coordinates
| Variable | Type | Shape | Description |
|----------|------|-------|-------------|
| `x` | ndarray | (n_channels,) | ML coordinates in CCF (meters) |
| `y` | ndarray | (n_channels,) | AP coordinates in CCF (meters) |
| `z` | ndarray | (n_channels,) | DV coordinates in CCF (meters) |
| `axial_um` | ndarray | (n_channels,) | Distance along probe from tip (um) |
| `lateral_um` | ndarray | (n_channels,) | Lateral offset from probe center (um) |

#### Anatomical Assignment
| Variable | Type | Shape | Description |
|----------|------|-------|-------------|
| `atlas_id` | ndarray | (n_channels,) | Allen Brain Atlas region ID |
| `acronym` | ndarray | (n_channels,) | Brain region acronym |
| `rawInd` | ndarray | (n_channels,) | Raw channel indices from recording |

### 3. Trajectory Variables

#### Trajectory Object Fields
| Variable | Type | Description |
|----------|------|-------------|
| `id` | UUID | Unique trajectory identifier |
| `probe_insertion` | UUID | Link to parent insertion |
| `provenance` | str | Data source/creation method |
| `x`, `y`, `z` | float | Entry point coordinates (um) |
| `theta`, `phi` | float | Insertion angles (degrees) |
| `depth` | float | Total insertion depth (um) |
| `roll` | float | Probe rotation angle (degrees) |

#### Trajectory Provenance Types
- **`'Planned'`**: Pre-surgical target coordinates
- **`'Micro-manipulator'`**: Recorded manipulator coordinates
- **`'Histology track'`**: Traced from post-mortem histology
- **`'Ephys aligned histology track'`**: Aligned using electrophysiology

### 4. Quality Control Variables

#### Extended QC Fields
```python
qc_fields = {
    'alignment_resolved': bool,    # Final alignment approved
    'alignment_stored': bool,      # Data saved to files
    'tracing_exists': bool,        # Histology tracing available
    'alignment_count': int,        # Number of alignment attempts
    'insertion_qc': str,          # Overall insertion quality
    'drift_rms_um': float,        # Electrode drift estimate
    'noise_cutoff': dict          # Noise level thresholds
}
```

## Histology and Localization Status

The IBL SpikeSortingLoader determines histology quality through a hierarchical system that prioritizes local ALF files over database trajectory data. The `histology` attribute indicates the reliability of channel brain location data.

### Histology Quality Levels (Best to Worst)

#### 1. 'alf' - Highest Quality
- **Source**: Pre-computed brain locations in local ALF files
- **Location**: `alf/{probe_name}/` collections
- **Key Files**:
  - `channels.brainLocationIds_ccf_2017.npy`
  - `channels.atlas_id.npy`
  - `channels.x.npy`, `channels.y.npy`, `channels.z.npy`
  - `channels.acronym.npy` (optional)
  - `electrodeSites.*` files (alternative)
- **Quality**: Final, validated channel locations ready for analysis

#### 2. 'resolved' - High Quality
- **Source**: Alyx database with finalized alignments
- **API Check**: `insertion['json']['extended_qc']['alignment_resolved'] = True`
- **Data Sources**:
  - `insertion['json']['xyz_picks']` - Raw tracing coordinates
  - `trajectory['json'][align_key]` - Validated alignment data
- **Quality**: Manually reviewed and approved by experts

#### 3. 'aligned' - Medium Quality
- **Source**: Alyx database with pending alignments
- **API Check**: `insertion['json']['extended_qc']['alignment_count'] > 0`
- **Data Sources**: Same as 'resolved' but not yet validated
- **Quality**: Aligned but awaiting review - potentially inaccurate

#### 4. 'traced' - Basic Quality
- **Source**: Raw histology tracing from microscopy
- **API Check**: `insertion['json']['extended_qc']['tracing_exists'] = True`
- **Data Sources**: Only `insertion['json']['xyz_picks']` coordinates
- **Quality**: Basic trace, depths may not match ephys data

#### 5. '' (Empty) - No Data
- **Condition**: No histology tracing exists in database
- **Warning**: "Histology tracing for {probe} does not exist"
- **Quality**: No brain location data available

### How Histology Quality is Determined

#### Primary Check: ALF Files
```python
if 'brainLocationIds_ccf_2017' not in channels:
    # Load from database trajectory
    _channels, self.histology = _load_channel_locations_traj(
        self.eid, probe=self.pname, one=self.one,
        brain_atlas=self.atlas, return_source=True, aligned=True)
else:
    # Use pre-computed ALF data
    channels = _channels_alf2bunch(channels, brain_regions=self.atlas.regions)
    self.histology = 'alf'
```

#### Database Trajectory Check
```python
# Check trajectory quality
tracing = insertion['json']['extended_qc']['tracing_exists']
resolved = insertion['json']['extended_qc']['alignment_resolved']
counts = insertion['json']['extended_qc']['alignment_count']

if tracing and resolved:
    self.histology = 'resolved'
elif counts > 0 and aligned:
    self.histology = 'aligned'
elif tracing:
    self.histology = 'traced'
else:
    self.histology = ''  # No data
```

### REST API Endpoints for Histology

#### Insertion Data
```
GET /insertions?session={eid}&name={probe}
```
**Key Fields**:
- `json.xyz_picks` - Raw tracing coordinates
- `json.extended_qc.tracing_exists` - Boolean
- `json.extended_qc.alignment_resolved` - Boolean
- `json.extended_qc.alignment_count` - Integer
- `json.extended_qc.alignment_stored` - Alignment key

#### Trajectory Data
```
GET /trajectories?session={eid}&probe={probe}&provenance=Ephys%20aligned%20histology%20track
```
**Key Fields**:
- `json[alignment_key][0]` - Feature data
- `json[alignment_key][1]` - Track data

### Required Additional Files for Histology

#### Local Coordinates
- **File**: `channels.localCoordinates.npy`
- **Purpose**: Maps channel depths for trajectory interpolation
- **Location**: `alf/{probe_name}/` collection

## Data Analysis Applications

### 1. Multi-region Analysis
```python
# Load data from multiple brain regions
insertions_cortex = one.search_insertions(atlas_acronym='CTX', project='brainwide')
insertions_thalamus = one.search_insertions(atlas_acronym='TH', project='brainwide')

# Compare activity across regions
for pid in insertions_cortex[:5]:  # First 5 cortical insertions
    ssl = SpikeSortingLoader(pid=pid, one=one)
    spikes, clusters, channels = ssl.load_spike_sorting()
    # Analyze cortical activity patterns
```

### 2. Anatomical Filtering with Histology Quality Check
```python
from brainbox.io.one import SpikeSortingLoader

ssl = SpikeSortingLoader(pid=pid, one=one)

# Check histology quality before anatomical analysis
print(f"Histology source: {ssl.histology}")
# Possible values: 'alf', 'resolved', 'aligned', 'traced', ''

# Only use high-quality anatomical localizations
if ssl.histology in ['resolved', 'alf']:
    spikes, clusters, channels = ssl.load_spike_sorting()

    # Filter clusters by brain region
    visual_clusters = clusters[clusters['acronym'].str.contains('VIS')]
    motor_clusters = clusters[clusters['acronym'].str.contains('MOp')]

    # Access channel brain locations
    print(f"Brain regions: {channels.acronym}")
    print(f"Atlas coordinates: {channels.x}, {channels.y}, {channels.z}")
else:
    print("Warning: Anatomical locations may be inaccurate")
```

### 3. Trajectory Analysis
```python
# Compare planned vs. actual insertion coordinates
insertion = one.alyx.rest('insertions', 'list', id=pid)[0]
planned_coords = (insertion['x'], insertion['y'], insertion['z'])

# Get actual trajectory from histology
trajectories = one.alyx.rest('trajectories', 'list',
                           probe_insertion=pid,
                           provenance='Histology track')
if trajectories:
    actual_coords = (trajectories[0]['x'], trajectories[0]['y'], trajectories[0]['z'])
    deviation = np.linalg.norm(np.array(actual_coords) - np.array(planned_coords))
    print(f"Insertion deviation: {deviation:.0f} um")
```

### 4. Cross-laboratory Comparisons
```python
# Find repeated recordings of the same brain region
target_region = 'VISp'  # Primary visual cortex
insertions = one.alyx.rest('insertions', 'list',
                          django=f'channels__brain_region__acronym__icontains,{target_region}')

# Group by laboratory
lab_groups = {}
for ins in insertions:
    session = one.alyx.rest('sessions', 'read', id=ins['session'])
    lab = session['lab']
    if lab not in lab_groups:
        lab_groups[lab] = []
    lab_groups[lab].append(ins['id'])

print(f"Found {target_region} recordings in {len(lab_groups)} laboratories")
```

## File Structure and Data Organization

### Directory Organization
```
session_path/
├── alf/
│   ├── probe00/                 # First probe data
│   │   ├── spikes.times.npy     # Spike timestamps
│   │   ├── spikes.clusters.npy  # Spike cluster assignments
│   │   ├── clusters.channels.npy # Cluster channel assignments
│   │   ├── channels.*.npy       # Channel location data
│   │   ├── channels.brainLocationIds_ccf_2017.npy  # Brain region IDs
│   │   ├── channels.localCoordinates.npy           # Local probe coordinates
│   │   └── electrodeSites.*     # Alternative electrode site files
│   └── probe01/                 # Second probe data (if present)
└── raw_ephys_data/
    ├── probe00/                 # Raw data from first probe
    │   ├── *.ap.cbin           # Compressed action potential data
    │   ├── *.lf.cbin           # Compressed LFP data
    │   └── *.meta              # Recording metadata
    └── probe01/                 # Raw data from second probe
```

### Data Access Patterns
```python
# Method 1: Direct file access
session_path = one.eid2path(eid)
probe_files = list((session_path / 'alf' / probe_name).glob('*.npy'))

# Method 2: ONE API access
spikes_times = one.load_dataset(eid, 'spikes.times.npy',
                               collection=f'alf/{probe_name}')

# Method 3: SpikeSortingLoader (recommended)
ssl = SpikeSortingLoader(pid=pid, one=one)
spikes, clusters, channels = ssl.load_spike_sorting()
```

## Best Practices

### 1. Quality Control
```python
# Always check histology quality before anatomical analysis
ssl = SpikeSortingLoader(pid=pid, one=one)
print(f"Histology quality: {ssl.histology}")

if ssl.histology not in ['resolved', 'alf']:
    print("Warning: Anatomical locations may be inaccurate")
```

### 2. Data Validation
```python
# Verify data completeness
required_datasets = ['spikes.times', 'spikes.clusters', 'clusters.channels']
available = one.list_datasets(eid, collection=f'alf/{probe_name}')

for dataset in required_datasets:
    if not any(dataset in ds for ds in available):
        print(f"Missing dataset: {dataset}")
```

### 3. Cross-reference Verification
```python
# Ensure PID matches expected session and probe
eid_check, pname_check = one.pid2eid(pid)
assert eid_check == eid, "PID does not match expected session"
assert pname_check == probe_name, "PID does not match expected probe"
```

## Coordinate Systems and the ASL vs PIR Mismatch

### Overview of the Problem

When storing Allen CCF coordinates in NWB files using the `ndx-anatomical-localization` extension, there is a **critical mismatch** between how the `AllenCCFv3Space` declares its orientation and how Allen CCF data is actually stored.

### The Three-Letter Orientation Convention

In neuroimaging, coordinate systems are described using three-letter codes indicating the **positive direction** of each axis:

| Letter | Meaning |
|--------|---------|
| **R** | Right (+x points right) |
| **L** | Left (+x points left) |
| **A** | Anterior (+y points forward) |
| **P** | Posterior (+y points backward) |
| **S** | Superior (+z points up/dorsal) |
| **I** | Inferior (+z points down/ventral) |

For example:
- **RAS**: +x=Right, +y=Anterior, +z=Superior (common in neuroimaging)
- **PIR**: +x=Posterior, +y=Inferior, +z=Right (Allen CCF actual convention)
- **ASL**: +x=Anterior, +y=Superior, +z=Left (what ndx-anatomical-localization declares)

### The Source of Confusion

Allen Institute documentation describes their CCF as:

> "ASL orientation such that first (x) axis is **anterior-to-posterior**, second (y) axis is **superior-to-inferior**, third (z) axis is **left-to-right**"

This phrase is **ambiguous** and can be interpreted two ways:

```
Interpretation A: "axis goes FROM anterior TO posterior"
  -> Origin at Anterior, values INCREASE toward Posterior
  -> +x = Posterior (PIR convention)

Interpretation B: "axis represents A-P, positive toward Anterior"
  -> +x = Anterior (ASL convention)
```

### The Two Meanings of "ASL": Origin vs Direction of Increase

The three-letter orientation code (e.g., "ASL", "PIR", "RAS") is used in two fundamentally different ways in neuroscience software, which is the root cause of this confusion:

#### Convention 1: Letters Describe the ORIGIN Location

In this convention, "ASL" means:
- The **origin** (coordinate [0, 0, 0]) is at the **A**nterior-**S**uperior-**L**eft corner
- Values **increase away** from that corner (toward Posterior, Inferior, Right)

```
      Superior (y=0)
           ^
           |
    A------+------P
   /|      |origin|
  L |      |      | R
    |      v      |
    +------+------+
           |
      Inferior (y increases)

Origin at ASL corner: coordinates increase toward PIR
```

This is what Allen Institute's documentation appears to describe when they say "origin at the dorsal-left-posterior corner" (which is ASL in their terminology, confusingly).

#### Convention 2: Letters Describe the POSITIVE DIRECTION

In this convention (used by neuroimaging tools like NIfTI, BIDS, and brainglobe), "ASL" means:
- **+x** points toward **A**nterior
- **+y** points toward **S**uperior
- **+z** points toward **L**eft

```
      Superior (+y)
           ^
           |
    P------+------A  (+x)
   /       |
  R        |       L (+z)
           |
    +------+------+
           |
      Inferior (-y)

+x = Anterior, +y = Superior, +z = Left
```

#### The Critical Difference

| Aspect | Convention 1 (Origin) | Convention 2 (Direction) |
|--------|----------------------|--------------------------|
| "ASL" means... | Origin is at ASL corner | +x/y/z point toward A/S/L |
| If origin is at ASL corner... | Code would be "ASL" | Code would be "PIR" (values increase toward PIR) |
| Allen CCF in this convention | Would be called "ASL" | Would be called "PIR" |

#### What Different Tools Use

| Tool/Library | Convention | Allen CCF Orientation Code |
|--------------|------------|---------------------------|
| Allen Institute docs | Origin location | "ASL" (describes origin corner) |
| ndx-anatomical-localization | **Direction of increase** (per NWB spec) | Declares "ASL" (WRONG) |
| BrainGlobe | Direction of increase | "asr" (correct for their volume order) |
| iblatlas | Internal RAS, outputs PIR | Returns PIR-ordered coordinates |
| NIfTI/BIDS | Direction of increase | Would be "PIR" |

#### Why This Matters

The `ndx-anatomical-localization` extension uses **Convention 2** (direction of increase) as stated in the NWB specification. However, `AllenCCFv3Space` was defined using Allen Institute's "ASL" label, which follows **Convention 1** (origin location).

This results in the declared orientation being **exactly opposite** to the actual data:
- Declared: "ASL" (+x=Anterior, +y=Superior, +z=Left)
- Actual: PIR (+x=Posterior, +y=Inferior, +z=Right)

A consumer of NWB files using the metadata would flip all coordinates on all three axes.

#### Verification with BrainGlobe

BrainGlobe's `brainglobe-atlasapi` reports the Allen atlas orientation as `"asr"`, meaning:
- Axis 0: increases toward **A**nterior (their volume is reoriented)
- Axis 1: increases toward **S**uperior
- Axis 2: increases toward **R**ight

BrainGlobe's space module documentation explicitly states they use direction-of-increase convention. Their atlas has been reoriented from the raw Allen data for consistency with neuroimaging standards.

### What Allen CCF Data Actually Contains

The Allen CCF volume has:
- **Origin**: At the Anterior-Superior-Left corner of the 3D image
- **Values increase toward**: Posterior, Inferior (Ventral), Right
- **Effective orientation**: **PIR** (in terms of positive direction)

This can be verified empirically:

```python
from iblatlas.atlas import AllenAtlas
import numpy as np

atlas = AllenAtlas()

# Bregma at origin in IBL coordinates
bregma = np.array([[0, 0, 0]])
bregma_ccf = atlas.xyz2ccf(bregma, ccf_order='apdvml')
# Result: [5400, 332, 5739] um

# Point 1mm posterior to bregma
posterior = np.array([[0, -0.001, 0]])  # IBL: -y = posterior
posterior_ccf = atlas.xyz2ccf(posterior, ccf_order='apdvml')
# Result: [6400, 332, 5739] um

# x increased by 1000um when moving posterior
# Therefore: +x = Posterior direction
```

### The ndx-anatomical-localization Mismatch

The `AllenCCFv3Space` class in ndx-anatomical-localization declares:

```python
AllenCCFv3Space:
    orientation: "ASL"  # Claims +x=Anterior, +y=Superior, +z=Left
    origin: "Dorsal-left-posterior corner of the 3D image volume"
```

But the actual Allen CCF data (as returned by iblatlas, brainglobe, Allen SDK) has:
- **+x = Posterior** (not Anterior)
- **+y = Inferior** (not Superior)
- **+z = Right** (not Left)

This is **PIR**, the exact opposite of the declared **ASL**.

### Verification Results

Running the verification script on IBL NWB files:

```
TABLE: AnatomicalCoordinatesTableElectrodesCCFv3
  Declared orientation: ASL

Region verification:
  Interpreting as PIR (what iblatlas outputs): 768/768 (100.0%)
  Interpreting as ASL (what's declared):       0/768 (0.0%)

CONCLUSION: Data is stored as PIR but declared as ASL
```

When coordinates are interpreted as **PIR** (ignoring the declaration), brain region lookups match 100%. When interpreted as **ASL** (trusting the declaration), all electrodes map to "void" (outside the brain).

### Impact on Users

A user reading an NWB file with `AllenCCFv3Space` who trusts the metadata would:
1. Read `orientation="ASL"`
2. Interpret coordinates as +x=Anterior, +y=Superior, +z=Left
3. Get **completely wrong** brain locations (inverted on all three axes)

### The IBL Bregma Table is Correct

The second anatomical coordinates table (`AnatomicalCoordinatesTableElectrodesIBLBregma`) uses a custom `Space` with:

```python
Space:
    name: "IBLBregma"
    orientation: "RAS"  # +x=Right, +y=Anterior, +z=Superior
    origin: "bregma"
    units: "um"
```

This table stores IBL coordinates directly (bregma-centered, RAS orientation) and verification shows 100% match. The declared orientation matches the actual data.

### Recommended Fix

The fix should be in **ndx-anatomical-localization**. Change `AllenCCFv3Space` to:

```python
class AllenCCFv3Space(Space):
    def __init__(self, name="AllenCCFv3"):
        super().__init__(
            name=name,
            space_name="AllenCCFv3",
            origin="Anterior-superior-left corner of the 3D image volume",
            units="um",
            orientation="PIR",  # Changed from "ASL"
        )
```

This matches:
1. What Allen CCF data actually contains
2. What iblatlas, brainglobe, and Allen SDK return
3. The neuroimaging convention that orientation codes describe positive direction

### Verification Script

A verification script is available at `build/verify_electrode_coordinates.py` that:
1. Loads electrode coordinates from NWB files
2. Tests multiple coordinate interpretations
3. Compares stored brain regions with atlas lookups
4. Generates plots showing electrodes on brain slices

Run with:
```bash
uv run python build/verify_electrode_coordinates.py
```

### Summary Table

| Table | Declared | Actual | Match Rate | Status |
|-------|----------|--------|------------|--------|
| IBLBregma | RAS | RAS | 100% | Correct |
| AllenCCFv3 | ASL | PIR | 0% (if trusted) | Bug |

## Troubleshooting

### "Histology tracing does not exist"
- **Cause**: No tracing data in Alyx database
- **Solution**: Use probe without brain location data or find alternative session
- **Result**: `histology = ''` and no brain region assignments

### File Size Mismatch Warnings
- **Cause**: Database metadata out of sync with S3 files
- **Solution**: Use `cache_rest=None` in ONE constructor
- **Impact**: Does not affect histology loading, only file validation

## Summary

IBL probe insertions represent a systematic approach to mapping brain function:

- **Standardized procedure**: Consistent methodology across laboratories
- **Precise localization**: Combine electrophysiology with histological verification
- **Rich metadata**: Comprehensive tracking of insertion parameters and quality
- **Cross-referenced data**: Links behavioral, neural, and anatomical information
- **Quality control**: Multiple levels of verification for anatomical assignments
- **Flexible access**: Multiple APIs for different analysis needs
- **Histology hierarchy**: Five quality levels (alf > resolved > aligned > traced > none)

The probe insertion system enables large-scale, quantitative neuroscience by providing standardized, high-quality neural recordings with precise anatomical localization across the entire mouse brain.

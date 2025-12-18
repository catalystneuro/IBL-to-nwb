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

### 1. **Pre-surgical Planning**

**Target Selection**:
- **Coordinate system**: Allen Brain Atlas Common Coordinate Framework (CCF)
- **Grid-based sampling**: Systematic coverage of brain areas
- **Stereotactic coordinates**: ML (medial-lateral), AP (anterior-posterior), DV (dorsal-ventral)

**Probe Selection**:
- **Neuropixels 1.0**: 384 channels, 3.84 mm long shank
- **Channel layout**: 384 recording sites distributed along probe length
- **Spatial resolution**: 20 μm spacing between recording sites

### 2. **Surgical Insertion**

**Procedure**:
1. **Anesthesia**: Isoflurane anesthesia throughout procedure
2. **Craniotomy**: Small opening above target brain region
3. **Dura removal**: Access to brain tissue
4. **Probe advancement**: Slow insertion using micromanipulator
5. **Settling time**: 30+ minutes for tissue stabilization

**Critical Parameters**:
- **Insertion angle**: Typically vertical or with slight angle
- **Insertion speed**: ~10 μm/s to minimize tissue damage
- **Target depth**: Variable based on brain region of interest
- **Brain surface detection**: Electrical impedance changes mark entry

### 3. **Recording Session**

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

### 1. **Finding Probe Insertions**

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

### 2. **Loading Probe Data**

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

### 3. **Probe Metadata and Trajectory Information**

#### Basic Insertion Information
```python
# Get detailed insertion information
insertion = one.alyx.rest('insertions', 'list', session=eid, name=probe_name)[0]

print(f"Insertion ID: {insertion['id']}")
print(f"Probe name: {insertion['name']}")
print(f"Target region: {insertion['json'].get('target')}")
print(f"Depth: {insertion['json'].get('depth_um')} μm")
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

### 1. **Insertion Object Variables**

#### Core Identification
| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `id` | UUID | Unique probe insertion identifier | `'da8dfec1-d265-44e8-84ce-6ae9c109b8bd'` |
| `name` | str | Human-readable probe name | `'probe00'`, `'probe01'` |
| `session` | UUID | Parent session identifier | Link to experimental session |

#### Spatial Information
| Variable | Type | Description | Units |
|----------|------|-------------|-------|
| `x` | float | ML coordinate in CCF space | μm |
| `y` | float | AP coordinate in CCF space | μm |
| `z` | float | DV coordinate in CCF space | μm |
| `theta` | float | Polar angle (from vertical) | degrees |
| `phi` | float | Azimuth angle | degrees |
| `depth` | float | Insertion depth | μm |

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

### 2. **Channel Location Variables**

When loading channels via `ssl.load_spike_sorting()`:

#### Spatial Coordinates
| Variable | Type | Shape | Description |
|----------|------|-------|-------------|
| `x` | ndarray | (n_channels,) | ML coordinates in CCF (meters) |
| `y` | ndarray | (n_channels,) | AP coordinates in CCF (meters) |
| `z` | ndarray | (n_channels,) | DV coordinates in CCF (meters) |
| `axial_um` | ndarray | (n_channels,) | Distance along probe from tip (μm) |
| `lateral_um` | ndarray | (n_channels,) | Lateral offset from probe center (μm) |

#### Anatomical Assignment
| Variable | Type | Shape | Description |
|----------|------|-------|-------------|
| `atlas_id` | ndarray | (n_channels,) | Allen Brain Atlas region ID |
| `acronym` | ndarray | (n_channels,) | Brain region acronym |
| `rawInd` | ndarray | (n_channels,) | Raw channel indices from recording |

### 3. **Histology Provenance Levels**

The `ssl.histology` property indicates the quality of anatomical localization:

#### Provenance Hierarchy (Best to Worst)
1. **`'alf'`**: Final, file-stored channel locations
   - Data written to permanent files
   - Highest confidence in anatomical assignments
   - Ready for publication use

2. **`'resolved'`**: Consensus alignment achieved
   - Multiple experts agree on alignment
   - High confidence in locations
   - Awaiting file generation

3. **`'aligned'`**: Alignment completed, pending review
   - Initial alignment done
   - May require verification
   - Use with caution for anatomical claims

4. **`'traced'`**: Histology track recovered
   - Probe track visible in histology
   - Depths may not match recording
   - Preliminary anatomical information

5. **`None` or missing**: No histology available
   - Only planned coordinates available
   - No anatomical verification
   - Avoid making anatomical claims

### 4. **Trajectory Variables**

#### Trajectory Object Fields
| Variable | Type | Description |
|----------|------|-------------|
| `id` | UUID | Unique trajectory identifier |
| `probe_insertion` | UUID | Link to parent insertion |
| `provenance` | str | Data source/creation method |
| `x`, `y`, `z` | float | Entry point coordinates (μm) |
| `theta`, `phi` | float | Insertion angles (degrees) |
| `depth` | float | Total insertion depth (μm) |
| `roll` | float | Probe rotation angle (degrees) |

#### Trajectory Provenance Types
- **`'Planned'`**: Pre-surgical target coordinates
- **`'Micro-manipulator'`**: Recorded manipulator coordinates
- **`'Histology track'`**: Traced from post-mortem histology
- **`'Ephys aligned histology track'`**: Aligned using electrophysiology

### 5. **Quality Control Variables**

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

## Data Analysis Applications

### 1. **Multi-region Analysis**
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

### 2. **Anatomical Filtering**
```python
# Only use high-quality anatomical localizations
ssl = SpikeSortingLoader(pid=pid, one=one)
if ssl.histology in ['resolved', 'alf']:
    spikes, clusters, channels = ssl.load_spike_sorting()

    # Filter clusters by brain region
    visual_clusters = clusters[clusters['acronym'].str.contains('VIS')]
    motor_clusters = clusters[clusters['acronym'].str.contains('MOp')]
```

### 3. **Trajectory Analysis**
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
    print(f"Insertion deviation: {deviation:.0f} μm")
```

### 4. **Cross-laboratory Comparisons**
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
│   │   └── channels.*.npy       # Channel location data
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

### 1. **Quality Control**
```python
# Always check histology quality before anatomical analysis
ssl = SpikeSortingLoader(pid=pid, one=one)
print(f"Histology quality: {ssl.histology}")

if ssl.histology not in ['resolved', 'alf']:
    print("Warning: Anatomical locations may be inaccurate")
```

### 2. **Data Validation**
```python
# Verify data completeness
required_datasets = ['spikes.times', 'spikes.clusters', 'clusters.channels']
available = one.list_datasets(eid, collection=f'alf/{probe_name}')

for dataset in required_datasets:
    if not any(dataset in ds for ds in available):
        print(f"Missing dataset: {dataset}")
```

### 3. **Cross-reference Verification**
```python
# Ensure PID matches expected session and probe
eid_check, pname_check = one.pid2eid(pid)
assert eid_check == eid, "PID does not match expected session"
assert pname_check == probe_name, "PID does not match expected probe"
```

## Summary

IBL probe insertions represent a systematic approach to mapping brain function:

- **Standardized procedure**: Consistent methodology across laboratories
- **Precise localization**: Combine electrophysiology with histological verification
- **Rich metadata**: Comprehensive tracking of insertion parameters and quality
- **Cross-referenced data**: Links behavioral, neural, and anatomical information
- **Quality control**: Multiple levels of verification for anatomical assignments
- **Flexible access**: Multiple APIs for different analysis needs

The probe insertion system enables large-scale, quantitative neuroscience by providing standardized, high-quality neural recordings with precise anatomical localization across the entire mouse brain.
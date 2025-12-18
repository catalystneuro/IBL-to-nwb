# How to Fetch Histology Data in IBL ONE API

## Overview

The IBL SpikeSortingLoader determines histology quality through a hierarchical system that prioritizes local ALF files over database trajectory data. The `histology` attribute indicates the reliability of channel brain location data.

## Histology Quality Levels (Best to Worst)

### 1. **'alf'** - Highest Quality ✅
- **Source**: Pre-computed brain locations in local ALF files
- **Location**: `alf/{probe_name}/` collections
- **Key Files**:
  - `channels.brainLocationIds_ccf_2017.npy`
  - `channels.atlas_id.npy`
  - `channels.x.npy`, `channels.y.npy`, `channels.z.npy`
  - `channels.acronym.npy` (optional)
  - `electrodeSites.*` files (alternative)
- **Quality**: Final, validated channel locations ready for analysis

### 2. **'resolved'** - High Quality ✅
- **Source**: Alyx database with finalized alignments
- **API Check**: `insertion['json']['extended_qc']['alignment_resolved'] = True`
- **Data Sources**:
  - `insertion['json']['xyz_picks']` - Raw tracing coordinates
  - `trajectory['json'][align_key]` - Validated alignment data
- **Quality**: Manually reviewed and approved by experts

### 3. **'aligned'** - Medium Quality ⚠️
- **Source**: Alyx database with pending alignments
- **API Check**: `insertion['json']['extended_qc']['alignment_count'] > 0`
- **Data Sources**: Same as 'resolved' but not yet validated
- **Quality**: Aligned but awaiting review - potentially inaccurate

### 4. **'traced'** - Basic Quality ⚠️
- **Source**: Raw histology tracing from microscopy
- **API Check**: `insertion['json']['extended_qc']['tracing_exists'] = True`
- **Data Sources**: Only `insertion['json']['xyz_picks']` coordinates
- **Quality**: Basic trace, depths may not match ephys data

### 5. **''** (Empty) - No Data ❌
- **Condition**: No histology tracing exists in database
- **Warning**: "Histology tracing for {probe} does not exist"
- **Quality**: No brain location data available

## Code Implementation

### Loading Process Location
**File**: `/home/heberto/miniconda3/envs/work/lib/python3.12/site-packages/brainbox/io/one.py`

### Primary Check: ALF Files (Lines 1033-1041)
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

### Database Trajectory Check (Lines 305-362)
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

## REST API Endpoints Used

### Insertion Data
```
GET /insertions?session={eid}&name={probe}
```
**Key Fields**:
- `json.xyz_picks` - Raw tracing coordinates
- `json.extended_qc.tracing_exists` - Boolean
- `json.extended_qc.alignment_resolved` - Boolean
- `json.extended_qc.alignment_count` - Integer
- `json.extended_qc.alignment_stored` - Alignment key

### Trajectory Data
```
GET /trajectories?session={eid}&probe={probe}&provenance=Ephys%20aligned%20histology%20track
```
**Key Fields**:
- `json[alignment_key][0]` - Feature data
- `json[alignment_key][1]` - Track data

## Required Additional Files

### Local Coordinates
- **File**: `channels.localCoordinates.npy`
- **Purpose**: Maps channel depths for trajectory interpolation
- **Location**: `alf/{probe_name}/` collection

## Usage Example

```python
from brainbox.io.one import SpikeSortingLoader

sorting_loader = SpikeSortingLoader(eid=eid, one=one, pname=probe_name, atlas=atlas)
spikes, clusters, channels = sorting_loader.load_spike_sorting()

# Check histology quality
print(f"Histology source: {sorting_loader.histology}")
# Possible values: 'alf', 'resolved', 'aligned', 'traced', ''

# Access channel brain locations (if available)
if sorting_loader.histology:
    print(f"Brain regions: {channels.acronym}")
    print(f"Atlas coordinates: {channels.x}, {channels.y}, {channels.z}")
else:
    print("No histology data available for this probe")
```

## Troubleshooting

### "Histology tracing does not exist"
- **Cause**: No tracing data in Alyx database
- **Solution**: Use probe without brain location data or find alternative session
- **Result**: `histology = ''` and no brain region assignments

### File Size Mismatch Warnings
- **Cause**: Database metadata out of sync with S3 files
- **Solution**: Use `cache_rest=None` in ONE constructor
- **Impact**: Does not affect histology loading, only file validation

## Files Created by This Documentation
- **Location**: `/home/heberto/development/IBL-to-nwb/build/how_to_fetch_histology.md`
- **Purpose**: Reference for understanding IBL histology data sources and quality levels
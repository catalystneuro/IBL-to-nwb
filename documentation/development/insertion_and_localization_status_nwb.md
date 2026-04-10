# IBL Probe Insertion and Localization Status in NWB Conversion

## Overview

This document tracks the current status of probe insertion and localization information in the IBL-to-NWB conversion pipeline, identifying what is included, what is missing, and what needs to be implemented.

## Current Implementation Status

### ✅ **INCLUDED** - Currently Converted to NWB

| Information Type | NWB Location | Source Interface | Implementation Status |
|------------------|--------------|------------------|----------------------|
| **Probe Device Info** | `nwbfile.devices['NeuropixelsProbe']` | `IblStreamingApInterface` | ✅ Complete |
| **Electrode Groups** | `nwbfile.electrode_groups['NeuropixelsShank']` | `IblStreamingApInterface` | ✅ Complete |
| **Channel Coordinates** | `nwbfile.electrodes` table | `IblStreamingApInterface` | ✅ Complete |
| **Brain Region Mappings** | `nwbfile.electrodes` table | `IblStreamingApInterface` | ✅ Complete |
| **Probe-Session Mapping** | Via PID-EID mapping in code | `bwm_to_nwb.py` | ✅ Complete |

### ❌ **MISSING** - Not Currently Converted

| Information Type | Source API | Current Status | Priority |
|------------------|------------|----------------|----------|
| **Stereotactic Angles** | `trajectories.theta`, `trajectories.phi` | ❌ Not included | 🔴 High |
| **Insertion Coordinates** | `trajectories.x`, `trajectories.y`, `trajectories.z` | ❌ Not included | 🔴 High |
| **Probe Insertion ID (PID)** | `insertions.id` | ❌ Not included | 🔴 High |
| **Trajectory Provenance** | `trajectories.provenance` | ❌ Not included | 🟡 Medium |
| **Insertion Depth** | `trajectories.depth` | ❌ Not included | 🟡 Medium |
| **Probe Roll Angle** | `trajectories.roll` | ❌ Not included | 🟡 Medium |
| **Target Brain Region** | `insertions.json.target` | ❌ Not included | 🟡 Medium |
| **Histology QC Status** | `insertions.json.extended_qc` | ❌ Not included | 🟡 Medium |
| **Alignment Status** | `insertions.json.extended_qc.alignment_resolved` | ❌ Not included | 🟡 Medium |

## Detailed Analysis

### What Is Currently Included

#### 1. **Device and Hardware Information**
```python
# From IblStreamingApInterface.get_metadata()
metadata["Ecephys"].update(
    Device=[dict(
        name="NeuropixelsProbe",  # or "NeuropixelsProbe00", "NeuropixelsProbe01"
        description="A Neuropixels probe.",
        manufacturer="IMEC"
    )]
)
```
**Status**: ✅ **Well implemented** - Basic device information is included

#### 2. **Electrode Groups and Locations**
```python
# Brain region information included in electrode table
self.recording_extractor.set_property(key="brain_area", values=list(channels["acronym"]))
self.recording_extractor.set_property(key="beryl_location", values=...)
self.recording_extractor.set_property(key="cosmos_location", values=...)
```
**Status**: ✅ **Well implemented** - Multiple brain atlas mappings included

#### 3. **Channel Spatial Coordinates**
```python
# Both CCF and IBL coordinate systems included
self.recording_extractor.set_property(key="x", values=ccf_coords[:, 0])  # CCF space
self.recording_extractor.set_property(key="ibl_x", values=ibl_coords[:, 0])  # IBL space
```
**Status**: ✅ **Excellent implementation** - Dual coordinate systems preserved

### What Is Missing

#### 1. **Stereotactic Insertion Angles** ❌
**Current Problem**: No stereotactic angles (theta, phi, roll) are stored in NWB files

**Impact**:
- Cannot reconstruct probe insertion trajectory
- Cannot validate histological alignment
- Missing critical metadata for reproducibility

**Proposed Solution**:
```python
# Add to Device or create custom extension
trajectories = one.alyx.rest('trajectories', 'list', probe_insertion=pid,
                           provenance='Ephys aligned histology track')
if trajectories:
    theta = trajectories[0]['theta']
    phi = trajectories[0]['phi']
    roll = trajectories[0].get('roll', 0)
```

#### 2. **Probe Insertion ID (PID)** ❌
**Current Problem**: The unique probe insertion identifier is not stored

**Impact**:
- Cannot cross-reference with IBL database
- Difficult to link NWB files to original insertions
- Loss of data provenance

**Current Workaround**: PID is used internally in `bwm_to_nwb.py` but not stored:
```python
# Current: PID used but not saved
insertions = one.alyx.rest('insertions', 'list', session=eid)
pname_pid_map = {ins['name']: ins['id'] for ins in insertions}  # Used but not stored
```

#### 3. **Insertion Entry Point** ❌
**Current Problem**: Entry coordinates (x, y, z) not stored

**Impact**:
- Cannot reconstruct full probe trajectory
- Missing spatial context for insertion

#### 4. **Histology Quality Control Information** ❌
**Current Problem**: No QC metadata about anatomical localization quality

**Impact**:
- Users cannot assess reliability of brain region assignments
- No warning about low-quality localizations

## Implementation Gaps Analysis

### Gap 1: No Insertion-Level Metadata Storage

**Current State**: Only channel-level data is stored
**Missing**: Probe-level insertion metadata

**Files Affected**:
- `IblStreamingApInterface` - handles electrodes but not insertion metadata
- No dedicated insertion metadata interface exists

### Gap 2: Limited Trajectory Information

**Current State**: Only final channel locations stored
**Missing**: Full trajectory path and insertion parameters

### Gap 3: No Data Provenance for Localization

**Current State**: Brain regions included but no quality indication
**Missing**: Histology provenance levels (`ssl.histology` information)

## Recommended Implementation Plan

### Phase 1: High Priority (Critical Missing Data)

#### 1.1 Add Probe Insertion Metadata Interface
```python
class ProbeInsertionInterface(BaseDataInterface):
    def __init__(self, one: ONE, pid: str):
        self.pid = pid
        self.insertion_data = one.alyx.rest('insertions', 'read', id=pid)
        self.trajectories = one.alyx.rest('trajectories', 'list', probe_insertion=pid)

    def add_to_nwbfile(self, nwbfile: NWBFile):
        # Add insertion metadata to device or custom extension
        pass
```

#### 1.2 Add Stereotactic Angles to Device Metadata
**Location**: Extend `IblStreamingApInterface.get_metadata()`
**Implementation**: Add trajectory angles to Device description or custom fields

#### 1.3 Store Probe Insertion ID (PID)
**Location**: Device metadata or custom extension field
**Implementation**: Include PID for cross-referencing with IBL database

### Phase 2: Medium Priority (Enhanced Metadata)

#### 2.1 Add Trajectory Provenance Information
**Implementation**: Store histology quality level in electrode table metadata

#### 2.2 Add Insertion Target Information
**Implementation**: Store planned target region from insertion metadata

#### 2.3 Add Quality Control Status
**Implementation**: Store alignment status and QC flags

### Phase 3: Advanced Features (Optional)

#### 3.1 Full Trajectory Path Storage
**Implementation**: Store complete 3D trajectory as TimeSeries or custom object

#### 3.2 Multiple Trajectory Versions
**Implementation**: Store planned, micro-manipulator, and histology-aligned trajectories

## Technical Implementation Recommendations

### Option 1: Extend Existing Device Metadata
```python
# Add to IblStreamingApInterface
device_metadata = {
    "name": device_name,
    "description": "A Neuropixels probe.",
    "manufacturer": "IMEC",
    "probe_insertion_id": pid,
    "stereotactic_theta": theta,
    "stereotactic_phi": phi,
    "stereotactic_roll": roll,
    "entry_point_x": entry_x,
    "entry_point_y": entry_y,
    "entry_point_z": entry_z,
    "histology_provenance": ssl.histology
}
```

### Option 2: Create Custom NWB Extension
```python
# Use ndx-ibl extension to store insertion metadata
from ndx_ibl import ProbeInsertion

probe_insertion = ProbeInsertion(
    name="probe_insertion_metadata",
    insertion_id=pid,
    stereotactic_angles=(theta, phi, roll),
    entry_coordinates=(x, y, z),
    target_region=target,
    histology_quality=ssl.histology
)
nwbfile.add_lab_meta_data(probe_insertion)
```

### Option 3: Enhance Electrode Table
```python
# Add insertion-level columns to electrode table
nwbfile.electrodes.add_column(
    name='probe_insertion_id',
    description='Unique probe insertion identifier',
    data=[pid] * n_channels
)
nwbfile.electrodes.add_column(
    name='histology_provenance',
    description='Quality of anatomical localization',
    data=[ssl.histology] * n_channels
)
```

## Current Code Locations for Implementation

### Files to Modify:
1. **`IblStreamingApInterface`** (`_ibl_streaming_interface.py`) - Add insertion metadata
2. **`bwm_to_nwb.py`** - Pass insertion information to interfaces
3. **`ecephys.yml`** - Add metadata schemas for new fields

### Integration Points:
```python
# In bwm_to_nwb.py - already has insertion data
insertions = one.alyx.rest('insertions', 'list', session=eid)
pname_pid_map = {ins['name']: ins['id'] for ins in insertions}

# Pass to streaming interface
IblStreamingApInterface(
    session=eid,
    stream_name=stream_name,
    insertion_metadata=insertions  # ADD THIS
)
```

## Summary

**Current Status**: **60% Complete**
- ✅ Hardware and electrode information: Excellent
- ✅ Channel locations and brain regions: Excellent
- ❌ Probe insertion metadata: Missing
- ❌ Stereotactic parameters: Missing
- ❌ Data provenance: Missing

**Priority Actions**:
1. 🔴 **Critical**: Add stereotactic angles (theta, phi, roll)
2. 🔴 **Critical**: Store probe insertion ID (PID)
3. 🔴 **Critical**: Add insertion entry coordinates
4. 🟡 **Important**: Include histology provenance quality information
5. 🟡 **Important**: Add target region and QC status metadata

**Impact**: Adding this missing information would significantly improve:
- **Reproducibility**: Full insertion parameters stored
- **Data provenance**: Clear links to IBL database
- **Scientific value**: Trajectory information for analysis
- **Quality assessment**: Users can evaluate localization reliability

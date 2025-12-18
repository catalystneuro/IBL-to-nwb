# How samples2times Works in IBL SpikeSortingLoader

## Overview

The `samples2times` method in SpikeSortingLoader converts ephys sample indices to session main clock timestamps (seconds). This synchronization is critical for aligning neural data across different recording systems and behavioral events.

## Core Functionality

### Method Location
**File**: `/home/heberto/miniconda3/envs/work/lib/python3.12/site-packages/brainbox/io/one.py:1207-1216`

### Method Signature
```python
def samples2times(self, values, direction='forward'):
    """
    Converts ephys sample values to session main clock seconds
    :param values: numpy array of times in seconds or samples to resync
    :param direction: 'forward' (samples probe time to seconds main time) or 'reverse'
     (seconds main time to samples probe time)
    :return: synchronized timestamps
    """
```

### Implementation
```python
def samples2times(self, values, direction='forward'):
    self._get_probe_info()  # Ensures sync data is loaded
    return self._sync[direction](values)  # Uses interpolation functions
```

## Synchronization System Architecture

### 1. **Data Initialization** (`_get_probe_info` method)
**Location**: `/home/heberto/miniconda3/envs/work/lib/python3.12/site-packages/brainbox/io/one.py:1178-1198`

#### Required Files Loading:
```python
# Main synchronization file (probe time <-> main clock)
timestamps = one.load_dataset(eid,
    dataset='_spikeglx_*.timestamps.npy',
    collection=f'raw_ephys_data/{probe_name}')

# Additional sync data (downloaded but not used directly)
sync_data = one.load_dataset(eid,
    dataset='_spikeglx_*.sync.npy',
    collection=f'raw_ephys_data/{probe_name}')

# Metadata for sampling rate
ap_meta = spikeglx.read_meta_data(one.load_dataset(eid,
    dataset='_spikeglx_*.ap.meta',
    collection=f'raw_ephys_data/{probe_name}'))
```

### 2. **Synchronization Object Creation**
```python
self._sync = {
    'timestamps': timestamps,                    # Raw sync data [N x 2]
    'forward': interp1d(timestamps[:, 0],       # Probe samples -> Main time
                       timestamps[:, 1],
                       fill_value='extrapolate'),
    'reverse': interp1d(timestamps[:, 1],       # Main time -> Probe samples
                       timestamps[:, 0],
                       fill_value='extrapolate'),
    'ap_meta': ap_meta,                         # SpikeGLX metadata
    'fs': sampling_rate,                        # Sampling frequency (Hz)
}
```

## Data File Structure

### **Timestamps File Format**
**File**: `_spikeglx_*.timestamps.npy`
**Shape**: `[N_sync_pulses, 2]`
**Content**:
- **Column 0**: Probe sample indices (local probe clock)
- **Column 1**: Main session timestamps (seconds, session master clock)

**Example Structure**:
```python
timestamps = np.array([
    [0,      0.0],      # Probe sample 0 = session time 0.0s
    [30000,  1.0],      # Probe sample 30000 = session time 1.0s
    [60000,  2.0],      # Probe sample 60000 = session time 2.0s
    # ... continues for entire session
])
```

### **Metadata Files**
**File**: `_spikeglx_*.ap.meta`
**Key Fields**:
- `imSampRate`: Sampling rate for IMEC probes (typically 30kHz)
- `niSampRate`: Sampling rate for NI-DAQ systems
- `typeThis`: Probe type identifier ('imec' vs other)

**Sampling Rate Extraction**:
```python
def _get_fs_from_meta(meta_data):
    if meta_data.get("typeThis") == "imec":
        return meta_data.get("imSampRate")  # Usually 30000 Hz
    else:
        return meta_data.get("niSampRate")
```

### **Sync Files**
**File**: `_spikeglx_*.sync.npy`
**Purpose**: Additional synchronization pulses (downloaded but not used directly by samples2times)

## Interpolation System

### **Forward Direction** (Probe Samples → Session Time)
```python
# Convert probe sample indices to session timestamps
forward_func = interp1d(timestamps[:, 0],     # Input: probe samples
                       timestamps[:, 1],      # Output: session time
                       fill_value='extrapolate')

# Usage: probe_samples -> session_seconds
session_times = forward_func(probe_sample_indices)
```

### **Reverse Direction** (Session Time → Probe Samples)
```python
# Convert session timestamps to probe sample indices
reverse_func = interp1d(timestamps[:, 1],     # Input: session time
                       timestamps[:, 0],      # Output: probe samples
                       fill_value='extrapolate')

# Usage: session_seconds -> probe_samples
probe_samples = reverse_func(session_timestamps)
```

### **Extrapolation Handling**
- **`fill_value='extrapolate'`**: Allows conversion beyond recorded sync range
- **Linear extrapolation**: Maintains constant drift correction outside sync bounds
- **Fallback sampling rate**: 30kHz default if metadata unavailable

## Usage Examples

### **Basic Forward Conversion**
```python
# Convert spike sample indices to session time
spike_samples = np.array([0, 30000, 60000, 90000])
spike_times = sorting_loader.samples2times(spike_samples, direction='forward')
# Result: [0.0, 1.0, 2.0, 3.0] seconds (assuming perfect 30kHz clock)
```

### **Reverse Conversion**
```python
# Convert behavioral event times to probe samples
event_times = np.array([1.5, 2.7, 4.2])  # seconds
event_samples = sorting_loader.samples2times(event_times, direction='reverse')
# Result: [45000, 81000, 126000] approximate sample indices
```

### **Real-world Application** (from your codebase)
```python
# Create aligned timestamps for entire recording
aligned_timestamps = spike_sorting_loader.samples2times(
    np.arange(0, sglx_streamer.ns),  # All sample indices [0, 1, 2, ..., total_samples]
    direction="forward",              # Convert to session time
    band=band                        # AP or LF band
)
```

## Clock Drift Correction

### **Why Synchronization is Needed**
1. **Independent Clocks**: Probe sampling clock vs session master clock
2. **Clock Drift**: Sampling rates drift over time due to temperature/hardware
3. **Multi-probe Sessions**: Each probe has its own clock
4. **Behavioral Alignment**: Neural events must align with behavioral timestamps

### **Sync Pulse System**
- **Regular Pulses**: Sync signals sent every ~1 second during recording
- **Drift Tracking**: Timestamps file tracks cumulative drift
- **Linear Interpolation**: Smooth correction between sync points
- **Extrapolation**: Handle data outside sync range

### **Drift Correction Formula**
```python
# Simplified version of what interp1d does internally:
def linear_sync(probe_samples, timestamps):
    # Find nearest sync points
    sync_samples = timestamps[:, 0]  # Probe sample indices of sync pulses
    sync_times = timestamps[:, 1]    # Corresponding session times

    # Linear interpolation between sync points
    session_times = np.interp(probe_samples, sync_samples, sync_times)
    return session_times
```

## Error Handling and Fallbacks

### **Missing Metadata**
```python
try:
    ap_meta = spikeglx.read_meta_data(meta_file)
    fs = spikeglx._get_fs_from_meta(ap_meta)
except ALFObjectNotFound:
    ap_meta = None
    fs = 30_000  # Default 30kHz sampling rate
```

### **Missing Sync Data**
- **Consequence**: `_sync` remains `None`, method will fail
- **Prevention**: `_get_probe_info()` called before every conversion
- **Fallback**: Some sessions may lack proper sync data

## Performance Characteristics

### **Interpolation Objects**
- **Creation**: One-time setup cost when first called
- **Interpolation**: Fast scipy linear interpolation
- **Memory**: Stores full timestamps array and interpolation functions
- **Caching**: Sync data cached in `_sync` dictionary

### **Typical Performance**
- **Setup Time**: ~100-500ms (file loading + interpolation setup)
- **Conversion Time**: ~1-10ms for typical spike arrays
- **Memory Usage**: ~1-10MB per probe (depends on session length)

## Integration with IBL Pipeline

### **File Collection Structure**
```
session/
├── raw_ephys_data/
│   ├── probe00/
│   │   ├── _spikeglx_ephysData_g0_t0.imec0.ap.meta
│   │   ├── _spikeglx_ephysData_g0_t0.imec0.timestamps.npy  ← Key file
│   │   ├── _spikeglx_ephysData_g0_t0.imec0.sync.npy       ← Additional sync
│   │   └── ...
│   └── probe01/
│       └── ...
└── alf/
    └── ...
```

### **Dependencies**
- **scipy.interpolate.interp1d**: Core interpolation functionality
- **spikeglx library**: Metadata parsing
- **ONE API**: File loading and session management

## Troubleshooting

### **"ALFObjectNotFound" for sync files**
- **Cause**: Session missing sync/metadata files
- **Impact**: Uses default 30kHz sampling rate
- **Solution**: Check if raw ephys data properly uploaded

### **Extrapolation Warnings**
- **Cause**: Converting samples outside recorded sync range
- **Impact**: May have reduced accuracy at session edges
- **Solution**: Usually safe due to linear extrapolation

### **Memory Issues with Large Sessions**
- **Cause**: Very long sessions with many sync pulses
- **Solution**: Interpolation objects handle this efficiently
- **Monitoring**: Check `_sync['timestamps'].shape`

## Related Methods

### **timesprobe2times** (Similar but Different)
```python
def timesprobe2times(self, values, direction='forward'):
    # Multiplies by sampling rate before/after sync conversion
    if direction == 'forward':
        return self._sync['forward'](values * self._sync['fs'])
    elif direction == 'reverse':
        return self._sync['reverse'](values) / self._sync['fs']
```

**Key Difference**:
- `samples2times`: Direct sample index ↔ session time
- `timesprobe2times`: Probe time (seconds) ↔ session time (seconds)

## Files Created by This Documentation
- **Location**: `/home/heberto/development/IBL-to-nwb/build/how_samples2times_works.md`
- **Purpose**: Complete reference for understanding IBL time synchronization system
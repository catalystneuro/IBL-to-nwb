# NIDQ Availability and Raw Timing Sources in IBL Sessions

## Executive Summary

NIDQ (National Instruments DAQ) behavioral sync signals are **optional** in IBL NWB conversions. Sessions without NIDQ files fall into two categories:

1. **Neuropixels 3A systems (2019-2020)**: Sync signals recorded on probe analog channels, not on dedicated NIDQ board
2. **Missing uploads**: Had NIDQ hardware but raw files were not uploaded to database

Even without raw NIDQ data, **all timing information is available** through preprocessed sync files (`_spikeglx_sync.*.npy`) that IBL's pipeline extracts from either NIDQ or probe channels.

---

## Data Availability Patterns

### Overall Statistics

From the Brain-Wide Map dataset analysis (session_diagnosis_report_20251105_213640.csv):

- **Sessions without NIDQ**: Primarily early sessions (2019-2020)
- **Sessions with NIDQ**: Primarily later sessions (2020-2021 onwards)
- **All sessions have sync data**: Either from NIDQ or probe channels

### Temporal Distribution

**Early sessions (2019 - mid-2020)**:
- Used Neuropixels 3A probes
- Sync signals recorded on probe analog channels (channels 2, 3, 4, 12-15)
- No dedicated NIDQ board
- Example: CSHL045, CSHL047, early NYU sessions

**Later sessions (mid-2020 onwards)**:
- Transitioned to Neuropixels 3B probes
- Dedicated NIDQ board for behavioral sync
- Sync signals on separate acquisition system
- Example: Most angelakilab, churchlandlab sessions from late 2020+

### Laboratory-Specific Patterns

Different labs transitioned at different times based on hardware availability and experimental protocols.

---

## Hardware Architecture

### Neuropixels 3A System (Early IBL)

```
┌─────────────────────────────────────────────────────────────┐
│  Neuropixels 3A Probe                                       │
│                                                              │
│  Neural Channels: 0-383 (AP band: spikes, LF band: LFP)    │
│  Sync Channels (analog): 2, 3, 4, 12, 13, 14, 15           │
│    - Channel 2:  left_camera TTL                            │
│    - Channel 3:  right_camera TTL                           │
│    - Channel 4:  body_camera TTL                            │
│    - Channel 12: frame2ttl (visual stimulus photodiode)     │
│    - Channel 13: rotary_encoder_0 (wheel quadrature A)      │
│    - Channel 14: rotary_encoder_1 (wheel quadrature B)      │
│    - Channel 15: audio (auditory stimulus)                  │
│                                                              │
│  Note: Multi-probe sessions use Frame2TTL or camera as      │
│        common reference for inter-probe synchronization     │
└─────────────────────────────────────────────────────────────┘
```

**File outputs**:
- `_spikeglx_*.ap.cbin`: Neural data + sync channels
- `_spikeglx_sync.times.npy`: Sync event timestamps (preprocessed)
- `_spikeglx_sync.channels.npy`: Sync channel IDs
- `_spikeglx_sync.polarities.npy`: Sync event directions (rising/falling)
- `_spikeglx_*.timestamps.npy`: Probe-to-session clock mapping

### Neuropixels 3B System (Later IBL)

```
┌──────────────────────────────┐   ┌────────────────────────────┐
│  Neuropixels 3B Probe(s)     │   │  NIDQ Acquisition Board    │
│                              │   │  (National Instruments)    │
│  Neural Channels: 0-383      │   │                            │
│  ImecSync Channel: 3         │───│  Digital Channels (P0.0-7):│
│  (1 Hz square wave)          │   │    0: left_camera          │
│                              │   │    1: right_camera         │
│  Provides neural data        │   │    2: body_camera          │
│  and probe timing            │   │    3: imec_sync            │
│                              │   │    4: frame2ttl            │
│                              │   │    5: rotary_encoder_0     │
│                              │   │    6: rotary_encoder_1     │
│                              │   │    7: audio                │
│                              │   │                            │
│                              │   │  Analog Channels (AI0-2):  │
│                              │   │    0: Bpod                 │
│                              │   │    1: Laser power          │
│                              │   │    2: Laser TTL            │
└──────────────────────────────┘   └────────────────────────────┘
         ↓                                      ↓
         └──────────────────┬───────────────────┘
                            ↓
                 Synchronized via ImecSync
```

**File outputs**:

Probe files:
- `_spikeglx_*.ap.cbin`: Neural data
- `_spikeglx_*.timestamps.npy`: Probe-to-session clock mapping

NIDQ files:
- `_spikeglx_*.nidq.cbin`: Raw behavioral sync signals (digital + analog)
- `_spikeglx_*.nidq.meta`: Acquisition metadata
- `_spikeglx_*.nidq.ch`: Channel information
- `_spikeglx_*.nidq.wiring.json`: Device-to-channel mapping (optional)

Preprocessed sync files (extracted from NIDQ):
- `_spikeglx_sync.times.npy`: Sync event timestamps
- `_spikeglx_sync.channels.npy`: Sync channel IDs
- `_spikeglx_sync.polarities.npy`: Sync event directions

---

## Raw Timing Sources by Session Type

### When NIDQ is Available (3B systems)

**Primary source**: NIDQ raw files (`*.nidq.cbin`)

**Processing pipeline**:
1. IBL pipeline extracts sync events from raw NIDQ
2. Creates preprocessed `_spikeglx_sync.*.npy` files
3. Uses NIDQ master clock for multi-probe synchronization
4. Camera timestamps extracted from NIDQ channel 0-2
5. Wheel timestamps from NIDQ channels 5-6
6. Visual stimulus timing from NIDQ channel 4 (Frame2TTL)

**NWB conversion**:
- `IblNIDQInterface`: Adds raw NIDQ continuous data (optional, for verification)
- `IblSortingInterface`: Uses preprocessed sync for spike alignment
- Camera interfaces: Use preprocessed sync for video frame timestamps
- Wheel interface: Uses preprocessed sync for movement tracking

### When NIDQ is NOT Available (3A systems)

**Primary source**: Probe analog channels (recorded in `*.ap.cbin`)

**Processing pipeline**:
1. IBL pipeline extracts sync events from probe analog channels
2. Creates preprocessed `_spikeglx_sync.*.npy` files (same format as 3B)
3. For multi-probe: Uses Frame2TTL or camera as common reference
4. Camera timestamps extracted from probe channels 2-4
5. Wheel timestamps from probe channels 13-14
6. Visual stimulus timing from probe channel 12 (Frame2TTL)

**NWB conversion**:
- `IblNIDQInterface`: Skipped (not available)
- `IblSortingInterface`: Uses preprocessed sync (same as 3B sessions)
- Camera interfaces: Use preprocessed sync (same as 3B sessions)
- Wheel interface: Uses preprocessed sync (same as 3B sessions)

**Critical insight**: The preprocessed `_spikeglx_sync.*.npy` files provide identical timing information regardless of whether source was NIDQ or probe channels. This abstraction enables uniform processing across hardware versions.

### Fallback Sources (Rare)

If preprocessed sync files are unavailable (data quality issues, upload failures):

1. **Camera timestamps from camlog files**:
   - `_ibl_*.camlog.jsonable`: Camera software timestamps
   - Less precise than hardware TTLs
   - Used for frame timing when hardware sync unavailable

2. **Bpod timestamps**:
   - `_iblrig_*.bpodlog.jsonable`: Behavioral task events
   - Software timestamps from Bpod controller
   - Used for trial structure and task events

3. **Wheel data from raw encoder**:
   - `_ibl_wheel.position.npy`: Wheel position samples
   - Can derive timestamps from Bpod or camera timing

---

## Sync File Structure

### Preprocessed Sync Files (Universal Format)

These files exist for **all** IBL sessions regardless of hardware:

#### `_spikeglx_sync.times.{probe_name}.npy`
- **Shape**: `(N_events,)`
- **Dtype**: `float64`
- **Content**: Timestamps in session clock (seconds from session start)
- **Example**: `[0.033, 0.066, 0.100, ...]` (camera frame times at 30 Hz)

#### `_spikeglx_sync.channels.{probe_name}.npy`
- **Shape**: `(N_events,)`
- **Dtype**: `int16`
- **Content**: Channel ID for each event
- **Example**: `[2, 2, 3, 3, 4, 4, ...]` (camera channels)
- **3A mapping**: 2=left_camera, 3=right_camera, 4=body_camera, 12=frame2ttl
- **3B mapping**: 0=left_camera, 1=right_camera, 2=body_camera, 4=frame2ttl

#### `_spikeglx_sync.polarities.{probe_name}.npy`
- **Shape**: `(N_events,)`
- **Dtype**: `int8`
- **Content**: Event direction (1=rising edge, -1=falling edge)
- **Example**: `[1, -1, 1, -1, ...]` (TTL pulses)

### Example Sync Data

```python
# Session: CSHL045 2020-02-25 (3A system, no NIDQ)
sync_times = np.array([0.033, 0.066, 0.100, 0.133, ...])  # 30 Hz camera
sync_channels = np.array([2, 2, 3, 3, 4, 4, ...])          # left, right, body cameras
sync_polarities = np.array([1, -1, 1, -1, 1, -1, ...])     # rising/falling edges

# Extract left camera frame times (channel 2, rising edges)
left_camera_mask = (sync_channels == 2) & (sync_polarities == 1)
left_camera_times = sync_times[left_camera_mask]
# Result: [0.033, 0.100, ...] (every other event)
```

---

## Multi-Probe Synchronization

### 3B System (NIDQ as Master)

```
Session Master Clock (NIDQ)
        ↓
        ├─→ Probe00 (synchronized via ImecSync channel)
        │   ├─→ _spikeglx_*.timestamps.npy (probe00 samples → session time)
        │   └─→ Neural spikes aligned to session clock
        │
        └─→ Probe01 (synchronized via ImecSync channel)
            ├─→ _spikeglx_*.timestamps.npy (probe01 samples → session time)
            └─→ Neural spikes aligned to session clock
```

**Synchronization mechanism**:
- NIDQ sends 1 Hz square wave to all probes via ImecSync channel
- Each probe records this signal on dedicated sync channel (channel 3)
- `_spikeglx_*.timestamps.npy` maps probe samples to NIDQ master clock
- See [how_samples2times_works.md](how_samples2times_works.md) for details

### 3A System (Frame2TTL or Camera as Reference)

```
Common Reference (Frame2TTL or Camera TTL)
        ↓
        ├─→ Probe00 (records Frame2TTL on channel 12)
        │   ├─→ Frame2TTL events → reference time
        │   ├─→ One probe chosen as "master"
        │   └─→ _spikeglx_*.timestamps.npy (probe00 samples → reference time)
        │
        └─→ Probe01 (records Frame2TTL on channel 12)
            ├─→ Frame2TTL events → reference time
            ├─→ Aligned to master probe via common events
            └─→ _spikeglx_*.timestamps.npy (probe01 samples → reference time)
```

**Synchronization mechanism**:
- Both probes record same Frame2TTL or camera signal
- IBL pipeline (`sync_probes.version3A()`) uses common events to align clocks
- One probe designated as master, other probe(s) aligned to it
- Handles clock drift via linear interpolation between common events

---

## IBL Pipeline Processing

### Relevant Code Locations

From `ibllib/ephys/sync_probes.py`:

```python
def version3B(ses_path, **kwargs):
    """
    Synchronize multiple 3B probes using NIDQ as master clock.

    NIDQ provides:
    - Master session clock
    - ImecSync 1 Hz square wave to all probes
    - Behavioral sync signals (cameras, wheel, stimuli)
    """
    # Extract sync from NIDQ
    nidq_sync = extract_sync_nidq(ses_path)

    # For each probe: map probe samples to NIDQ time
    for probe in probes:
        probe_sync = extract_sync_probe(probe_path)
        # Create interpolation: probe_samples → nidq_time
        sync_mapping = sync_probe_front_times(probe_sync, nidq_sync)
        # Save: _spikeglx_*.timestamps.npy

def version3A(ses_path, **kwargs):
    """
    Synchronize multiple 3A probes using Frame2TTL or camera as reference.

    Probes record sync on analog channels:
    - No NIDQ
    - Common reference (Frame2TTL or camera) on all probes
    - One probe chosen as master
    """
    # Extract sync from probe channels
    for probe in probes:
        probe_sync = extract_sync_probe_3a(probe_path)

    # Identify common reference events (Frame2TTL or camera)
    reference_events = find_common_events(probe_syncs)

    # Choose master probe, align others to it
    master_probe = choose_master_probe(probes)
    for probe in other_probes:
        # Create interpolation using common events
        sync_mapping = sync_probe_front_times(probe_sync, master_sync)
        # Save: _spikeglx_*.timestamps.npy
```

### Camera Timestamp Extraction

From `ibllib/io/extractors/camera.py`:

```python
def extract_camera_sync(sync, chmap):
    """
    Extract camera timestamps from preprocessed sync files.

    Works identically for 3A and 3B systems because both produce
    the same preprocessed sync file format.

    Parameters
    ----------
    sync : dict
        Loaded from _spikeglx_sync.*.npy files
        Keys: 'times', 'channels', 'polarities'
    chmap : dict
        Channel mapping (e.g., {'left_camera': 2, 'right_camera': 3})
    """
    times = {}
    for k in filter(lambda x: x.endswith('_camera'), chmap):
        label, _ = k.rsplit('_', 1)
        # Extract rising edges (frame acquisition start)
        times[label] = get_sync_fronts(sync, chmap[k]).times[::2]
    return times
    # Result: {'left': array([...]), 'right': array([...]), 'body': array([...])}
```

---

## NWB Conversion Behavior

### With NIDQ Available

```python
# conversion/raw.py

# Core data interfaces (always added)
data_interfaces.append(IblSortingInterface(...))  # Uses preprocessed sync
data_interfaces.append(WheelInterface(...))       # Uses preprocessed sync
data_interfaces.append(RawVideoInterface(...))    # Uses preprocessed sync

# NIDQ interface (optional, for raw verification)
if IblNIDQInterface.check_availability(one, eid)["available"]:
    nidq_interface = IblNIDQInterface(...)
    data_interfaces.append(nidq_interface)
    logger.info("✓ NIDQ interface added (behavioral sync signals)")
```

**Result**:
- NWB file contains raw NIDQ continuous data (8 digital + 3 analog channels)
- Users can verify timing by comparing NWB events to raw NIDQ signals
- Provides full fidelity behavioral sync for advanced analyses

### Without NIDQ Available

```python
# conversion/raw.py

# Core data interfaces (always added)
data_interfaces.append(IblSortingInterface(...))  # Uses preprocessed sync
data_interfaces.append(WheelInterface(...))       # Uses preprocessed sync
data_interfaces.append(RawVideoInterface(...))    # Uses preprocessed sync

# NIDQ interface (skipped)
if IblNIDQInterface.check_availability(one, eid)["available"]:  # False
    # Not executed
    pass
else:
    logger.warning("NIDQ data not available for session {eid} - skipping NIDQ interface")
```

**Result**:
- NWB file contains all timing information from preprocessed sync
- Neural spikes, video frames, wheel movement all properly aligned
- Missing: Raw continuous NIDQ traces (but these are optional)
- **Conversion succeeds** with no loss of essential timing data

---

## Verification Examples

### Confirming 3A vs 3B System

```python
from one.api import ONE
import numpy as np

one = ONE(base_url="https://openalyx.internationalbrainlab.org",
          password="international", silent=True)

eid = 'dfd8e7df-dc51-4589-b6ca-7baccfeb94b4'  # Example session

# Method 1: Check for NIDQ files
datasets = one.list_datasets(eid=eid)
has_nidq = any('nidq.cbin' in str(d) for d in datasets)

if has_nidq:
    print("3B system (NIDQ present)")
else:
    print("Likely 3A system (no NIDQ)")

# Method 2: Check sync channel numbers
sync_channels = one.load_dataset(
    eid,
    '_spikeglx_sync.channels.probe01.npy',
    collection='raw_ephys_data/probe01'
)

unique_channels = sorted(np.unique(sync_channels))
print(f"Sync channels: {unique_channels}")

# 3A pattern: [2, 3, 4, 12, 13, 14, 15]
# 3B pattern: [0, 1, 2, 3, 4, 5, 6, 7]
if 12 in unique_channels:
    print("Confirmed 3A system (Frame2TTL on channel 12)")
elif 4 in unique_channels and 12 not in unique_channels:
    print("Confirmed 3B system (Frame2TTL on channel 4)")
```

### Extracting Camera Times (Both Systems)

```python
from one.api import ONE
import numpy as np

one = ONE(base_url="https://openalyx.internationalbrainlab.org",
          password="international", silent=True)

eid = 'dfd8e7df-dc51-4589-b6ca-7baccfeb94b4'
probe_name = 'probe01'

# Load preprocessed sync (works for both 3A and 3B)
sync_times = one.load_dataset(
    eid, f'_spikeglx_sync.times.{probe_name}.npy',
    collection=f'raw_ephys_data/{probe_name}'
)
sync_channels = one.load_dataset(
    eid, f'_spikeglx_sync.channels.{probe_name}.npy',
    collection=f'raw_ephys_data/{probe_name}'
)
sync_polarities = one.load_dataset(
    eid, f'_spikeglx_sync.polarities.{probe_name}.npy',
    collection=f'raw_ephys_data/{probe_name}'
)

# Determine channel map (3A vs 3B)
if 12 in sync_channels:  # 3A system
    left_camera_ch = 2
    right_camera_ch = 3
    body_camera_ch = 4
else:  # 3B system
    left_camera_ch = 0
    right_camera_ch = 1
    body_camera_ch = 2

# Extract left camera frame times (rising edges)
left_camera_mask = (sync_channels == left_camera_ch) & (sync_polarities == 1)
left_camera_times = sync_times[left_camera_mask]

print(f"Left camera frames: {len(left_camera_times)}")
print(f"Frame rate: {1/np.diff(left_camera_times).mean():.2f} Hz")
print(f"Session duration: {left_camera_times[-1] - left_camera_times[0]:.2f} seconds")
```

---

## Summary for Users

### For Data Consumers

**Q: Will my analysis work if the session lacks NIDQ data?**

**A: Yes.** All essential timing information is available through preprocessed sync files regardless of whether the source was NIDQ (3B) or probe channels (3A). Your spike times, video frames, and wheel movements are all properly aligned.

**Q: What am I missing if NIDQ is not in the NWB file?**

**A: Raw continuous behavioral sync traces.** You still have all event times (camera frames, wheel movements, stimuli), but not the continuous voltage waveforms. This is typically only needed for:
- Debugging timing issues
- Custom event detection
- Verifying IBL's preprocessed events

**Q: How can I tell if a session is 3A or 3B?**

**A: Check the sync channel numbers:**
- 3A: Sync channels 2, 3, 4, 12-15 (on probe)
- 3B: Sync channels 0-7 (on NIDQ)

Or check the session date:
- Before mid-2020: Likely 3A
- After mid-2020: Likely 3B

### For Data Converters

**Q: Should conversions fail if NIDQ is missing?**

**A: No.** NIDQ is optional. The `IblNIDQInterface` uses `check_availability()` to conditionally add raw NIDQ data. All other interfaces use preprocessed sync files that are always available.

**Q: How do I handle sessions without NIDQ?**

**A: No special handling needed.** The conversion scripts already handle this via:
```python
if IblNIDQInterface.check_availability(one, eid)["available"]:
    data_interfaces.append(IblNIDQInterface(...))
else:
    logger.warning(f"NIDQ data not available - skipping NIDQ interface")
```

**Q: Where is the actual timing source?**

**A: Preprocessed sync files (`_spikeglx_sync.*.npy`).** These are extracted by IBL's pipeline from either:
- NIDQ raw files (3B systems)
- Probe analog channels (3A systems)

The NWB interfaces consume these preprocessed files, not the raw sources.

---

## References

### IBL Pipeline Code

- **Sync extraction**: `ibllib/ephys/sync_probes.py`
  - `version3A()`: 3A probe synchronization
  - `version3B()`: 3B NIDQ synchronization
  - `sync_probe_front_times()`: Creates sample-to-time mapping

- **Camera extraction**: `ibllib/io/extractors/camera.py`
  - `extract_camera_sync()`: Extracts timestamps from sync files

- **Channel maps**: `ibllib/io/extractors/ephys_fpga.py`
  - `CHMAPS['3A']`: 3A channel assignments
  - `CHMAPS['3B']`: 3B channel assignments

### NWB Conversion Code

- **NIDQ interface**: `IBL-to-nwb/src/ibl_to_nwb/datainterfaces/_ibl_nidq_interface.py`
  - Handles raw NIDQ data (when available)

- **Raw conversion**: `IBL-to-nwb/src/ibl_to_nwb/conversion/raw.py`
  - Orchestrates all interfaces with conditional NIDQ

- **Sync documentation**: `documentation/how_samples2times_works.md`
  - Detailed explanation of probe-to-session clock mapping

### Session Diagnosis

- **Availability report**: `session_diagnosis_report_20251105_213640.csv`
  - Per-session data availability across entire BWM dataset
  - Use to identify 3A vs 3B sessions

---

## Document History

- **Created**: 2025-11-05
- **Author**: Claude (Anthropic)
- **Purpose**: Comprehensive reference for NIDQ availability and raw timing sources in IBL sessions
- **Context**: Investigation following NIDQ interface separation and semantic labeling implementation

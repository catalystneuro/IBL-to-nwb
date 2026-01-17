# NIDQ Timing and Synchronization Details

This document consolidates technical details about NIDQ (National Instruments DAQ) timing, availability, and synchronization in IBL recordings. For a high-level overview of IBL's multi-clock synchronization system, see [synchronization.md](../ibl_science/synchronization.md).

---

## Table of Contents

1. [NIDQ Availability Patterns](#nidq-availability-patterns)
2. [Hardware Architecture](#hardware-architecture)
3. [Why 1 kHz Sampling is Sufficient](#why-1-khz-sampling-is-sufficient)
4. [Synchronization Algorithm](#synchronization-algorithm)
5. [NWB Conversion Behavior](#nwb-conversion-behavior)
6. [Verification Examples](#verification-examples)

---

## NIDQ Availability Patterns

### Overview

NIDQ behavioral sync signals are **optional** in IBL NWB conversions. Sessions without NIDQ files fall into two categories:

1. **Neuropixels 3A systems (2019-2020)**: Sync signals recorded on probe analog channels, not on dedicated NIDQ board
2. **Missing uploads**: Had NIDQ hardware but raw files were not uploaded to database

Even without raw NIDQ data, **all timing information is available** through preprocessed sync files (`_spikeglx_sync.*.npy`) that IBL's pipeline extracts from either NIDQ or probe channels.

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

## Why 1 kHz Sampling is Sufficient

### The Question

In IBL's Neuropixels recordings:
- **NIDQ** (master clock) samples at ~1 kHz (1 sample every 1 ms)
- **Probes** sample at 30 kHz (1 sample every 0.033 ms)

This is a 30x difference in sampling rate. Why doesn't NIDQ need to sample faster?

### The Answer

**1 kHz is not only sufficient - it's optimal. Synchronization accuracy is 0.01-0.1ms despite the 1 kHz sampling rate.**

### Key Insight: Event Detection vs Waveform Recording

**NIDQ records discrete events (pulses), not continuous analog signals:**

```
Camera frame pulse:     ┌──────────┐
                        │  10ms    │
                    ────┘          └────
                        ↑          ↑
                     Rising     Falling
                      edge       edge
```

- Events are ON/OFF transitions
- Pulse durations are typically 1-50ms
- 1 kHz sampling (1ms resolution) is more than sufficient to detect these edges

### Why Higher Sampling Wouldn't Help

**Hardware jitter dominates timing uncertainty:**

| Source | Uncertainty |
|--------|-------------|
| Hardware jitter (TTL generation) | 0.1-1ms |
| NIDQ sampling uncertainty | 0.5ms |
| Probe sampling uncertainty | 0.017ms |

Going from 1 kHz to 30 kHz on NIDQ would reduce sampling uncertainty from 0.5ms to 0.017ms, but this is **pointless** because hardware jitter is already 0.1-1ms.

### Cost-Benefit Analysis

| Metric | 1 kHz NIDQ | 30 kHz NIDQ |
|--------|------------|-------------|
| Hardware cost | ~$100 | ~$1000-5000 |
| Data per hour | 79 MB | 2,376 MB (30x more) |
| Processing load | Easy | Heavy |
| Accuracy | 0.01-0.1ms | 0.01-0.1ms (same!) |

---

## Synchronization Algorithm

### Key Concept: Interpolation, Not Direct Sampling

The synchronization doesn't directly compare NIDQ and probe timestamps. Instead, it uses **interpolation between sync points**.

### The Process

```
Step 1: Generate and record imec_sync pulse train (1 Hz square wave)

NIDQ generates:     ┌────┐    ┌────┐    ┌────┐    ┌────┐
                    │    │    │    │    │    │    │    │
                ────┘    └────┘    └────┘    └────┘    └────
                    0s   1s   2s   3s   4s   5s   6s   7s

Step 2: Record on both NIDQ and Probe (same physical pulses, different clocks)

NIDQ records (session time):
  Pulse 1 rising:   0.000000s
  Pulse 1 falling:  1.000123s
  Pulse 2 rising:   2.000456s

Probe records (probe local time - drifting!):
  Pulse 1 rising:   0.000000s   (aligned at start)
  Pulse 1 falling:  1.000456s   (0.3ms drift)
  Pulse 2 rising:   2.001123s   (0.7ms drift)

Step 3: Create mapping and interpolate

Example: A spike occurs at probe time 1.500000s

Find bracketing sync points and interpolate:
  Result: Spike at probe time 1.500000s → session time 1.499523s
```

### Sub-Millisecond Precision from 1 kHz Sampling

The interpolation achieves much higher precision than the NIDQ sampling rate:

```
NIDQ samples at:        1 kHz    (1ms resolution)
Sync pulses occur at:   1 Hz     (every 1 second)
Probe samples at:       30 kHz   (0.033ms resolution)

But interpolation precision:  ~0.01-0.1ms

How? We interpolate between probe timestamps (high resolution)
     using NIDQ timestamps as ground truth (coarse but accurate).
     Result: Interpolation inherits probe's high temporal resolution!
```

### Measured Accuracy

**IBL Quality Control Thresholds**:
```python
THRESH_PPM = 150  # Maximum clock drift: 150 parts per million
tol = 2.5         # Maximum sync error: 2.5 samples at 30 kHz = 0.083ms
```

**Typical synchronization accuracy in IBL data**: **0.01-0.1ms** (10-100 microseconds)

---

## NWB Conversion Behavior

### With NIDQ Available

```python
# Core data interfaces (always added)
data_interfaces.append(IblSortingInterface(...))  # Uses preprocessed sync
data_interfaces.append(WheelInterface(...))       # Uses preprocessed sync
data_interfaces.append(RawVideoInterface(...))    # Uses preprocessed sync

# NIDQ interface (optional, for raw verification)
if IblNIDQInterface.check_availability(one, eid)["available"]:
    nidq_interface = IblNIDQInterface(...)
    data_interfaces.append(nidq_interface)
```

**Result**:
- NWB file contains raw NIDQ continuous data (8 digital + 3 analog channels)
- Users can verify timing by comparing NWB events to raw NIDQ signals

### Without NIDQ Available

```python
# Core data interfaces (always added)
data_interfaces.append(IblSortingInterface(...))  # Uses preprocessed sync
data_interfaces.append(WheelInterface(...))       # Uses preprocessed sync
data_interfaces.append(RawVideoInterface(...))    # Uses preprocessed sync

# NIDQ interface skipped
logger.warning("NIDQ data not available - skipping NIDQ interface")
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

one = ONE()
eid = 'your-session-uuid'

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
    '_spikeglx_sync.channels.probe00.npy',
    collection='raw_ephys_data/probe00'
)

unique_channels = sorted(np.unique(sync_channels))
# 3A pattern: [2, 3, 4, 12, 13, 14, 15]
# 3B pattern: [0, 1, 2, 3, 4, 5, 6, 7]
if 12 in unique_channels:
    print("Confirmed 3A system")
elif 4 in unique_channels and 12 not in unique_channels:
    print("Confirmed 3B system")
```

### Extracting Camera Times (Both Systems)

```python
from one.api import ONE
import numpy as np

one = ONE()
eid = 'your-session-uuid'
probe_name = 'probe00'

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
else:  # 3B system
    left_camera_ch = 0

# Extract left camera frame times (rising edges)
left_camera_mask = (sync_channels == left_camera_ch) & (sync_polarities == 1)
left_camera_times = sync_times[left_camera_mask]

print(f"Left camera frames: {len(left_camera_times)}")
print(f"Frame rate: {1/np.diff(left_camera_times).mean():.2f} Hz")
```

---

## Summary for Users

**Q: Will my analysis work if the session lacks NIDQ data?**

**A: Yes.** All essential timing information is available through preprocessed sync files regardless of whether the source was NIDQ (3B) or probe channels (3A).

**Q: What am I missing if NIDQ is not in the NWB file?**

**A: Raw continuous behavioral sync traces.** You still have all event times (camera frames, wheel movements, stimuli), but not the continuous voltage waveforms. This is typically only needed for debugging timing issues or custom event detection.

**Q: Should conversions fail if NIDQ is missing?**

**A: No.** NIDQ is optional. The conversion scripts handle this via conditional interface addition.

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

### Related Documentation

- [Synchronization](../ibl_science/synchronization.md) - High-level overview of IBL's multi-clock system
- [IblNIDQInterface](../conversion/conversion_modalities.md) - NIDQ interface in NWB conversion

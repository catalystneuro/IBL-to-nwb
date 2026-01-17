# IBL Temporal Synchronization System

**A comprehensive guide to understanding how IBL aligns neural recordings with behavioral events across multiple independent clocks**

**Version**: 2.0
**Last Updated**: 2025-11-05
**Maintainer**: IBL-to-NWB Conversion Project

---

## Table of Contents

1. [The Big Picture: The Synchronization Problem](#the-big-picture-the-synchronization-problem)
2. [The Solution: Multi-Level Hardware Synchronization](#the-solution-multi-level-hardware-synchronization)
3. [Hardware Components](#hardware-components)
4. [Data Files and Their Relationships](#data-files-and-their-relationships)
5. [File Generation Pipeline](#file-generation-pipeline)
6. [NWB Conversion: Unifying to Session Time](#nwb-conversion-unifying-to-session-time)
7. [Detailed Technical Reference](#detailed-technical-reference)

---

## The Big Picture: The Synchronization Problem

### What Problem Are We Solving?

In a typical IBL recording session, we have:
- **1-2 Neuropixels probes** recording neural activity (30,000 samples/second each)
- **3 video cameras** recording behavior (60-150 frames/second each)
- **1 behavioral rig** (Bpod) controlling task events (variable timing)
- **1 wheel** for mouse responses (continuous rotation)
- **Audio stimuli** synchronized with visual stimuli

**The fundamental problem:** Each device has its **own independent clock** that drifts at different rates (typically 10-50 parts per million).

### Why This Matters

```
Scenario: A spike occurs at "1.5 seconds" according to Probe 1's clock
Question: When did this spike occur relative to:
  - The visual stimulus (screen time)?
  - The mouse's wheel turn (wheel encoder time)?
  - Spikes recorded by Probe 2 (Probe 2's clock)?
  - The video frame showing the mouse's reaction (camera time)?

Answer: We cannot know without synchronization!

After 1 hour of recording:
  - Probe 1's clock might be 180 ms ahead
  - Probe 2's clock might be 140 ms behind
  - Camera clock might be 95 ms ahead

→ A 320 ms error between probes would completely misalign neural activity!
```

### The Core Challenge

We need to answer: **"What is the TRUE time that this event occurred in the session?"**

For this, we need:
1. A **single master clock** (ground truth)
2. A way to **distribute timing signals** to all devices
3. A method to **map each device's local time → master time**

---

## The Solution: Multi-Level Hardware Synchronization

IBL solves this using a **three-tier system**:

```
┌─────────────────────────────────────────────────────────────────┐
│ TIER 1: SESSION MASTER CLOCK (NIDQ)                            │
│ Records ALL sync signals in session time @ ~1 kHz              │
│ - Receives TTL pulses from cameras, wheel, audio, etc.        │
│ - Generates imec_sync pulse train for probes                   │
│ - Provides ground truth timestamps                             │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ Distributes sync signals via cables
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ TIER 2: PROBE LOCAL CLOCKS                                     │
│ Record COPIES of sync signals @ 30 kHz (AP) or 2.5 kHz (LF)   │
│ - Each probe has independent clock (drifts ~10-50 ppm)        │
│ - Records sync signals on physical channel 384 (SYNC channel) │
│ - Multiplexes all signals into 16-bit digital word             │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ Offline processing
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ TIER 3: TIME ALIGNMENT FILES                                   │
│ Map probe local time → session master time                     │
│ - Created by matching imec_sync pulses between NIDQ and probes│
│ - Enable samples2times() conversion for all analyses           │
│ - Provide sub-millisecond precision alignment                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Insight: Redundant Recording

The same events (camera pulses, wheel turns, etc.) are recorded **twice**:
1. **By NIDQ** - in session master time (ground truth, low sampling rate)
2. **By each probe** - in probe local time (drifted, high sampling rate)

By **matching the same pulse train** in both recordings, we create a mapping:
```
Probe local time → Session master time
```

---

## Hardware Components

### 1. NIDQ (National Instruments DAQ) - The Master Clock

**Purpose**: Session-level master clock and signal hub

**Hardware**: National Instruments USB-6001 or similar DAQ device

**Sampling Rate**: ~1 kHz (30003 Hz in practice)

**Inputs - Digital Channels** (Port 0, bits 0-7):
| Channel | Signal | Source | Purpose |
|---------|--------|--------|---------|
| P0.0 | `left_camera` | Left camera TTL | Camera frame timestamps |
| P0.1 | `right_camera` | Right camera TTL | Camera frame timestamps |
| P0.2 | `body_camera` | Body camera TTL | Camera frame timestamps |
| P0.3 | `imec_sync` | **NIDQ generates this** | **Critical: Multi-probe alignment** |
| P0.4 | `frame2ttl` | Screen photodiode | Visual stimulus timing |
| P0.5 | `rotary_encoder_0` | Wheel encoder phase A | Wheel position/velocity |
| P0.6 | `rotary_encoder_1` | Wheel encoder phase B | Wheel position/velocity |
| P0.7 | `audio` | Sound card TTL | Audio stimulus timing |

**Inputs - Analog Channels** (AI0-AI2):
| Channel | Signal | Source | Purpose |
|---------|--------|--------|---------|
| AI0 | `bpod` | Bpod TTL output | Task events (thresholded) |
| AI1 | `laser` | Laser power sensor | Optogenetics power |
| AI2 | `laser_ttl` | Laser TTL | Optogenetics timing |

**Outputs**:
- `imec_sync` signal distributed to all probes (1 Hz square wave, critical for alignment)

**Data Files**:
- `_spikeglx_ephysData_g0_t0.nidq.bin` - Binary data (all channels multiplexed)
- `_spikeglx_ephysData_g0_t0.nidq.meta` - Metadata (sampling rate, channel config)
- `_spikeglx_ephysData_g0_t0.nidq.wiring.json` - Documentation of channel mapping (created by experimenter, not hardware)

### 2. Neuropixels Probes - Independent Neural Recorders

**Purpose**: Record neural activity with local clock

**Hardware**: Neuropixels 1.0 or 2.0 probes (384 recording channels + 1 sync channel)

**Sampling Rate**:
- AP (action potential) band: 30 kHz
- LF (local field potential) band: 2.5 kHz

**Physical Channels**:
- Channels 0-383: Neural data
- **Channel 384: SYNC channel (16-bit digital input)**

**SYNC Channel Structure**:
The SYNC channel is a **single 16-bit digital word** where each bit represents a different signal:
```
Bit layout (varies by system, example for 3B):
Bit 0:  left_camera     (from NIDQ P0.0)
Bit 1:  right_camera    (from NIDQ P0.1)
Bit 2:  body_camera     (from NIDQ P0.2)
Bit 6:  imec_sync       (from NIDQ P0.3) ← Critical for alignment!
Bit 4:  frame2ttl       (from NIDQ P0.4)
Bit 5:  rotary_encoder_0 (from NIDQ P0.5)
Bit 6:  rotary_encoder_1 (from NIDQ P0.6)
Bit 7:  audio           (from NIDQ P0.7)
```

**Key Point**: These are **copies** of signals that NIDQ also records. Same pulses, different clocks!

**Data Files**:
- `_spikeglx_ephysData_g0_t0.imec0.ap.bin` - AP band data (30 kHz, 385 channels)
- `_spikeglx_ephysData_g0_t0.imec0.lf.bin` - LF band data (2.5 kHz, 385 channels)
- `_spikeglx_ephysData_g0_t0.imec0.ap.meta` - Metadata (sampling rate, channel config)

### 3. Signal Flow Diagram

#### Complete Signal Path for All Channels

```
═══════════════════════════════════════════════════════════════════════════
EXTERNAL DEVICES → NIDQ (Session Time) → PROBES (Local Time)
═══════════════════════════════════════════════════════════════════════════

1. LEFT CAMERA (e.g., at t=1.234s)
   Camera triggers ──TTL──> NIDQ P0.0 ──cable──> Probe SYNC bit 0
                            @ 1 kHz              @ 30 kHz
                            1.234567s            1.234923s (probe 0)
                            (session time)       1.234512s (probe 1)

2. RIGHT CAMERA (e.g., at t=1.234s)
   Camera triggers ──TTL──> NIDQ P0.1 ──cable──> Probe SYNC bit 1
                            @ 1 kHz              @ 30 kHz
                            1.234567s            1.234923s (probe 0)

3. BODY CAMERA (e.g., at t=1.234s)
   Camera triggers ──TTL──> NIDQ P0.2 ──cable──> Probe SYNC bit 2
                            @ 1 kHz              @ 30 kHz
                            1.234567s            1.234923s (probe 0)

4. IMEC_SYNC (CRITICAL - generated by NIDQ at 1 Hz)
   NIDQ generates  ──TTL──> NIDQ P0.3 ──cable──> Probe SYNC bit 6
   1 Hz square wave         @ 1 kHz              @ 30 kHz
                            0.000, 1.000, 2.000s 0.000, 1.003, 2.007s
                            (ground truth!)      (drifted!)

5. FRAME2TTL (screen photodiode, e.g., at t=0.500s)
   Photodiode ─────TTL──> NIDQ P0.4 ──cable──> Probe SYNC bit 4
                          @ 1 kHz              @ 30 kHz
                          0.500123s            0.500456s (probe 0)

6. ROTARY ENCODER (wheel, continuous pulses)
   Encoder phase A ──TTL──> NIDQ P0.5 ──cable──> Probe SYNC bit 5
   Encoder phase B ──TTL──> NIDQ P0.6 ──cable──> Probe SYNC bit 6
                            @ 1 kHz              @ 30 kHz
                            (every ~10ms)        (every ~10ms)

7. AUDIO STIMULUS (e.g., at t=2.000s)
   Sound card ─────TTL──> NIDQ P0.7 ──cable──> Probe SYNC bit 7
                          @ 1 kHz              @ 30 kHz
                          2.000234s            2.000567s (probe 0)

8. BPOD TASK EVENTS (analog, e.g., trial start at t=5.000s)
   Bpod TTL ──analog──> NIDQ AI0 ──(not sent to probes)
                        @ 1 kHz
                        5.000456s
                        (thresholded to detect events)

9. LASER OPTOGENETICS (analog, when used)
   Laser power ──analog──> NIDQ AI1 ──(not sent to probes)
   Laser TTL ────analog──> NIDQ AI2 ──(not sent to probes)
                           @ 1 kHz

═══════════════════════════════════════════════════════════════════════════
KEY INSIGHT: Every signal is recorded TWICE
═══════════════════════════════════════════════════════════════════════════

NIDQ records:    All signals in SESSION MASTER TIME (ground truth)
                 Lower sampling (1 kHz) but correct time reference

Probes record:   Copies of digital signals in PROBE LOCAL TIME (drifted)
                 Higher sampling (30 kHz) but needs alignment

By MATCHING the same pulses (especially imec_sync), we create:
    Probe local time → Session master time mapping

═══════════════════════════════════════════════════════════════════════════
```

#### Example: Following One Pulse Through the System

```
Event: Left camera captures frame at true time T

Step 1: Camera generates TTL pulse
        ┌──────────┐
        │   10ms   │  5V pulse
    ────┘          └────

Step 2: NIDQ receives pulse on P0.0
        Sampled at 1 kHz (every 1ms)
        Detects rising edge at timestamp: T + 0.123ms
        Detects falling edge at timestamp: T + 10.456ms
        Stored in: nidq.bin, NIDQ clock (session time)

Step 3: NIDQ distributes pulse to probes via cable
        (same physical pulse, ~0.01ms propagation delay)

Step 4: Probe 0 receives pulse on SYNC channel bit 0
        Sampled at 30 kHz (every 0.033ms)
        Detects rising edge at timestamp: T + 0.456ms (in Probe 0's clock)
        Stored in: imec0.ap.bin, Probe 0 clock (local time, DRIFTED)
        Sample index: 13680 (at 30 kHz)

Step 5: Probe 1 receives pulse on SYNC channel bit 0
        Sampled at 30 kHz (every 0.033ms)
        Detects rising edge at timestamp: T + 0.234ms (in Probe 1's clock)
        Stored in: imec1.ap.bin, Probe 1 clock (local time, DRIFTED differently!)
        Sample index: 7020 (at 30 kHz)

Result: Same physical pulse → THREE different timestamps
        NIDQ:    T + 0.123ms  (session time - GROUND TRUTH)
        Probe 0: T + 0.456ms  (probe 0 local time - needs conversion)
        Probe 1: T + 0.234ms  (probe 1 local time - needs conversion)

The difference (0.333ms between probes) is CLOCK DRIFT that must be corrected!
```

---

## Data Files and Their Relationships

### File Hierarchy: From Hardware to Analysis

```
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 1: RAW BINARY FILES (Hardware output)                    │
├─────────────────────────────────────────────────────────────────┤
│ Written during recording by SpikeGLX software                  │
│                                                                 │
│ NIDQ:                                                          │
│   _spikeglx_ephysData_g0_t0.nidq.bin   (~1 kHz, 11 channels)  │
│   _spikeglx_ephysData_g0_t0.nidq.meta  (metadata)              │
│                                                                 │
│ Probe 0:                                                       │
│   _spikeglx_ephysData_g0_t0.imec0.ap.bin  (30 kHz, 385 ch)    │
│   _spikeglx_ephysData_g0_t0.imec0.lf.bin  (2.5 kHz, 385 ch)   │
│   _spikeglx_ephysData_g0_t0.imec0.ap.meta  (metadata)         │
│                                                                 │
│ Probe 1:                                                       │
│   _spikeglx_ephysData_g0_t0.imec1.ap.bin  (30 kHz, 385 ch)    │
│   _spikeglx_ephysData_g0_t0.imec1.lf.bin  (2.5 kHz, 385 ch)   │
│   _spikeglx_ephysData_g0_t0.imec1.ap.meta  (metadata)         │
│                                                                 │
│ Documentation (optional, created by experimenter):             │
│   _spikeglx_ephysData_g0_t0.nidq.wiring.json (channel map)    │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ Extract sync pulses (_sync_to_alf)
                           │ Source: ibllib/io/extractors/ephys_fpga.py:138-186
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 2: EXTRACTED SYNC ARRAYS (ALF format)                    │
├─────────────────────────────────────────────────────────────────┤
│ Created by IBL preprocessing pipeline                          │
│ Uploaded to ONE database for analysis                          │
│                                                                 │
│ From NIDQ:                                                     │
│   _spikeglx_sync.times.npy         (pulse times, session time)│
│   _spikeglx_sync.channels.npy      (channel IDs, 0-7 for P0.x)│
│   _spikeglx_sync.polarities.npy    (+1 rising, -1 falling)   │
│                                                                 │
│ From Probe 0:                                                  │
│   _spikeglx_sync.times.probe00.npy       (pulse times, probe) │
│   _spikeglx_sync.channels.probe00.npy    (bit IDs, 0-15)     │
│   _spikeglx_sync.polarities.probe00.npy  (+1 rising, -1 fall)│
│                                                                 │
│ From Probe 1:                                                  │
│   _spikeglx_sync.times.probe01.npy                            │
│   _spikeglx_sync.channels.probe01.npy                         │
│   _spikeglx_sync.polarities.probe01.npy                       │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ Match imec_sync pulses (sync_probes.py)
                           │ Source: ibllib/ephys/sync_probes.py:116-174
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 3: TIME ALIGNMENT FILES (Final products)                 │
├─────────────────────────────────────────────────────────────────┤
│ Map probe local time → session master time                     │
│ Used by all downstream analyses                                 │
│                                                                 │
│ Probe 0 alignment:                                             │
│   _spikeglx_ephysData_g0_t0.imec0.sync.npy                    │
│     Shape: [N, 2]                                             │
│     Column 0: Probe 0 time (seconds in probe clock)           │
│     Column 1: Session time (seconds in NIDQ clock)            │
│                                                                 │
│   _spikeglx_ephysData_g0_t0.imec0.timestamps.npy              │
│     Shape: [N, 2]                                             │
│     Column 0: Probe 0 sample index (integers, 0-based)        │
│     Column 1: Session time (seconds in NIDQ clock)            │
│                                                                 │
│ Probe 1 alignment:                                             │
│   _spikeglx_ephysData_g0_t0.imec1.sync.npy                    │
│   _spikeglx_ephysData_g0_t0.imec1.timestamps.npy              │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ Used by samples2times()
                           │ Source: brainbox/io/one.py:1207-1216
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 4: ANALYSIS & NWB CONVERSION                             │
├─────────────────────────────────────────────────────────────────┤
│ All data aligned to SESSION MASTER TIME                        │
│                                                                 │
│ - Spike times: samples2times(spike_samples) → session seconds │
│ - LFP times: samples2times(lfp_samples) → session seconds     │
│ - Behavior events: already in session time (from NIDQ)        │
│ - Videos: frame2ttl pulses in session time (from NIDQ)        │
└─────────────────────────────────────────────────────────────────┘
```

### File Relationships Diagram

```
Hardware Recording (SpikeGLX):
  NIDQ.bin ──────────┐
  Probe0.ap.bin ─────┤
  Probe0.lf.bin ─────┤
  Probe1.ap.bin ─────┤
  Probe1.lf.bin ─────┤
                     │
                     │ Extract sync pulses (_sync_to_alf)
                     │ Source: ibllib/io/extractors/ephys_fpga.py
                     ▼
  sync.times.npy ────┐ (NIDQ - session time)
  sync.times.probe00 ┼─┐ (Probe 0 - local time)
  sync.times.probe01 ┘ │ (Probe 1 - local time)
                       │
                       │ Match imec_sync pulses (sync_probes.version3B)
                       │ Source: ibllib/ephys/sync_probes.py
                       ▼
  imec0.sync.npy ──────┐ (Probe 0 time → Session time)
  imec0.timestamps.npy │ (Probe 0 samples → Session time)
  imec1.sync.npy ──────┤ (Probe 1 time → Session time)
  imec1.timestamps.npy ┘ (Probe 1 samples → Session time)
                       │
                       │ NWB Conversion (samples2times)
                       │ Source: brainbox/io/one.py + ibl-to-nwb
                       ▼
  All data in unified SESSION TIME (NIDQ master clock)
  ↓
  NWB file with all modalities synchronized
```

---

## File Generation Pipeline

### Stage 1: Recording (SpikeGLX Software)

**When**: During live experiment

**Software**: SpikeGLX (https://billkarsh.github.io/SpikeGLX/)

**Process**:
1. SpikeGLX interfaces with NIDQ and probes via hardware drivers
2. Continuously writes binary data to disk during recording
3. Metadata files (.meta) written with hardware configuration
4. Experimenter may create wiring.json to document channel mapping

**Output**:
- `.bin` files (binary data: int16 samples, all channels multiplexed)
- `.meta` files (sampling rates, channel counts, gain, etc.)
- `.wiring.json` files (optional documentation of NIDQ channel → signal mapping)

**Source**: Hardware drivers + SpikeGLX application

**Note**: IBL stores data as `.cbin` (compressed) in the database for space efficiency, but this is a storage detail. The conceptual output is raw binary samples.

### Stage 2: Sync Pulse Extraction (IBL Preprocessing)

**When**: Offline, after recording session uploaded

**Software**: ibllib (IBL's Python library)

**Process**:
```python
# Source: ibllib/io/extractors/ephys_fpga.py:138-186
def _sync_to_alf(raw_ephys_apfile, output_path=None, save=False, parts=''):
    """
    Extracts sync.times, sync.channels and sync.polarities from binary ephys dataset

    Key steps:
    1. Open .bin file with spikeglx.Reader
    2. Read SYNC channel (ch 384 for probes, digital channels for NIDQ)
    3. Detect rising/falling edges using ibldsp.utils.fronts()
    4. Unpack multiplexed bits into individual channel events
    5. Save as ALF format arrays (times, channels, polarities)
    """
    sr = spikeglx.Reader(raw_ephys_apfile)

    # Process in chunks to handle large files
    wg = ibldsp.utils.WindowGenerator(sr.ns, int(SYNC_BATCH_SIZE_SECS * sr.fs), overlap=1)

    all_events = []
    for sl in wg.slice:
        # Read SYNC channel (ch 384) for this time window
        sync_data = sr.read_sync(sl)  # Returns 16-bit digital word

        # Detect edges (transitions from 0→1 or 1→0)
        sample_indices, channel_bits = ibldsp.utils.fronts(sync_data, axis=0)

        # Convert to (time, channel, polarity) format
        times = (sample_indices[0, :] + sl.start) / sr.fs  # Sample → seconds
        channels = sample_indices[1, :]  # Bit number (0-15)
        polarities = fronts.astype(np.double)  # +1 or -1

        all_events.append(np.c_[times, channels, polarities])

    # Concatenate all chunks
    events = np.vstack(all_events)

    return {
        'times': events[:, 0],
        'channels': events[:, 1],
        'polarities': events[:, 2]
    }
```

**Applied to**:
- NIDQ `.bin` file → `_spikeglx_sync.times.npy` (session time)
- Each probe `.ap.bin` → `_spikeglx_sync.times.probe*.npy` (probe local time)

**Output**: ALF sync arrays uploaded to ONE database

**Source**:
- Function: `_sync_to_alf()` in `ibllib/io/extractors/ephys_fpga.py`
- Edge detection: `ibldsp.utils.fronts()`

### Stage 3: Time Alignment (IBL Preprocessing)

**When**: After sync pulse extraction

**Software**: ibllib synchronization module

**Process**:
```python
# Source: ibllib/ephys/sync_probes.py:116-174
def version3B(ses_path, display=True, type=None, tol=2.5, probe_names=None):
    """
    Synchronize probes to NIDQ using imec_sync pulse train

    For Neuropixels 3B (modern IBL standard):
    1. Load extracted sync arrays for NIDQ and all probes
    2. Extract imec_sync pulses (NIDQ channel 3, Probe bit 6)
    3. Match pulse trains (should have ~same number within 10%)
    4. Create interpolation mapping: probe time → session time
    5. Save sync.npy and timestamps.npy for each probe
    """

    # Load sync arrays
    nidq_file = find_nidq_file(ses_path)
    nidq_sync = load_sync(nidq_file)  # From Level 3 files

    # Extract imec_sync channel from NIDQ (channel 3)
    nidq_imec_times = get_sync_fronts(
        nidq_sync,
        channel_nb=nidq_sync_map['imec_sync']  # Usually channel 3
    )

    for probe in probes:
        # Load probe sync arrays
        probe_sync = load_sync(probe_file)

        # Extract imec_sync channel from probe (bit 6 in 3B)
        probe_imec_times = get_sync_fronts(
            probe_sync,
            channel_nb=probe_sync_map['imec_sync']  # Usually bit 6
        )

        # Verify pulse counts match (within 10% tolerance)
        assert np.isclose(
            len(nidq_imec_times),
            len(probe_imec_times),
            rtol=0.1
        ), "Sync pulse mismatch!"

        # Match pulses and create alignment
        # This creates the mapping: probe_time → nidq_time
        sync_points, qc = sync_probe_front_times(
            probe_imec_times.times,  # Probe local time (seconds)
            nidq_imec_times.times,   # Session time (seconds)
            sampling_rate=30000       # For timestamps.npy
        )

        # Save alignment files
        _save_timestamps_npy(probe, sync_points, sampling_rate)
```

**Key Algorithm** (`sync_probe_front_times`):
```python
def sync_probe_front_times(t_probe, t_nidq, sr):
    """
    Create alignment from matched pulse times

    Parameters
    ----------
    t_probe : array
        Probe imec_sync pulse times (probe local clock)
    t_nidq : array
        NIDQ imec_sync pulse times (session master clock)
    sr : float
        Sampling rate (30000 Hz for AP band)

    Returns
    -------
    sync_points : array [N, 2]
        Column 0: Probe time or sample index
        Column 1: Corresponding session time
    """
    # Fit linear drift model
    pol = np.polyfit(t_probe, t_nidq, 1)  # slope, intercept

    # Compute residual (non-linear drift)
    residual = t_nidq - np.polyval(pol, t_probe)

    # Smooth residual using frequency-domain filtering
    # (removes high-frequency noise while preserving drift)
    residual_smoothed = fourier_lowpass(residual)

    # Combine linear + smoothed residual
    # Sample every 20 seconds for efficient storage
    t_out = np.arange(0, np.max(t_nidq) + 20, 20)
    sync_points = np.c_[
        t_out,  # Probe time
        np.polyval(pol, t_out) + np.interp(t_out, t_nidq, residual_smoothed)
    ]

    return sync_points
```

**Output**:
- `*.sync.npy` - Time alignment (probe seconds → session seconds)
- `*.timestamps.npy` - Sample alignment (probe samples → session seconds)

**Source**:
- Main function: `version3B()` in `ibllib/ephys/sync_probes.py`
- Alignment algorithm: `sync_probe_front_times()` in same file

### Stage 4: NWB Conversion (This Project)

**When**: When creating NWB files from IBL data

**Software**: ibl-to-nwb converter (this repository)

**Process**: Use `samples2times()` to convert ALL probe data to session time

---

## NWB Conversion: Unifying to Session Time

### The Goal

**ALL data in the NWB file must be in a single, unified time basis: SESSION MASTER TIME (NIDQ clock)**

### Why Session Time (NIDQ) is the Master

1. **Ground truth**: NIDQ records original signals from external devices
2. **Behavioral data**: Task events, video frames, wheel position all in NIDQ time
3. **Multi-probe alignment**: Can only align multiple probes via common NIDQ reference
4. **Standard reference**: Enables cross-session, cross-lab comparisons

### What Gets Converted

```
DATA IN PROBE TIME               →  Conversion  →  DATA IN SESSION TIME
══════════════════════           ═══════════════  ═══════════════════════

Spike times (samples)            samples2times() → Spike times (seconds)
Spike amplitudes (at samples)    samples2times() → Amplitudes (at session time)
LFP samples                      samples2times() → LFP timestamps
Raw AP/LF continuous data        samples2times() → Continuous timestamps

ALL PROBE DATA converted to session time!


DATA ALREADY IN SESSION TIME    →  No change  →  DATA IN SESSION TIME
═══════════════════════════     ═══════════════  ═══════════════════════

Trial start/end times                   ✓       → Already session time
Wheel position/velocity times           ✓       → Already session time
Lick times                              ✓       → Already session time
Camera frame times (frame2ttl)          ✓       → Already session time
Audio stimulus times                    ✓       → Already session time


DATA IN VIDEO TIME               →  Conversion  →  DATA IN SESSION TIME
═══════════════════════         ═══════════════  ═══════════════════════

Video frame indices              Camera TTL      → Video frame timestamps
                                 (from NIDQ)

Process:
  1. Extract camera TTL pulses from NIDQ (P0.0, P0.1, P0.2)
     → These are already in session time!
  2. Each rising edge = one video frame captured
  3. Frame index N → session time = TTL_times[N]

Example:
  Video frame 0  → TTL pulse at 1.234s (session time)
  Video frame 1  → TTL pulse at 1.251s (session time)
  Video frame 2  → TTL pulse at 1.267s (session time)
  ...

Result: Video frames aligned to session time via camera TTL pulses
```

### How Conversion Works: samples2times()

**Location**: `brainbox/io/one.py:1207-1216` (IBL's brainbox library)

**Used by**: `IblSortingInterface`, `IblRecordingInterface` in ibl-to-nwb

```python
class SpikeSortingLoader:
    """IBL's standard interface for loading spike sorting data"""

    def samples2times(self, values, direction='forward', band='ap'):
        """
        Convert probe sample indices to session timestamps

        Parameters
        ----------
        values : array
            Sample indices (forward) or session times (reverse)
        direction : str
            'forward' (samples → time) or 'reverse' (time → samples)
        band : str
            'ap' or 'lf' (affects sampling rate)

        Returns
        -------
        array
            Session timestamps (forward) or sample indices (reverse)
        """
        # Load alignment files on first call
        self._get_probe_info()

        # Use pre-computed interpolation function
        return self._sync[direction](values)

    def _get_probe_info(self):
        """Load timestamps.npy and create interpolation functions"""
        if self._sync is not None:
            return  # Already loaded

        # Load timestamps file (Level 4 from file hierarchy)
        timestamps = self.one.load_dataset(
            self.eid,
            dataset='_spikeglx_*.timestamps.npy',
            collection=f'raw_ephys_data/{self.probe_name}'
        )
        # Shape: [N, 2]
        #   Column 0: Probe sample indices
        #   Column 1: Session time (seconds)

        # Create bidirectional interpolation functions
        self._sync = {
            'timestamps': timestamps,
            'forward': interp1d(
                timestamps[:, 0],  # Probe samples (input)
                timestamps[:, 1],  # Session time (output)
                fill_value='extrapolate'
            ),
            'reverse': interp1d(
                timestamps[:, 1],  # Session time (input)
                timestamps[:, 0],  # Probe samples (output)
                fill_value='extrapolate'
            ),
            'fs': 30000,  # Sampling rate
        }
```

### NWB Conversion Examples

#### Example 1: Converting Spike Times

```python
# In ibl-to-nwb: IblSortingInterface

# Load spike data (in probe sample indices)
spike_samples = one.load_object(eid, 'spikes', collection=f'alf/{probe_name}')
# spike_samples.times is in probe sample indices!

# Create sorting loader
ssl = SpikeSortingLoader(one=one, eid=eid, pname=probe_name, pid=pid)

# Convert ALL spike times to session time
spike_times_session = ssl.samples2times(
    spike_samples.times,  # Probe sample indices
    direction='forward'    # samples → time
)

# Now spike_times_session is in SESSION TIME (NIDQ master clock)
# Can be directly compared to behavioral events!
```

#### Example 2: Converting Continuous Data Timestamps

```python
# In ibl-to-nwb: IblRecordingInterface

# Continuous AP data has N samples at 30 kHz
n_samples = recording.get_num_samples()

# Create timestamp for EVERY sample
all_sample_indices = np.arange(0, n_samples)  # [0, 1, 2, ..., n_samples-1]

# Convert to session time
timestamps_session = ssl.samples2times(
    all_sample_indices,
    direction='forward'
)

# Result: timestamps_session[i] = session time for sample i
# These go into NWB ElectricalSeries.timestamps
```

#### Example 3: Converting Video Frame Timestamps

```python
# In ibl-to-nwb: Video interface

# Load camera TTL pulses from NIDQ (already in session time)
camera_ttls = one.load_dataset(
    eid,
    dataset='_spikeglx_sync.times.npy',
    collection='raw_ephys_data'
)

# Extract left camera channel (P0.0 = channel 0)
camera_channels = one.load_dataset(
    eid,
    dataset='_spikeglx_sync.channels.npy',
    collection='raw_ephys_data'
)
camera_polarities = one.load_dataset(
    eid,
    dataset='_spikeglx_sync.polarities.npy',
    collection='raw_ephys_data'
)

# Get rising edges of left camera (each = one frame)
left_camera_mask = (camera_channels == 0) & (camera_polarities == 1)
frame_timestamps_session = camera_ttls[left_camera_mask]

# Result: frame_timestamps_session[i] = session time for video frame i
# Video frame 0 → 1.234s
# Video frame 1 → 1.251s (60 fps = 16.7ms between frames)
# Video frame 2 → 1.267s
# ...

# Now video frames are aligned to neural/behavioral data!
```

#### Example 4: Aligning Spikes with Behavior and Video

```python
# After conversion, everything is in session time:

# Neural data (converted from probe time)
spike_times = ssl.samples2times(spike_samples.times)  # Session time

# Behavioral data (already in session time from NIDQ)
trial_start_times = trials.intervals[:, 0]  # Session time
wheel_times = wheel.timestamps  # Session time
lick_times = licks.times  # Session time

# Video data (aligned via camera TTL from NIDQ)
video_frame_times = frame_timestamps_session  # Session time

# Now we can directly compare across ALL modalities:
trial_start = trial_start_times[0]
trial_end = trial_start + 2.0

# Get spikes in first 2 seconds of trial
spikes_in_trial = spike_times[
    (spike_times > trial_start) &
    (spike_times < trial_end)
]

# Get wheel movements during same period
wheel_in_trial = wheel_times[
    (wheel_times > trial_start) &
    (wheel_times < trial_end)
]

# Get video frames during same period
frames_in_trial = np.where(
    (video_frame_times > trial_start) &
    (video_frame_times < trial_end)
)[0]

# All three modalities perfectly synchronized!
# Can analyze: "What did the animal do (video) when this neuron fired (spikes)
#               and the wheel turned (behavior)?"
```

### Verification: Are We Using the Correct Time Basis?

**Yes!** Here's how to verify:

1. **Check alignment file source**:
```python
# timestamps.npy column 1 comes from NIDQ imec_sync times
# Source: sync_probes.version3B() line 170:
timestamps, qc = sync_probe_front_times(
    sync_probe.times,  # Probe local time (input)
    sync_nidq.times,   # NIDQ session time (output) ← This becomes column 1!
    sr
)
```

2. **Check samples2times() output**:
```python
# samples2times() uses timestamps[:, 1] as output
# This is NIDQ session time!
forward_func = interp1d(
    timestamps[:, 0],  # Probe samples
    timestamps[:, 1],  # NIDQ session time ← Interpolation target!
    fill_value='extrapolate'
)
```

3. **Cross-reference with behavioral data**:
```python
# Behavioral events are extracted from NIDQ directly
# Source: ibllib/io/extractors/ephys_fpga.py
trials.intervals  # From NIDQ bpod channel, in NIDQ time
wheel.timestamps  # From NIDQ wheel channels, in NIDQ time
licks.times      # From NIDQ lick sensor, in NIDQ time

# After samples2times(), neural data matches these timestamps
```

**Conclusion**: All NWB data is in **SESSION MASTER TIME (NIDQ clock basis)** ✓

---

## Detailed Technical Reference

### Critical Source Code References

1. **Sync pulse extraction**:
   - File: `ibllib/io/extractors/ephys_fpga.py`
   - Function: `_sync_to_alf()` (lines 138-186)
   - Purpose: Read binary files, detect edges, save ALF arrays

2. **Time alignment**:
   - File: `ibllib/ephys/sync_probes.py`
   - Function: `version3B()` (lines 116-174)
   - Purpose: Match imec_sync pulses, create alignment files

3. **Pulse matching algorithm**:
   - File: `ibllib/ephys/sync_probes.py`
   - Function: `sync_probe_front_times()` (lines 177-251)
   - Purpose: Linear + smoothed residual drift correction

4. **Sample to time conversion**:
   - File: `brainbox/io/one.py`
   - Class: `SpikeSortingLoader`
   - Method: `samples2times()` (lines 1207-1216)
   - Purpose: Convert probe samples → session time for analysis

5. **NWB conversion usage**:
   - File: `ibl_to_nwb/datainterfaces/ibl_sorting_interface.py`
   - File: `ibl_to_nwb/datainterfaces/ibl_recording_interface.py`
   - Purpose: Convert all probe data to session time for NWB

### Channel Mappings Reference

**Neuropixels 3B** (IBL standard):
```python
# Source: ibllib/io/extractors/ephys_fpga.py:73-101
CHMAPS = {
    '3B': {
        'nidq': {
            'left_camera': 0,      # P0.0
            'right_camera': 1,     # P0.1
            'body_camera': 2,      # P0.2
            'imec_sync': 3,        # P0.3 ← Critical!
            'frame2ttl': 4,        # P0.4
            'rotary_encoder_0': 5, # P0.5
            'rotary_encoder_1': 6, # P0.6
            'audio': 7,            # P0.7
            'bpod': 16,            # AI0 (analog)
            'laser': 17,           # AI1 (analog)
            'laser_ttl': 18        # AI2 (analog)
        },
        'ap': {
            'imec_sync': 6         # Probe SYNC ch bit 6
        }
    }
}
```

### File Format Details

**timestamps.npy structure**:
```python
# Shape: [N_sync_points, 2]
# Typical N_sync_points: ~180-200 per hour (every 20 seconds)

timestamps = np.array([
    [0,      0.000000],    # Sample 0 → 0.0 seconds session time
    [600000, 20.000134],   # Sample 600k → 20.0 seconds (with drift)
    [1200000, 40.000402],  # Sample 1.2M → 40.0 seconds
    # ... continues throughout session
])

# Column 0: Probe sample indices (integers)
# Column 1: Corresponding session time (float seconds)

# Usage: Linear interpolation between points
```

**sync.times.npy structure**:
```python
# Shape: [N_pulses,] - typically millions of events

times = np.array([
    0.033245,  # First pulse at 33ms (probe local time)
    0.033412,  # Rising edge of different channel
    0.043256,  # Next pulse at 43ms
    # ... millions of events
])

channels = np.array([
    6,   # imec_sync bit 6
    2,   # frame2ttl bit 2
    6,   # imec_sync bit 6 again
    # ... corresponds to times array
])

polarities = np.array([
    1,   # Rising edge (0 → 1)
    1,   # Rising edge
    -1,  # Falling edge (1 → 0)
    # ... corresponds to times array
])
```

---

## Summary

### The Complete Pipeline

1. **Hardware records** same events on NIDQ (session time) and probes (local time)
2. **SpikeGLX** writes compressed binary files during recording
3. **IBL preprocessing** extracts sync pulses from both NIDQ and probes
4. **Synchronization algorithm** matches imec_sync pulses to create alignment
5. **NWB conversion** uses `samples2times()` to unify all data to session time
6. **Result**: All NWB data referenced to SESSION MASTER TIME (NIDQ clock)

### Key Takeaways

- **NIDQ = ground truth**: Session master clock, ~1 kHz sampling
- **Probes = high resolution**: Local clocks, 30 kHz sampling, independent drift
- **imec_sync = alignment signal**: 1 Hz pulse train for matching clocks
- **timestamps.npy = conversion tool**: Maps probe samples → session time
- **samples2times() = interface**: Converts probe data to session time for NWB
- **Session time = final basis**: All NWB data unified to NIDQ master clock

---

## References

### IBL Documentation
- **IBL Public Docs**: https://docs.internationalbrainlab.org
- **ONE API**: https://int-brain-lab.github.io/ONE/
- **ibllib Source**: https://github.com/int-brain-lab/ibllib

### Source Code
- **Sync extraction**: `ibllib/io/extractors/ephys_fpga.py`
- **Probe alignment**: `ibllib/ephys/sync_probes.py`
- **Analysis tools**: `brainbox/io/one.py`
- **NWB conversion**: `ibl-to-nwb` (this repository)

### Hardware
- **SpikeGLX Manual**: https://billkarsh.github.io/SpikeGLX/
- **Neuropixels**: https://www.neuropixels.org/
- **National Instruments DAQ**: https://www.ni.com/

---

**End of Document**

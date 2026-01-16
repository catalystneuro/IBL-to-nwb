# IBL Wheel Data Documentation

## Overview

The **IBL Wheel** is a critical behavioral input device in the International Brain Laboratory's decision-making task. During experiments, head-fixed mice use a physical wheel to report their perceptual decisions by rotating it left or right. The wheel provides precise, continuous measurements of the animal's motor output and serves as the primary behavioral readout.

## Scientific Purpose

**Why Wheel Data Matters:**
- **Behavioral Quantification**: Provides objective, high-resolution measurements of the animal's decision
- **Reaction Time Analysis**: Enables precise timing of movement initiation relative to stimuli
- **Motor Planning Studies**: Reveals preparatory movements and hesitation patterns
- **Decision Confidence**: Movement kinematics correlate with decision confidence
- **Trial-by-Trial Analysis**: Continuous position data enables fine-grained behavioral characterization

## Physical Setup

### Hardware Specifications
- **Wheel Diameter**: 6.2 cm
- **Encoder Type**: Rotary encoder
- **Resolution**: 1024 ticks per revolution in X4 encoding (4096 effective ticks)
- **Mounting**: Positioned under the animal's forepaws during head-fixation

### Coordinate Convention
- **Reference Frame**: Initial angle at session start is zero
- **Sign Convention**: Counter-clockwise rotation is positive (mathematical convention)
- **Units**: Radians (absolute unwrapped angle)

## Signal Acquisition

### Rotary Encoder Hardware

The wheel position is measured using a **quadrature rotary encoder** that outputs two phase-shifted digital signals (channels A and B). This is a standard industrial method for measuring both position and direction of rotation.

**Quadrature Encoding Principle**:
```
Channel A:  ──┐   ┌───┐   ┌───┐   ┌──
              │   │   │   │   │   │
              └───┘   └───┘   └───┘

Channel B:    ┌───┐   ┌───┐   ┌───┐
              │   │   │   │   │   │
            ──┘   └───┘   └───┘   └──

              90° phase offset determines direction
```

**How It Works**:
1. **Two channels (A and B)** produce square wave pulses as the wheel rotates
2. **90-degree phase offset** between channels encodes direction:
   - Channel A leads channel B: clockwise rotation
   - Channel B leads channel A: counter-clockwise rotation
3. **X4 encoding** counts all rising and falling edges on both channels, providing 4x the resolution (4096 effective ticks from 1024-tick encoder)

### Signal Path

The rotary encoder signals are captured by the NIDQ (National Instruments DAQ) system, which serves as the session master clock:

```
                                    NIDQ (Master Clock)        Neuropixels Probes
                                    ┌─────────────────┐        ┌─────────────────┐
Rotary Encoder ──Phase A──TTL──────>│ P0.5 (channel 5)│──cable─>│ SYNC bit 5      │
               ──Phase B──TTL──────>│ P0.6 (channel 6)│──cable─>│ SYNC bit 6      │
                                    └─────────────────┘        └─────────────────┘
                                          @ ~1 kHz                   @ 30 kHz
                                     (session time)              (probe local time)
```

**Key Points**:
- **NIDQ records both encoder channels** as digital inputs on P0.5 and P0.6
- **Timestamps are in session master time** (ground truth for synchronization)
- **Probes also record encoder signals** via SYNC channel for redundant timing
- **Position is computed** from the TTL edge transitions using X4 decoding

### Position Extraction Algorithm

The IBL pipeline extracts wheel position from the raw TTL fronts using the `_rotary_encoder_positions_from_fronts()` function:

```python
# Simplified X4 decoding logic (from ibllib)
def decode_quadrature_x4(times_a, polarities_a, times_b, polarities_b, ticks=1024):
    """
    Decode quadrature encoder using X4 encoding.

    X4 encoding counts all edges (rising and falling) on both channels,
    providing 4x the resolution of the base encoder ticks.
    """
    # Combine edges from both channels
    # Direction determined by phase relationship at each edge
    # Cumulative sum gives absolute position
    position = cumsum(direction_at_each_edge) / ticks * 2 * pi / 4
    return timestamps, position
```

**Resolution Calculation**:
- Base encoder: 1024 ticks/revolution
- X4 encoding: 4096 effective ticks/revolution
- Angular resolution: 2pi / 4096 = 0.00153 radians (~0.088 degrees)

### Hardware Versions

**3B Systems (with NIDQ)**:
| Channel | Signal | NIDQ Pin |
|---------|--------|----------|
| `rotary_encoder_0` | Phase A | P0.5 |
| `rotary_encoder_1` | Phase B | P0.6 |

**3A Systems (without NIDQ)**:
| Channel | Signal | Probe SYNC Bit |
|---------|--------|----------------|
| `rotary_encoder_0` | Phase A | Bit 13 |
| `rotary_encoder_1` | Phase B | Bit 14 |

For 3A systems, wheel timestamps are extracted from the probe's SYNC channel and synchronized via the same preprocessing pipeline.

### Timing Synchronization

Wheel data is already in **session master time** because:
1. NIDQ records encoder TTL pulses with its own clock (ground truth)
2. Position extraction uses NIDQ timestamps directly
3. No additional time alignment is needed for wheel data

This makes wheel timestamps directly comparable to:
- Neural spike times (after `samples2times()` conversion)
- Camera frame times
- Trial event times
- Audio stimulus times

## Data Streams

### 1. Raw Wheel Position (`wheel`)

**Description**: Continuous measurement of wheel angle over time

**Data Files**:
- `alf/wheel.position.npy` - Wheel position in radians
- `alf/wheel.timestamps.npy` - Timestamps for each position sample

**Characteristics**:
- Absolute unwrapped angle (accumulates across full rotations)
- Variable sampling rate (event-driven from encoder)
- High temporal precision

### 2. Wheel Movements (`wheelMoves`)

**Description**: Detected discrete movement epochs extracted from continuous position

**Data Files**:
- `alf/wheelMoves.intervals.npy` - Start and stop times of detected movements
- `alf/wheelMoves.peakAmplitude.npy` - Maximum amplitude of each movement

**Movement Detection Algorithm**:
- **Minimum displacement**: 0.012 radians (~8 encoder ticks) over 200ms
- **Minimum duration**: Movements below 50ms are discarded
- **Merge threshold**: Movements within 100ms are combined into single movement
- **Onset refinement**: Lower threshold used to find precise onset time

### 3. Derived Signals (Computed During Conversion)

**Velocity**:
- Computed from position interpolated at 1000 Hz
- 8th order lowpass Butterworth filter applied
- Units: rad/s

**Acceleration**:
- Computed from velocity
- Same filtering as velocity
- Units: rad/s^2

## IBL-to-NWB Conversion

### Interface: `WheelInterface`

**Purpose**: Converts wheel behavioral data to NWB format

**Revision**: Uses BWM standard revision "2025-05-06"

### Data Requirements

```python
{
    "one_objects": [
        {
            "object": "wheel",
            "collection": "alf",
            "attributes": ["position", "timestamps"],
        },
        {
            "object": "wheelMoves",
            "collection": "alf",
            "attributes": ["intervals", "peakAmplitude"],
        },
    ],
    "exact_files": [
        "alf/wheel.position.npy",
        "alf/wheel.timestamps.npy",
        "alf/wheelMoves.intervals.npy",
        "alf/wheelMoves.peakAmplitude.npy",
    ],
}
```

### NWB Output Structure

```
NWBFile
└── processing
    └── wheel                              # Processing module
        ├── SpatialSeriesWheelPosition     # Raw position data
        │   ├── data: wheel positions (radians)
        │   ├── timestamps: sample times
        │   └── reference_frame: "Initial angle at start..."
        ├── TimeSeriesWheelVelocity        # Derived velocity
        │   ├── data: velocity (rad/s)
        │   ├── starting_time: first interpolated time
        │   └── rate: 1000 Hz
        ├── TimeSeriesWheelAcceleration    # Derived acceleration
        │   ├── data: acceleration (rad/s^2)
        │   ├── starting_time: first interpolated time
        │   └── rate: 1000 Hz
        └── TimeIntervalsWheelMovement     # Detected movements
            ├── start_time: movement onsets
            ├── stop_time: movement offsets
            └── peak_amplitude: max displacement per movement
```

### NWB Types Used

| Data Stream | NWB Type | Rationale |
|-------------|----------|-----------|
| Position | `SpatialSeries` | Represents position in space (angular) |
| Velocity | `TimeSeries` | Generic time-varying signal |
| Acceleration | `TimeSeries` | Generic time-varying signal |
| Movements | `TimeIntervals` | Discrete temporal epochs with metadata |

## Data Analysis Applications

### Loading Wheel Data from NWB

```python
from pynwb import NWBHDF5IO

# Load NWB file
with NWBHDF5IO("session.nwb", "r") as io:
    nwbfile = io.read()

    # Access wheel processing module
    wheel_module = nwbfile.processing["wheel"]

    # Load position data
    position = wheel_module["SpatialSeriesWheelPosition"]
    pos_data = position.data[:]
    pos_times = position.timestamps[:]

    # Load velocity (regularly sampled)
    velocity = wheel_module["TimeSeriesWheelVelocity"]
    vel_data = velocity.data[:]
    vel_rate = velocity.rate  # 1000 Hz
    vel_start = velocity.starting_time

    # Load movement intervals
    movements = wheel_module["TimeIntervalsWheelMovement"].to_dataframe()
```

### Reaction Time Analysis

```python
import numpy as np

# Get first movement after stimulus onset for each trial
def get_reaction_times(trials_df, movements_df):
    """Calculate reaction times from stimulus to first movement."""
    reaction_times = []

    for _, trial in trials_df.iterrows():
        stim_time = trial["stimOn_times"]

        # Find first movement after stimulus
        post_stim_moves = movements_df[movements_df["start_time"] > stim_time]

        if len(post_stim_moves) > 0:
            first_move = post_stim_moves.iloc[0]["start_time"]
            reaction_times.append(first_move - stim_time)
        else:
            reaction_times.append(np.nan)

    return np.array(reaction_times)
```

### Movement Kinematics

```python
def analyze_movement_kinematics(movements_df, velocity_data, velocity_rate, velocity_start):
    """Extract kinematic features from wheel movements."""

    vel_times = np.arange(len(velocity_data)) / velocity_rate + velocity_start

    for _, move in movements_df.iterrows():
        # Find velocity during this movement
        mask = (vel_times >= move["start_time"]) & (vel_times <= move["stop_time"])
        move_velocity = velocity_data[mask]

        # Compute kinematics
        peak_velocity = np.max(np.abs(move_velocity))
        duration = move["stop_time"] - move["start_time"]
        amplitude = move["peak_amplitude"]

        yield {
            "peak_velocity": peak_velocity,
            "duration": duration,
            "amplitude": amplitude,
        }
```

### Wheel Position Aligned to Events

```python
def get_wheel_around_event(position, timestamps, event_time, window=(-0.5, 1.0)):
    """Extract wheel position aligned to an event."""

    mask = (timestamps >= event_time + window[0]) & (timestamps <= event_time + window[1])

    aligned_times = timestamps[mask] - event_time
    aligned_pos = position[mask] - position[mask][0]  # Zero at window start

    return aligned_times, aligned_pos
```

## Relationship to Other Data Streams

### Trials Data
- `firstMovement_times`: Time of first detected wheel movement after go cue
- `response_times`: Time when wheel crosses threshold position
- `choice`: Direction of wheel turn (left/right)

### Neural Data
- Wheel position/velocity can be used as continuous behavioral regressor
- Movement onsets aligned to neural activity for motor preparation analysis
- Reaction time variability correlates with neural state

### Video Data
- Wheel movements correlate with paw movements visible in video
- Used for quality control of behavioral annotations

## Technical Notes

### Interpolation for Velocity Estimation
The raw wheel position has irregular timestamps (event-driven sampling). For velocity and acceleration computation:
1. Position is interpolated to a regular 1000 Hz grid
2. An 8th order Butterworth lowpass filter is applied
3. Velocity is computed as the derivative
4. Acceleration is computed as the derivative of velocity

### Revision System
Wheel data uses the BWM revision system (`2025-05-06`). Some sessions have revision-tagged files while others use untagged versions. The ONE API's revision fallback mechanism handles this automatically.

### Data Quality Considerations
- Encoder noise can cause small spurious movements (filtered by minimum displacement threshold)
- Very fast movements may be undersampled in raw data (velocity interpolation helps)
- Some sessions may have encoder malfunctions resulting in missing data

## File Structure Summary

### Original IBL Data
```
alf/
├── wheel.position.npy           # Wheel angle (radians)
├── wheel.timestamps.npy         # Sample timestamps (seconds)
├── wheelMoves.intervals.npy     # Movement start/stop times (N x 2)
└── wheelMoves.peakAmplitude.npy # Peak amplitude per movement (N,)
```

### NWB Conversion Output
```
NWBFile
└── processing
    └── wheel                           # Wheel behavior module
        ├── SpatialSeriesWheelPosition  # Raw position + timestamps
        ├── TimeSeriesWheelVelocity     # 1000 Hz interpolated velocity
        ├── TimeSeriesWheelAcceleration # 1000 Hz interpolated acceleration
        └── TimeIntervalsWheelMovement  # Detected movement epochs
```

## Scientific Applications

The IBL wheel data enables:

1. **Decision-Making Studies**: Quantifying how sensory evidence is integrated into motor output
2. **Motor Control Research**: Understanding movement initiation and execution
3. **Reaction Time Analysis**: Characterizing sensory-motor transformation speed
4. **Confidence Studies**: Relating movement vigor to decision confidence
5. **Learning Studies**: Tracking behavioral changes across sessions
6. **Individual Differences**: Characterizing behavioral strategies across animals

The conversion to NWB format preserves all essential information while providing standardized access for computational analysis and data sharing across the neuroscience community.

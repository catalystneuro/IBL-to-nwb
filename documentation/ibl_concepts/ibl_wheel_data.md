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

### Position Extraction Algorithm

The IBL pipeline extracts wheel position from the raw TTL fronts using the `_rotary_encoder_positions_from_fronts()` function. Understanding this requires knowing what data the NIDQ actually records and how it's converted to angular position.

#### What NIDQ Records

The NIDQ does **not** record pulse durations or intervals. It records the **timestamp of each edge** (rising or falling) on both channels:

| Channel A edges | Channel B edges |
|-----------------|-----------------|
| t=0.001 (rise)  | t=0.0015 (rise) |
| t=0.002 (fall)  | t=0.0025 (fall) |
| t=0.003 (rise)  | t=0.0035 (rise) |
| ...             | ...             |

The pulse width (time between rise and fall on the same channel) is irrelevant for position calculation. We only need:
1. **When** each edge occurred (timestamp)
2. **Which channel** (A or B)
3. **Which direction** (rising or falling)

#### Only One Parameter Needed

The only hardware parameter required is the **number of ticks per revolution** (1024 for IBL encoders). Combined with X4 encoding, this gives 4096 counts per full rotation.

#### How X4 Encoding Calculates Position

Each edge (rising or falling) on either channel represents a fixed angular increment. The direction (+1 or -1) is determined by the phase relationship between channels at the moment of each edge:

```
Example: Clockwise rotation

Channel A:  ___/‾‾‾‾\____/‾‾‾‾\____
Channel B:  __/‾‾‾‾\____/‾‾‾‾\____

Time →           1  2  3  4  5  6  7  8
                 ↑  ↑  ↑  ↑  ↑  ↑  ↑  ↑
                 edges (events)

At edge 1 (A rises): B is LOW  → clockwise → count +1
At edge 2 (B rises): A is HIGH → clockwise → count +1
At edge 3 (A falls): B is HIGH → clockwise → count +1
At edge 4 (B falls): A is LOW  → clockwise → count +1
... and so on
```

For counter-clockwise rotation, the phase relationship reverses, so each edge gives -1 instead of +1.

#### The Decoding Algorithm

```python
# Inputs from NIDQ (what's actually recorded)
times_a = [0.001, 0.003, 0.005, ...]    # Timestamps of channel A edges
polarity_a = [+1, -1, +1, ...]          # Rising (+1) or falling (-1)
times_b = [0.002, 0.004, 0.006, ...]    # Timestamps of channel B edges
polarity_b = [+1, -1, +1, ...]

# Only parameter needed from hardware
ticks_per_revolution = 1024
counts_per_revolution = ticks_per_revolution * 4  # X4 encoding = 4096

def decode_quadrature_x4(times_a, polarity_a, times_b, polarity_b, ticks=1024):
    """
    Decode quadrature encoder using X4 encoding.

    Position starts at 0 and accumulates based on edge counts.
    Each edge represents 2*pi/4096 radians of rotation.
    """
    # Merge all edges and sort by time
    all_edges = merge_and_sort_by_time(times_a, polarity_a, times_b, polarity_b)

    cumulative_count = 0  # Start at position 0
    positions = []
    timestamps = []

    for edge in all_edges:
        # Direction lookup based on phase relationship
        # When channel A transitions, check state of channel B (and vice versa)
        direction = determine_direction_from_phase(edge)  # Returns +1 or -1

        cumulative_count += direction
        positions.append(cumulative_count)
        timestamps.append(edge.time)

    # Convert counts to radians
    position_radians = np.array(positions) * (2 * np.pi) / (ticks * 4)
    return np.array(timestamps), position_radians
```

#### Why Position is "Cumulative"

Position accumulates because:
- We start at 0 at session start
- Each edge adds +1 or -1 to the running count
- The wheel can rotate multiple full turns, so position accumulates beyond 2π
- Position is "unwrapped" - it doesn't reset at 360°

```
Example trace:
Time (s):     0      0.1    0.2    0.3    0.4    0.5
Counts:       0      +200   +480   +320   +120   -80   (cumulative)
Radians:      0      0.307  0.737  0.491  0.184  -0.123
                            ↑ mouse turned wheel right, then back left
```

#### Why Edge Timing Doesn't Matter for Resolution

The pulse width could be 1 microsecond or 100 milliseconds - each edge still represents the same angular increment (2π/4096 radians). This is why quadrature encoders work across a huge range of speeds: they count discrete angular steps, not time intervals.

**Resolution Calculation**:
- Base encoder: 1024 ticks/revolution
- X4 encoding: 4096 effective counts/revolution
- Angular resolution: 2π / 4096 = 0.00153 radians (~0.088 degrees)

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

**Description**: Detected discrete movement epochs extracted from continuous position. Each movement represents a period when the mouse actively turned the wheel, as opposed to the wheel being stationary.

**Data Files**:
- `alf/wheelMoves.intervals.npy` - Start and stop times of detected movements (N x 2 array)
- `alf/wheelMoves.peakAmplitude.npy` - Maximum displacement during each movement relative to onset position (N,)

**What wheelMoves Represents Behaviorally**:

```
Time -->
         |----movement 1----|     |--movement 2--|          |---movement 3---|
Position: ___/```````\______     _____/``\_______          ____/`````````\____
              ^onset  ^offset        ^onset^offset              ^onset    ^offset

intervals[0] = [onset_1, offset_1]    # Time boundaries of movement 1
intervals[1] = [onset_2, offset_2]    # Time boundaries of movement 2
intervals[2] = [onset_3, offset_3]    # Time boundaries of movement 3

peakAmplitude[0] = max displacement during movement 1 (relative to position at onset)
peakAmplitude[1] = max displacement during movement 2
peakAmplitude[2] = max displacement during movement 3
```

Each movement bout corresponds to a **behavioral decision** - typically the mouse turning the wheel to move a visual stimulus. The `peakAmplitude` indicates the vigor/extent of each movement.

**Movement Detection Algorithm** (applied to 1000 Hz interpolated position):
- **Minimum displacement** (`pos_thresh=8`): Position must change by at least 8 units within a 200ms sliding window to be considered moving
- **Time window** (`t_thresh=0.2`): 200ms sliding window for displacement detection
- **Minimum duration** (`min_dur=0.05`): Movements shorter than 50ms are discarded as noise
- **Merge threshold** (`min_gap=0.1`): Movements separated by less than 100ms are combined into a single movement bout
- **Onset refinement** (`pos_thresh_onset=1.5`): A lower threshold (1.5 units) is used to find the precise onset time within the detected movement window

### 3. Relationship Between wheel and wheelMoves

The `wheel` and `wheelMoves` objects are related but serve different purposes:

```
wheel (continuous):      Raw position trace with irregular timestamps
                         ___/```````\______/``\_______/`````````\____

wheelMoves (discrete):   Detected movement epochs derived from wheel
                         |----move 1----|  |--move 2--|  |---move 3---|
```

**How to use them together**:

```python
import numpy as np

# Load both objects
wheel = one.load_object(eid, 'wheel', collection='alf')
wheel_moves = one.load_object(eid, 'wheelMoves', collection='alf')

# Extract wheel position during a specific movement
move_idx = 0  # First movement
start_time, end_time = wheel_moves['intervals'][move_idx]

# Find wheel samples within this movement interval
mask = (wheel['timestamps'] >= start_time) & (wheel['timestamps'] <= end_time)
move_timestamps = wheel['timestamps'][mask]
move_position = wheel['position'][mask]

# Verify peak amplitude matches
onset_position = wheel['position'][wheel['timestamps'] >= start_time][0]
max_displacement = np.max(np.abs(move_position - onset_position))
# This should approximately equal wheel_moves['peakAmplitude'][move_idx]
```

**Key relationships**:
- `wheelMoves.intervals` times fall within the range of `wheel.timestamps`
- `wheelMoves.peakAmplitude` can be verified by examining `wheel.position` within each interval
- Gaps between movements in `wheelMoves` correspond to stationary periods in `wheel`

### 4. Derived Signals (Computed During Conversion)

**Velocity**:
- Computed from position interpolated at 1000 Hz
- 8th order lowpass Butterworth filter applied
- Units: rad/s

**Acceleration**:
- Computed from velocity
- Same filtering as velocity
- Units: rad/s^2

## IBL-to-NWB Conversion

Wheel data is converted using three specialized interfaces, each handling distinct data types with clear provenance:

### Interface: `WheelPositionInterface`

**Purpose**: Raw wheel position from quadrature encoder (event-driven, irregular timestamps)

**Data Requirements**:
```python
{
    "exact_files_options": {
        "standard": ["alf/wheel.position.npy", "alf/wheel.timestamps.npy"]
    }
}
```

**Processing**: None (raw data passthrough)

### Interface: `WheelMovementsInterface`

**Purpose**: Detected wheel movement epochs (pre-computed by IBL pipeline)

**Data Requirements**:
```python
{
    "exact_files_options": {
        "standard": ["alf/wheelMoves.intervals.npy", "alf/wheelMoves.peakAmplitude.npy"]
    }
}
```

**Processing**: None (pre-computed intervals)

### Interface: `WheelKinematicsInterface`

**Purpose**: Derived kinematics (interpolated position, velocity, acceleration)

**Data Requirements**:
```python
{
    "exact_files_options": {
        "standard": ["alf/wheel.position.npy", "alf/wheel.timestamps.npy"]
    }
}
```

**Processing Pipeline** (hardcoded IBL defaults):
1. Interpolate position to 1000 Hz (linear)
2. Apply 8th order Butterworth lowpass filter (20 Hz corner, zero-phase)
3. Compute velocity as derivative of filtered position
4. Compute acceleration as derivative of velocity

### NWB Output Structure

All three interfaces write to a dedicated `wheel` processing module:

```
NWBFile
└── processing
    └── wheel                           # Dedicated wheel module
        ├── WheelPosition               # From WheelPositionInterface (raw)
        │   ├── data: wheel positions (radians)
        │   ├── timestamps: irregular sample times
        │   └── reference_frame: "Initial angle at start..."
        ├── WheelMovement               # From WheelMovementsInterface
        │   ├── start_time: movement onsets
        │   ├── stop_time: movement offsets
        │   └── peak_amplitude: max displacement per movement
        ├── WheelPositionSmoothed       # From WheelKinematicsInterface
        │   ├── data: filtered position (radians)
        │   ├── starting_time: first interpolated time
        │   └── rate: 1000 Hz
        ├── WheelSmoothedVelocity               # From WheelKinematicsInterface
        │   ├── data: velocity (rad/s)
        │   ├── starting_time: first interpolated time
        │   └── rate: 1000 Hz
        └── WheelSmoothedAcceleration           # From WheelKinematicsInterface
            ├── data: acceleration (rad/s^2)
            ├── starting_time: first interpolated time
            └── rate: 1000 Hz
```

### NWB Types Used

| Data Stream | NWB Type | Interface | Rationale |
|-------------|----------|-----------|-----------|
| Raw Position | `SpatialSeries` | WheelPositionInterface | Angular position in space |
| Movements | `TimeIntervals` | WheelMovementsInterface | Discrete temporal epochs |
| Filtered Position | `SpatialSeries` | WheelKinematicsInterface | Processed angular position |
| Velocity | `TimeSeries` | WheelKinematicsInterface | Derived time-varying signal |
| Acceleration | `TimeSeries` | WheelKinematicsInterface | Derived time-varying signal |

## Data Analysis Applications

### Loading Wheel Data from NWB

```python
from pynwb import NWBHDF5IO

# Load NWB file
with NWBHDF5IO("session.nwb", "r") as io:
    nwbfile = io.read()

    # Access wheel processing module
    wheel_module = nwbfile.processing["wheel"]

    # Load raw position data (irregular timestamps)
    position = wheel_module["WheelPosition"]
    pos_data = position.data[:]
    pos_times = position.timestamps[:]

    # Load smoothed position (uniformly sampled at 1000 Hz)
    smoothed_pos = wheel_module["WheelPositionSmoothed"]
    smoothed_data = smoothed_pos.data[:]
    smoothed_rate = smoothed_pos.rate  # 1000 Hz

    # Load velocity (regularly sampled)
    velocity = wheel_module["WheelSmoothedVelocity"]
    vel_data = velocity.data[:]
    vel_rate = velocity.rate  # 1000 Hz
    vel_start = velocity.starting_time

    # Load movement intervals
    movements = wheel_module["WheelMovement"].to_dataframe()
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
1. Position is interpolated to a regular 1000 Hz grid using linear interpolation
2. An 8th order Butterworth lowpass filter (20 Hz corner frequency) is applied to the interpolated position
3. Velocity is computed as the derivative of the filtered position
4. Acceleration is computed as the derivative of velocity

### Butterworth Filter Details

The velocity computation uses a **20 Hz corner frequency** 8th order Butterworth lowpass filter:

- **Why 20 Hz?** Mouse behavioral movements are typically below 10-15 Hz. The 20 Hz cutoff preserves all behavioral signals while removing high-frequency encoder noise and jitter.
- **Why 8th order?** Higher order provides a steeper rolloff, more effectively separating signal from noise.
- **Zero-phase filtering**: Uses `scipy.signal.sosfiltfilt` which applies the filter forward and backward, eliminating phase distortion. This preserves precise movement timing.
- **Filter applied to position**: The filter is applied to interpolated position *before* differentiation, not to velocity after. This prevents noise amplification that would occur from differentiating noisy position data.

### Why Interpolation is Required

1. **Uniform sampling for filtering**: Digital filters like Butterworth assume uniform sampling. The filter coefficients are designed for a specific sampling rate.
2. **Correct differentiation**: Computing velocity as `np.diff(position)` requires uniform time steps, otherwise the derivative would be incorrect.
3. **1000 Hz rate**: Much higher than behavioral frequencies of interest, so no information is lost. One sample per millisecond provides sufficient temporal resolution.

### Linear Displacement Conversion

With a wheel diameter of 6.2 cm:
- 1 radian of wheel rotation = 3.1 cm linear displacement at the wheel surface
- Full rotation (2*pi radians) = 19.5 cm linear displacement

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
    └── wheel                    # Wheel behavior module
        ├── WheelPosition        # Raw position + irregular timestamps
        ├── WheelMovement        # Detected movement epochs
        ├── WheelPositionSmoothed# 1000 Hz interpolated + filtered position
        ├── WheelSmoothedVelocity        # 1000 Hz derived velocity
        └── WheelSmoothedAcceleration    # 1000 Hz derived acceleration
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

# ROI Motion Energy

ROI Motion Energy is a scalar behavioral metric derived from video recordings that quantifies movement within a specific region of interest (ROI). It provides a simple yet powerful proxy for animal movement without requiring explicit body part tracking.

## What It Measures

Motion energy quantifies total movement within a region of interest (ROI) by computing pixel intensity changes across video frames.

### Calculation Pipeline

The motion energy calculation (implemented in `ibllib/brainbox/video.py`) follows these steps:

1. **Frame differencing**: Compare frame N with frame N+2 (default offset of 2 frames)
2. **Euclidean norm**: For each pixel, compute `sqrt(diff^2)` (or for color: `sqrt(R_diff^2 + G_diff^2 + B_diff^2)`)
3. **Spatial summation**: Sum all pixel values across the ROI
4. **Min-max normalization**: Scale to [0, 1] range: `(value - min) / (max - min)`

```
# Per-pixel difference (grayscale)
pixel_diff[t] = sqrt((frame[t+2] - frame[t])^2)

# Motion energy for frame t
motion_energy[t] = normalize(sum(pixel_diff[t]) for all pixels in ROI)
```

**Key details:**
- **Frame offset (diff=2)**: Compares frame N with frame N+2, not consecutive frames. This reduces noise while capturing movement.
- **Euclidean distance**: Uses L2 norm (sqrt of squared differences), not raw squared differences.
- **Normalization**: Output is scaled to [0, 1] range, making values comparable across sessions.
- **Optional smoothing**: A 9x9 Gaussian blur can be applied (not used by default).

Any movement within the ROI (whisker twitches, grooming, fidgeting, breathing) contributes to higher motion energy values. Static frames produce near-zero values.

## Why Motion Energy Matters

### 1. Behavioral Covariate for Neural Analysis

Brain activity reflects both task-related processing and uninstructed movements. Motion energy allows researchers to:

- **Regress out movement-related neural activity** to isolate decision-related signals
- **Identify neurons encoding movement** vs. task variables
- **Control for behavioral state** (aroused/active vs. quiescent)

### 2. Simpler Than Pose Estimation

While pose estimation (Lightning Pose/DLC) tracks specific body parts, motion energy:

- Requires no model training
- Captures **all** movement in the region, including subtle motions that keypoint tracking might miss
- Is computationally cheaper to generate
- Provides a single scalar time series (easier to analyze)

### 3. Complementary to Other Behavioral Measures

Motion energy captures different information than:

- **Wheel position** - only measures the behavioral response, not uninstructed movements
- **Lick times** - discrete events, not continuous movement
- **Pose estimation** - tracks specific keypoints, may miss diffuse motion

## Camera Setup and ROI Placement

IBL uses three synchronized cameras:

| Camera | Resolution | Frame Rate | ROI Focus |
|--------|-----------|------------|-----------|
| Left | 1280x1024 | 60 Hz | Whisker pad (orofacial movements) |
| Right | 640x512 | 150 Hz | Whisker pad (symmetric view) |
| Body | 640x512 | 30 Hz | Mouse trunk (postural adjustments) |

The ROI is a fixed rectangular region placed over the whisker pad (for side cameras) or body (for body camera). The exact pixel coordinates are stored alongside the motion energy data.

## Data Structure

Motion energy data consists of three components:

1. **`ROIMotionEnergy.npy`** - Motion energy values (one per frame)
2. **`times.npy`** - Timestamps for each frame (synchronized to neural recording clock)
3. **`position.npy`** - ROI coordinates: `[width, height, x, y]` (top-left corner)

### ROI Position Caveat

Different video loading libraries may flip axes. The stored coordinates use a specific convention:

```python
# Original convention (as stored)
roi = frame[y:y+height, x:x+width]

# With cv2 in Python (axes flipped)
roi = frame[y:y+height, x:x+width]  # Same, but image may be transposed
```

Always verify the ROI placement visually when working with the raw video.

## Quality Control

Motion energy data inherits quality control from the source video:

- **PASS/WARNING** - Data included in NWB conversion
- **CRITICAL/FAIL** - Data excluded (unreliable motion energy due to video artifacts)

QC status is checked via the `bwm_qc.json` fixture before conversion.

## Availability in the BWM Dataset

| Camera | Available Sessions | Percentage |
|--------|-------------------|------------|
| Left | 371/459 | 80.8% |
| Right | 356/459 | 77.6% |
| Body | 183/459 | 39.9% |

Body camera has lower availability because it was added mid-project (February 2020).

## NWB Storage

In the NWB file, motion energy is stored as a `TimeSeries` in the `video` processing module:

```
/processing/video/
    TimeSeriesLeftMotionEnergy
    TimeSeriesRightMotionEnergy
    TimeSeriesBodyMotionEnergy
```

Each `TimeSeries` includes:
- `data` - Motion energy values (normalized to 0-1 range)
- `timestamps` - Frame times in seconds
- `unit` - "a.u." (arbitrary units, normalized)
- `description` - ROI dimensions and position

## Scientific Applications

### Brain-Wide Map Analysis

In the IBL Brain-Wide Map papers, motion energy is used to:

1. **Identify movement-encoding neurons** across 279 brain regions
2. **Separate task-related from movement-related variance** in neural activity
3. **Characterize uninstructed behaviors** that correlate with neural state

### Example Analysis

```python
import numpy as np
from pynwb import NWBHDF5IO

# Load motion energy from NWB
with NWBHDF5IO("session.nwb", "r") as io:
    nwbfile = io.read()
    left_me = nwbfile.processing["video"]["TimeSeriesLeftMotionEnergy"]

    motion_energy = left_me.data[:]
    timestamps = left_me.timestamps[:]

# Correlate with neural activity
# (after aligning to common time base)
```

## Related Documentation

- [Pupil Tracking](pupil_tracking.md) - Pupil diameter measurements from video
- [Lick Detection](lick_detection.md) - Lick event timestamps from tongue pose estimation
- [Pose Estimation](../conversion/conversion_modalities.md) - Keypoint tracking for specific body parts
- [Raw Video](../conversion/conversion_modalities.md) - Source video files

## References

- [IBL Video Analysis Repository](https://github.com/int-brain-lab/iblvideo)
- [Brain-Wide Map Dataset](https://doi.org/10.1038/s41586-023-06417-4)
- [IBL Data Documentation](https://docs.internationalbrainlab.org/public_docs/public_introduction.html)

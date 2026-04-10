# Pupil Tracking

Pupil tracking provides continuous measurements of pupil diameter from video recordings of the mouse eye. Pupil diameter is a well-established indicator of arousal, attention, and cognitive state, making it a valuable covariate for neural data analysis.

## Scientific Purpose

**Why Pupil Diameter Matters:**

- **Arousal and Attention**: Pupil diameter correlates with noradrenergic locus coeruleus activity and reflects global brain state
- **Cognitive Load**: Pupil dilation increases with task difficulty and mental effort
- **Decision Confidence**: Pupil dynamics relate to uncertainty and decision-making processes
- **Behavioral State**: Distinguishes engaged vs. disengaged states during the task
- **Movement Covariate**: Pupil changes correlate with uninstructed movements and should be regressed from neural signals

## Camera Setup

IBL uses synchronized video cameras that capture the mouse face during behavior:

| Camera | Resolution | Frame Rate | Eye Coverage |
|--------|-----------|------------|--------------|
| Left | 1280x1024 | 60 Hz | Primary eye view |
| Right | 640x512 | 150 Hz | Secondary eye view |
| Body | 640x512 | 30 Hz | No eye coverage |

Only left and right cameras capture pupil data. The body camera does not image the eye.

## Measurement Method

### Keypoint Tracking

Pupil diameter is estimated using DeepLabCut (DLC) pose estimation trained on IBL video data. The model tracks multiple points around the pupil boundary:

- Top of pupil
- Bottom of pupil
- Left edge of pupil
- Right edge of pupil
- Additional circular fit points

### Diameter Computation

Multiple diameter estimates are computed from the tracked keypoints:

1. **Vertical diameter (d1)**: Distance from top to bottom points
2. **Horizontal diameter (d2)**: Distance from left to right points
3. **Circular fit diameters**: Assuming the pupil is circular, estimate diameter from other point pairs

The final **raw pupil diameter** is the **median** of these multiple estimates, providing robustness against individual keypoint tracking errors.

### Smoothed Diameter

A **smoothed version** is also provided:
- Interpolates over missing/low-confidence frames
- Applies temporal smoothing to reduce frame-to-frame noise
- Useful for analyses where smooth trajectories are preferred

## Data Structure

Pupil data is stored in the ALF format:

| File | Description |
|------|-------------|
| `alf/_ibl_{camera}.features.pqt` | Parquet table with pupil features |
| `alf/_ibl_{camera}.times.npy` | Timestamps for each frame |

The features parquet file contains columns including:
- `pupilDiameter_raw`: Median diameter estimate (pixels)
- `pupilDiameter_smooth`: Smoothed and interpolated diameter (pixels)

### Units

Pupil diameter is measured in **pixels**. The absolute pixel size depends on camera resolution and distance to the eye, but relative changes within a session are meaningful for tracking arousal dynamics.

## Quality Control

Pupil tracking quality depends on video quality. Sessions are filtered based on video QC status from the `bwm_qc.json` fixture:

| QC Status | Included in NWB |
|-----------|-----------------|
| PASS | Yes |
| WARNING | Yes |
| CRITICAL | No |
| FAIL | No |

Sessions with CRITICAL or FAIL video QC are excluded to ensure reliable pupil measurements.

## Availability in the BWM Dataset

| Camera | Available Sessions | Percentage |
|--------|-------------------|------------|
| Left | 371/459 | 80.8% |
| Right | 356/459 | 77.6% |

Availability is limited by video quality issues, missing recordings, or DLC tracking failures.

## NWB Storage

In the NWB file, pupil data is stored in a dedicated processing module:

```
/processing/pupil/
    LeftPupilDiameter          # Raw diameter from left camera
    LeftPupilDiameterSmoothed  # Smoothed diameter from left camera
    RightPupilDiameter         # Raw diameter from right camera
    RightPupilDiameterSmoothed # Smoothed diameter from right camera
```

Each is stored as a `TimeSeries` with:
- `data`: Pupil diameter values
- `timestamps`: Frame times in seconds (synchronized to session clock)
- `unit`: "px" (pixels)

## Loading Pupil Data from NWB

```python
from pynwb import NWBHDF5IO

with NWBHDF5IO("session.nwb", "r") as io:
    nwbfile = io.read()

    # Access pupil processing module
    pupil_module = nwbfile.processing["pupil"]

    # Load left camera pupil diameter
    left_pupil = pupil_module["LeftPupilDiameter"]
    diameter = left_pupil.data[:]
    timestamps = left_pupil.timestamps[:]

    # Load smoothed version
    left_smooth = pupil_module["LeftPupilDiameterSmoothed"]
    smooth_diameter = left_smooth.data[:]
```

## Scientific Applications

### Arousal Analysis

```python
import numpy as np

# Compute z-scored pupil diameter for cross-session comparison
pupil_zscore = (diameter - np.nanmean(diameter)) / np.nanstd(diameter)

# Identify high vs. low arousal periods
high_arousal = pupil_zscore > 1.0
low_arousal = pupil_zscore < -1.0
```

### Trial-Aligned Pupil Responses

```python
def get_pupil_around_event(pupil_data, pupil_times, event_time, window=(-0.5, 2.0)):
    """Extract pupil diameter aligned to an event."""
    mask = (pupil_times >= event_time + window[0]) & (pupil_times <= event_time + window[1])
    aligned_times = pupil_times[mask] - event_time
    aligned_pupil = pupil_data[mask]
    return aligned_times, aligned_pupil

# Align pupil to stimulus onset for each trial
for stim_time in trials_df["stimOn_times"]:
    t, p = get_pupil_around_event(diameter, timestamps, stim_time)
    # Analyze pupil dilation response...
```

### Neural Correlation

Pupil diameter can be used as a regressor to separate arousal-related neural activity from task-related signals:

```python
from sklearn.linear_model import LinearRegression

# Interpolate pupil to match neural sampling
pupil_interp = np.interp(neural_times, timestamps, diameter)

# Regress pupil from neural activity
model = LinearRegression()
model.fit(pupil_interp.reshape(-1, 1), neural_activity)
residual_activity = neural_activity - model.predict(pupil_interp.reshape(-1, 1))
```

## Related Documentation

- [ROI Motion Energy](roi_motion_energy.md) - Another video-derived behavioral metric
- [Pose Estimation](../conversion/conversion_modalities.md) - Full body pose tracking
- [Synchronization](synchronization.md) - How video timestamps align with neural data

## References

- [IBL Video Processing](https://github.com/int-brain-lab/iblvideo)
- [DeepLabCut](http://www.mackenziemathislab.org/deeplabcut)
- [Brain-Wide Map Dataset](https://doi.org/10.1038/s41586-023-06417-4)

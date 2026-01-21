# Lick Detection

Lick detection provides timestamps of individual licking events during the behavioral task. Licks are detected from video-based tongue pose estimation, capturing the consummatory behavior when mice receive water rewards.

## Scientific Purpose

**Why Lick Data Matters:**

- **Reward Consumption**: Licking indicates when the animal is actively consuming the water reward
- **Behavioral State**: Lick patterns reflect motivation, satiety, and engagement with the task
- **Reward Timing Analysis**: Relates reward delivery to neural activity and behavior
- **Motor Output**: Licking involves coordinated orofacial movements with distinct neural correlates
- **Quality Control**: Lick patterns can validate trial outcomes and detect behavioral anomalies

## Detection Method

### Tongue Pose Estimation

Lick events are detected using **Lightning Pose** (formerly DLC-based) tracking of tongue landmarks from video. The model tracks four tongue endpoints:

- `tongue_end_l_x`, `tongue_end_l_y` (left tongue tip)
- `tongue_end_r_x`, `tongue_end_r_y` (right tongue tip)

### Detection Algorithm

The algorithm identifies frames where the tongue moves significantly:

1. **Compute frame-to-frame differences** for each tongue coordinate
2. **Calculate threshold**: `threshold = std(diff) / 4` for each coordinate
3. **Mark lick events**: Frames where any coordinate changes exceed the threshold
4. **Merge cameras**: If both left and right camera data exist, combine detected licks

```python
# Simplified algorithm (actual implementation in IBL pipeline)
def detect_licks(tongue_coords, timestamps):
    """
    Detect licks from tongue position changes.

    Parameters
    ----------
    tongue_coords : dict
        Contains tongue_end_l_x, tongue_end_l_y, tongue_end_r_x, tongue_end_r_y
    timestamps : array
        Frame timestamps
    """
    lick_frames = []

    for coord_name in ['tongue_end_l_x', 'tongue_end_l_y',
                       'tongue_end_r_x', 'tongue_end_r_y']:
        coord = tongue_coords[coord_name]
        diff = np.diff(coord)
        threshold = np.std(diff) / 4

        # Frames with large tongue movement
        lick_idx = np.where(np.abs(diff) > threshold)[0]
        lick_frames.extend(lick_idx)

    # Unique frames, sorted by time
    lick_frames = np.unique(lick_frames)
    lick_times = timestamps[lick_frames]

    return lick_times
```

### Why This Method Works

- **Movement-based detection**: Captures the rapid tongue protrusion during licking
- **Adaptive threshold**: `std(diff)/4` adapts to the signal quality of each session
- **Multi-coordinate**: Using all four coordinates increases sensitivity
- **Camera fusion**: Combining left and right views improves coverage

## Data Structure

Lick data is stored as a simple timestamp array in ALF format:

| File | Description |
|------|-------------|
| `alf/licks.times.npy` | Array of lick event timestamps (seconds) |

Each timestamp represents a single detected lick event.

## Relationship to Trials

In the IBL task, water reward delivery is **automatic** and **not contingent on licking**:

- Correct responses trigger automatic water delivery via solenoid
- Licking is the animal's response to water availability
- Lick times typically follow reward delivery by ~100-300 ms
- Some anticipatory licking may occur before reward

This means lick data captures **consummatory behavior**, not the decision itself.

## Quality Considerations

Lick detection quality depends on:

1. **Video quality**: Clear view of the tongue required
2. **Pose estimation accuracy**: Lightning Pose must track tongue reliably
3. **Lighting conditions**: Consistent illumination improves tracking
4. **Animal behavior**: Some mice lick more vigorously than others

Sessions with poor video quality may have incomplete or noisy lick detection.

## Availability in the BWM Dataset

| Metric | Value |
|--------|-------|
| Available Sessions | 443/459 |
| Availability | 96.5% |

High availability because lick detection only requires the side camera video and pose estimation output.

## NWB Storage

In the NWB file, lick events are stored using the `ndx-events` extension:

```
/processing/lick_times/
    EventsLickTimes    # Point events with timestamps only
```

The `Events` object contains:
- `timestamps`: Lick event times in seconds (session clock)
- `description`: Detection algorithm details

### Why Events Type

Licks are **point events** (discrete timestamps without duration or amplitude), making the `ndx_events.Events` type appropriate. This differs from continuous time series like pupil diameter.

## Loading Lick Data from NWB

```python
from pynwb import NWBHDF5IO

with NWBHDF5IO("session.nwb", "r") as io:
    nwbfile = io.read()

    # Access lick times
    lick_module = nwbfile.processing["lick_times"]
    lick_events = lick_module["EventsLickTimes"]

    # Get lick timestamps
    lick_times = lick_events.timestamps[:]

    print(f"Total licks detected: {len(lick_times)}")
```

## Scientific Applications

### Lick Rate Analysis

```python
import numpy as np

def compute_lick_rate(lick_times, bin_size=0.1):
    """Compute lick rate over time."""
    bins = np.arange(lick_times.min(), lick_times.max(), bin_size)
    lick_counts, _ = np.histogram(lick_times, bins=bins)
    lick_rate = lick_counts / bin_size  # licks per second
    bin_centers = bins[:-1] + bin_size / 2
    return bin_centers, lick_rate

times, rate = compute_lick_rate(lick_times)
```

### Trial-Aligned Lick Rasters

```python
def get_licks_around_event(lick_times, event_time, window=(-0.5, 2.0)):
    """Get licks relative to an event."""
    mask = (lick_times >= event_time + window[0]) & (lick_times <= event_time + window[1])
    return lick_times[mask] - event_time

# Create lick raster aligned to reward delivery
for trial_idx, reward_time in enumerate(trials_df["feedback_times"]):
    if trials_df["feedbackType"].iloc[trial_idx] == 1:  # Correct trials only
        aligned_licks = get_licks_around_event(lick_times, reward_time)
        # Plot as raster...
```

### Lick-Neural Correlation

```python
# Compute peri-lick time histogram (PLTH) for neural activity
def compute_plth(spike_times, lick_times, window=(-0.2, 0.5), bin_size=0.01):
    """Compute spike rate aligned to lick events."""
    bins = np.arange(window[0], window[1] + bin_size, bin_size)
    all_counts = []

    for lick_time in lick_times:
        aligned_spikes = spike_times - lick_time
        counts, _ = np.histogram(aligned_spikes, bins=bins)
        all_counts.append(counts)

    mean_rate = np.mean(all_counts, axis=0) / bin_size
    return bins[:-1] + bin_size/2, mean_rate
```

### Consumption Latency

```python
def compute_consumption_latency(trials_df, lick_times):
    """Time from reward to first lick for correct trials."""
    latencies = []

    for _, trial in trials_df.iterrows():
        if trial["feedbackType"] == 1:  # Correct trial
            reward_time = trial["feedback_times"]

            # Find first lick after reward
            post_reward_licks = lick_times[lick_times > reward_time]
            if len(post_reward_licks) > 0:
                first_lick = post_reward_licks[0]
                latencies.append(first_lick - reward_time)

    return np.array(latencies)
```

## Related Documentation

- [Pupil Tracking](pupil_tracking.md) - Another video-derived behavioral metric
- [ROI Motion Energy](roi_motion_energy.md) - Movement quantification from video
- [Trials Interface](../conversion/trials_interface.md) - Trial structure including reward times
- [Pose Estimation](../conversion/conversion_modalities.md) - Full pose tracking from video

## References

- [Lightning Pose](https://github.com/danbider/lightning-pose)
- [IBL Video Processing](https://github.com/int-brain-lab/iblvideo)
- [Brain-Wide Map Dataset](https://doi.org/10.1038/s41586-023-06417-4)

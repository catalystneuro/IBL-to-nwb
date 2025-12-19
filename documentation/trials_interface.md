# IBL Trials Interface Documentation

This document provides comprehensive documentation for the `BrainwideMapTrialsInterface`, which handles the conversion of IBL behavioral trial data to NWB format.

## Table of Contents

1. [Overview](#overview)
2. [The IBL Behavioral Task](#the-ibl-behavioral-task)
   - [Task Description](#task-description)
   - [Visual Stimulus](#visual-stimulus)
   - [Trial Structure and Timing](#trial-structure-and-timing)
   - [Task Variants](#task-variants)
3. [Trial Columns Reference](#trial-columns-reference)
4. [Data Extraction with ibllib](#data-extraction-with-ibllib)
5. [Interface Implementation](#interface-implementation)
6. [References](#references)

---

## Overview

The `BrainwideMapTrialsInterface` converts behavioral trial data from IBL experiments into the NWB trials table format. This interface handles the standardized decision-making task used across all IBL laboratories, ensuring consistent representation of behavioral events and their timing.

**Key characteristics:**
- Adds 15 columns to the NWB trials table
- Supports both BWM parquet format and legacy NumPy file formats
- Uses revision `2025-05-06` for Brain-Wide Map standard data
- Available for 100% of the 459 BWM sessions

---

## The IBL Behavioral Task

### Task Description

The IBL developed a standardized two-alternative forced-choice perceptual detection task to study decision-making across multiple laboratories. In this task:

1. **Goal**: Mice detect the presence of a visual grating (Gabor patch) appearing in their left or right visual field
2. **Response**: Mice turn a steering wheel to move the stimulus to the center of the screen
3. **Outcome**: Correct responses are rewarded with sugar water; incorrect responses trigger a white noise burst and timeout

The task is designed to probe three key aspects of decision-making:
- **Visual processing**: Detection of stimuli at varying contrast levels
- **Experience-based learning**: Integration of past successes and failures
- **Probabilistic reasoning**: Estimation of stimulus location likelihood based on block statistics

### Visual Stimulus

The visual stimulus is a Gabor patch with the following parameters:

#### Fixed Parameters (Same for All Trials)

| Parameter | Value |
|-----------|-------|
| Type | Gabor patch (sinusoidal grating) |
| Spatial frequency | 0.1 cycles/degree |
| Orientation | Vertical |
| Size (sigma) | ~7 degrees visual angle |
| Screen distance | 8 cm from animal |
| Visual coverage | ~102 degrees azimuth |

#### Per-Trial Parameters

| Parameter | Values | Data Availability |
|-----------|--------|-------------------|
| **Contrast** | 0%, 6.25%, 12.5%, 25%, 50%, 100% | Stored as `contrastLeft`/`contrastRight` in database |
| **Position** | -35 or +35 degrees azimuth | Not saved to database (derivable from contrast columns) |
| **Phase** | 0 to 2*pi radians (random) | Not saved to database (in raw Bpod data only) |

The **phase** parameter determines where in the sine wave cycle the grating pattern starts. It is randomized per trial to prevent the mouse from learning to detect the stimulus based on a specific spatial pattern at the expected location. While phase is extracted during IBL's processing pipeline, it is not saved to the database as it is primarily used for experimental control rather than analysis.

**Contrast levels** used in the task:
- 100% (easy)
- 50%
- 25%
- 12.5%
- 6.25% (difficult)
- 0% (catch trials - no stimulus)

When a stimulus appears on one side, the opposite side has 0% contrast. On catch trials, both sides have NaN contrast values.

### Trial Structure and Timing

Each trial follows this sequence:

```
[Quiescence Period] -> [Go Cue + Stimulus Onset] -> [Response Window] -> [Feedback] -> [ITI]
```

#### Detailed Timing Parameters

| Event | Duration/Timing |
|-------|-----------------|
| **Quiescence period** | 400-700 ms (exponential distribution, mean 550 ms) |
| **Go cue tone** | 100 ms, 5 kHz sine wave with 10 ms ramp |
| **Response window** | Up to 60 seconds from stimulus onset |
| **Response threshold** | Wheel movement equivalent to +/- 35 degrees azimuth |
| **Correct feedback** | Stimulus held at center for 1 second, reward delivered |
| **Incorrect feedback** | 500 ms white noise burst |
| **ITI after correct** | 1 second (stimulus at center) |
| **ITI after incorrect** | 2 seconds (timeout) |

#### Reward Parameters

| Parameter | Value |
|-----------|-------|
| Reward type | 10% sucrose solution |
| Initial volume | 3 uL |
| After 200+ trials | Progressively reduced to 1.5 uL |
| Delivery | Automatic, not contingent on licking |

#### Wheel Parameters

| Parameter | Value |
|-----------|-------|
| Initial gain | 8 degrees/mm |
| After 200+ trials | 4 degrees/mm |
| Movement threshold | >= 0.1 radians for first movement detection |

### Task Variants

The IBL uses two main task variants:

#### 1. trainingChoiceWorld (Basic Task)

- **Stimulus probability**: 50% left, 50% right (symmetric)
- **Purpose**: Initial training and basic decision-making assessment
- **Repeat trials**: On incorrect responses, trials may repeat with probability based on recent performance (N(bias, 4) where bias is calculated from last 10 trials)

#### 2. biasedChoiceWorld (Full Task)

- **Block structure**: Asymmetric stimulus probabilities that change across blocks
- **Probability values**: 20%, 50%, or 80% left (complementary right)
- **Block lengths**: Geometric distribution with mean 51 trials, truncated to 20-100 trials
- **Session start**: 90 trials at 50:50 probability, then alternating blocks

This variant tests the ability of mice to incorporate prior probability information into their decisions.

---

## Trial Columns Reference

The interface adds the following 17 columns to the NWB trials table:

### Temporal Columns

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `start_time` | `intervals_0` | The beginning of the trial (seconds from session start) |
| `stop_time` | `intervals_1` | The end of the trial (seconds from session start) |
| `quiescence_period` | `quiescencePeriod` | Required duration (seconds) the mouse must hold the wheel still before stimulus presentation. Sampled from exponential distribution (400-700ms, mean ~550ms). If wheel moves during this period, the timer resets. Relationship: `gabor_stimulus_onset_time` ≈ `start_time` + `quiescence_period` |

### Event Timing Columns (Chronological Order)

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `gabor_stimulus_onset_time` | `stimOn_times` | Time when the visual stimulus (Gabor patch) appears on screen, detected by photodiode. Coincides with auditory go cue |
| `auditory_cue_time` | `goCue_times` | Time of the auditory go cue (100ms, 5kHz tone) signaling the mouse may respond. Presented simultaneously with visual stimulus |
| `wheel_movement_onset_time` | `firstMovement_times` | Time of first detected wheel movement (>= 0.1 radians threshold) after go cue |
| `choice_registration_time` | `response_times` | Time when the mouse's choice was registered: either wheel movement reached the +/-35 degree threshold, or 60-second timeout elapsed |
| `feedback_time` | `feedback_times` | Time of feedback delivery: water reward for correct responses, or white noise pulse + 2-second timeout for incorrect responses |
| `gabor_stimulus_offset_time` | `stimOff_times` | Time when the Gabor patch disappears from screen, recorded by external photodiode |

### Stimulus Columns

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `gabor_stimulus_contrast` | computed | Contrast of the Gabor patch as a percentage (0, 6.25, 12.5, 25, or 100). Uniformly sampled across trials. At 0% contrast (no visible stimulus), mice can still perform above chance using block probability prior. Computed from `contrastLeft`/`contrastRight` |
| `gabor_stimulus_side` | computed | Side where stimulus was assigned: `"left"` or `"right"`. Even at 0% contrast (invisible), trials are assigned a correct side based on block probability, allowing mice to use prior information. Computed from `contrastLeft`/`contrastRight` |
| `probability_left` | `probabilityLeft` | Block prior probability for stimulus on left side. After initial 90 unbiased trials (0.5), blocks alternate between 0.2 (right-biased) and 0.8 (left-biased). Block lengths: 20-100 trials from truncated geometric distribution (mean 51). Block changes are not cued |
| `block_index` | computed | Zero-indexed block number. Increments each time `probability_left` changes. Block 0 is typically the initial unbiased block (~90 trials at 0.5 probability). Computed from `probabilityLeft` |
| `block_type` | computed | Block type based on stimulus probability bias: `"unbiased"` (probability_left=0.5), `"left_block"` (probability_left=0.8, stimulus 80% likely on left), or `"right_block"` (probability_left=0.2, stimulus 80% likely on right). Computed from `probabilityLeft` |

### Response and Outcome Columns

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `mouse_wheel_choice` | `choice` | Mouse's response: `"left"` (CCW wheel turn moving stimulus rightward), `"right"` (CW wheel turn moving stimulus leftward), or `"no_go"` (no response within 60s timeout). Transformed from IBL's -1/0/+1 encoding |
| `is_mouse_rewarded` | `feedbackType` | Whether the mouse received a water reward (`True`) or negative feedback consisting of white noise pulse and 2-second timeout (`False`). Transformed from IBL's +1/-1 encoding |
| `reward_volume_uL` | `rewardVolume` | Volume of water reward in microliters (0 for incorrect/timeout trials)

### NOT Available in Database (Extracted but Not Saved)

The following parameters are extracted from Bpod raw data during IBL's pipeline but are **not saved to the database**:

| Parameter | Description | Why Not Saved |
|-----------|-------------|---------------|
| `phase` | Spatial phase of the Gabor sinusoid (0-2*pi radians) | Random value for experimental control; rarely needed for analysis |
| `position` | Stimulus position (-35 or +35 degrees azimuth) | Redundant with `contrastLeft`/`contrastRight` columns |

These parameters exist in the raw Bpod data files but would require re-extraction from `_iblrig_taskData.raw.jsonable` to access. The extraction code in `ibllib` sets `save_names = None` for these fields, meaning they are computed but discarded.

**To recover phase/position from raw data:**
```python
from ibllib.io.extractors.training_trials import PhasePosQuiescence
from ibllib.io import raw_data_loaders as raw

# Load raw Bpod data
bpod_trials = raw.load_data(session_path)
settings = raw.load_settings(session_path)

# Extract (requires local raw data, not available via ONE for most sessions)
extractor = PhasePosQuiescence(session_path, bpod_trials=bpod_trials, settings=settings)
phase, position, quiescence = extractor.extract()
```

---

## Data Extraction with ibllib

### Primary Extraction Method

The interface uses `SessionLoader` from `brainbox.io.one` to load trial data:

```python
from brainbox.io.one import SessionLoader
from one.api import ONE

one = ONE()
session_loader = SessionLoader(one=one, eid=session_id, revision="2025-05-06")
session_loader.load_trials()
trials = session_loader.trials  # Returns pandas DataFrame
```

### Data Formats

The interface supports two data formats:

#### BWM Format (Preferred)
- **File**: `alf/trials.table.pqt`
- **Format**: Consolidated Parquet table containing all trial columns
- **Advantages**: Single file, faster loading, standardized column names

#### Legacy Format
Individual NumPy files for each column:
- `alf/trials.intervals.npy`
- `alf/trials.choice.npy`
- `alf/trials.feedbackType.npy`
- `alf/trials.rewardVolume.npy`
- `alf/trials.contrastLeft.npy`
- `alf/trials.contrastRight.npy`
- `alf/trials.probabilityLeft.npy`
- `alf/trials.feedback_times.npy`
- `alf/trials.response_times.npy`
- `alf/trials.stimOff_times.npy`
- `alf/trials.stimOn_times.npy`
- `alf/trials.goCue_times.npy`
- `alf/trials.firstMovement_times.npy`

The `SessionLoader` automatically detects and handles both formats.

### Revision System

IBL uses a revision system for processed data. The trials interface uses revision `2025-05-06`, which is the Brain-Wide Map standard revision. This ensures:
- Consistent data processing across all sessions
- Reproducible analyses
- Quality-controlled event timing extraction

---

## Interface Implementation

### Class Definition

```python
class BrainwideMapTrialsInterface(BaseIBLDataInterface):
    """Interface for trial behavioral data (revision-dependent processed data)."""

    REVISION: str | None = "2025-05-06"  # BWM standard revision
```

**Source file**: [_brainwide_map_trials_interface.py](../IBL-to-nwb/src/ibl_to_nwb/datainterfaces/_brainwide_map_trials_interface.py)

### Key Methods

#### `get_data_requirements()`
Declares the exact files needed for trials data, supporting both BWM and legacy formats.

#### `download_data()`
Downloads trials data using `SessionLoader.load_trials()`. Automatically handles format detection and caching.

#### `add_to_nwbfile()`
Adds the trials table to the NWB file using `pynwb.epoch.TimeIntervals`. Supports `stub_test=True` for quick testing with limited trials.

### Usage Example

```python
from one.api import ONE
from ibl_to_nwb.datainterfaces import BrainwideMapTrialsInterface

one = ONE()
session_id = "a]session_eid_here"

# Create interface
trials_interface = BrainwideMapTrialsInterface(one=one, session=session_id)

# Download data
trials_interface.download_data(one=one, eid=session_id)

# Add to NWB file
nwbfile = ...  # Your NWBFile instance
metadata = trials_interface.get_metadata()
trials_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)
```

### Stub Testing

For quick testing without loading all trials:

```python
trials_interface.add_to_nwbfile(
    nwbfile=nwbfile,
    metadata=metadata,
    stub_test=True,
    stub_trials=10  # Only first 10 trials
)
```

---

## References

### Primary Publications

1. **Task Protocol**: International Brain Laboratory, et al. "Standardized and reproducible measurement of decision-making in mice." *eLife* 10 (2021): e63711.
   - DOI: [10.7554/eLife.63711](https://doi.org/10.7554/eLife.63711)
   - Full task protocol in Appendix 2

2. **Brain-Wide Map**: International Brain Laboratory, et al. "Brain-wide map of neural activity during a task." (2020).
   - DOI: [10.1101/2020.01.17.909838](https://doi.org/10.1101/2020.01.17.909838)

### Data Resources

- **IBL Data Portal**: [data.internationalbrainlab.org](https://data.internationalbrainlab.org)
- **FigShare Dataset**: [10.6084/m9.figshare.21400815.v6](https://doi.org/10.6084/m9.figshare.21400815.v6)

### Software Documentation

- **ONE API**: [int-brain-lab.github.io/ONE](https://int-brain-lab.github.io/ONE/)
- **ibllib**: [int-brain-lab.github.io/iblenv](https://int-brain-lab.github.io/iblenv/)
- **NeuroConv**: [neuroconv.readthedocs.io](https://neuroconv.readthedocs.io/)

---

## Appendix: Column Value Interpretations

### mouse_wheel_choice Values
| Value | Meaning | Wheel Direction | Stimulus Movement |
|-------|---------|-----------------|-------------------|
| `"left"` | Left choice | Counter-clockwise | Stimulus moves right |
| `"right"` | Right choice | Clockwise | Stimulus moves left |
| `"no_go"` | Timeout | No movement to threshold | N/A |

### is_mouse_rewarded Values
| Value | Meaning | Consequence |
|-------|---------|-------------|
| `True` | Correct response | Sugar water reward delivered |
| `False` | Incorrect response or timeout | White noise burst, 2s timeout |

### probability_left Values (biasedChoiceWorld)
| Value | Block Type | Stimulus More Likely On |
|-------|------------|------------------------|
| 0.2 | Right-biased block | Right side (80%) |
| 0.5 | Neutral block | Equal (50/50) |
| 0.8 | Left-biased block | Left side (80%) |

### gabor_stimulus_side and gabor_stimulus_contrast Interpretation
| gabor_stimulus_side | gabor_stimulus_contrast | Trial Type |
|---------------------|-------------------------------------|------------|
| `"left"` | 6.25 - 100 | Left stimulus trial (visible) |
| `"right"` | 6.25 - 100 | Right stimulus trial (visible) |
| `"left"` | 0 | 0% contrast trial assigned to left (invisible, but mouse can use block prior) |
| `"right"` | 0 | 0% contrast trial assigned to right (invisible, but mouse can use block prior) |

---

## Tidy Data Format Implementation

The trials table follows [tidy data principles](https://vita.had.co.nz/papers/tidy-data.pdf) (Wickham, 2014) to make the data more self-documenting, easier to analyze, and aligned with best practices for tabular data.

### Design Rationale

#### Self-Documenting Column Names

Column names are designed to be understandable without consulting documentation:

| Column | Rationale |
|--------|-----------|
| `quiescence_period` | Clear that this is a duration (period), not a timestamp. Relates to other columns: `gabor_stimulus_onset_time` ≈ `start_time` + `quiescence_period` |
| `gabor_stimulus_onset_time` | Specifies stimulus type (Gabor) and event (onset) |
| `auditory_cue_time` | Explicit that cue is auditory (vs visual) |
| `wheel_movement_onset_time` | Specifies wheel (the response mechanism) and onset |
| `choice_registration_time` | When choice was registered by the system |
| `gabor_stimulus_offset_time` | Specifies stimulus type (Gabor) and event (offset) |
| `gabor_stimulus_contrast` | Specifies the stimulus type (Gabor patch) and includes units (percentage) |
| `gabor_stimulus_side` | Consistent naming with other gabor_stimulus_* columns |
| `mouse_wheel_choice` | Explicit that this is the mouse's choice |
| `is_mouse_rewarded` | Boolean for easy filtering; outcome-focused |
| `reward_volume_uL` | Includes units in the name |

#### Categorical String Values

String and boolean values replace numeric encodings for clarity:

| IBL Encoding | NWB Value | Benefit |
|--------------|-----------|---------|
| choice: -1/0/+1 | `"left"`/`"no_go"`/`"right"` | Self-documenting queries |
| feedbackType: -1/+1 | `True`/`False` | Direct boolean filtering |

#### Tidy Contrast Representation

The original IBL format uses two columns (`contrastLeft`, `contrastRight`) where one is always 0 or both are NaN. This violates the tidy data principle that each variable should form a column.

**IBL format** (redundant):
| contrastLeft | contrastRight | Meaning |
|--------------|---------------|---------|
| 0.25 | 0 | Left stimulus at 25% |
| 0 | 1.0 | Right stimulus at 100% |
| 0 | 0 | 0% contrast trial (assigned side depends on which column was set) |

**NWB format** (tidy):
| gabor_stimulus_contrast | gabor_stimulus_side | Meaning |
|------------------------------------|---------------------|---------|
| 25 | `"left"` | Left stimulus at 25% |
| 100 | `"right"` | Right stimulus at 100% |
| 0 | `"left"` or `"right"` | 0% contrast trial (invisible, but assigned a correct side based on block probability) |

#### Chronological Column Ordering

Event timing columns are ordered chronologically within a trial:

| Order | Column | Typical Timing |
|-------|--------|----------------|
| 1 | `gabor_stimulus_onset_time` | 0 ms (reference) |
| 2 | `auditory_cue_time` | ~0 ms (simultaneous) |
| 3 | `wheel_movement_onset_time` | +200 ms |
| 4 | `choice_registration_time` | +593 ms |
| 5 | `feedback_time` | +593 ms |
| 6 | `gabor_stimulus_offset_time` | +1950 ms |

### Example Queries

```python
# Get left stimulus trials with correct outcomes (rewarded)
left_correct = trials[
    (trials['gabor_stimulus_side'] == 'left') &
    trials['is_mouse_rewarded']
]

# Get trials where mouse chose left
chose_left = trials[trials['mouse_wheel_choice'] == 'left']

# Calculate reaction time (stimulus to movement onset)
trials['reaction_time'] = trials['wheel_movement_onset_time'] - trials['gabor_stimulus_onset_time']

# Calculate motor time (movement onset to choice registration)
trials['motor_time'] = trials['choice_registration_time'] - trials['wheel_movement_onset_time']
```

### IBL to NWB Column Mapping

For users familiar with IBL naming conventions:

| IBL Column | NWB Column | Transformation |
|------------|------------|----------------|
| `intervals_0` | `start_time` | Direct copy |
| `intervals_1` | `stop_time` | Direct copy |
| `quiescencePeriod` | `quiescence_period` | Direct copy |
| `stimOn_times` | `gabor_stimulus_onset_time` | Direct copy |
| `goCue_times` | `auditory_cue_time` | Direct copy |
| `firstMovement_times` | `wheel_movement_onset_time` | Direct copy |
| `response_times` | `choice_registration_time` | Direct copy |
| `feedback_times` | `feedback_time` | Direct copy |
| `stimOff_times` | `gabor_stimulus_offset_time` | Direct copy |
| `contrastLeft`/`contrastRight` | `gabor_stimulus_contrast` | Consolidated (x100) |
| `contrastLeft`/`contrastRight` | `gabor_stimulus_side` | Computed |
| `probabilityLeft` | `probability_left` | Direct copy |
| `choice` | `mouse_wheel_choice` | -1/0/+1 to strings |
| `feedbackType` | `is_mouse_rewarded` | -1/+1 to boolean |
| `rewardVolume` | `reward_volume_uL` | Direct copy |

### References

- Wickham, H. (2014). Tidy Data. *Journal of Statistical Software*, 59(10), 1-23. https://doi.org/10.18637/jss.v059.i10
- NWB Best Practices: https://www.nwb.org/best-practices/

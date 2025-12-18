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
- Adds 14 columns to the NWB trials table
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

The interface adds the following 14 columns to the NWB trials table:

### Temporal Columns

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `start_time` | `intervals_0` | The beginning of the trial (seconds from session start) |
| `stop_time` | `intervals_1` | The end of the trial (seconds from session start) |

### Event Timing Columns

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `stim_on_time` | `stimOn_times` | Time when the visual stimulus appears on screen, detected by photodiode placed over the sync square |
| `stim_off_time` | `stimOff_times` | Time of stimulus offset, recorded by external photodiode |
| `go_cue_time` | `goCue_times` | Start time of the go cue tone (100 ms, 5 kHz sine wave). Recorded via soundcard sync fed back into Bpod |
| `response_time` | `response_times` | Time when response was recorded. Marks end of closed loop state - occurs when 60s elapsed OR wheel reaches threshold |
| `feedback_time` | `feedback_times` | Time of feedback delivery. For correct trials: valve TTL trigger. For incorrect: white noise trigger |
| `first_movement_time` | `firstMovement_times` | Time of first wheel movement >= 0.1 radians, occurring between go cue and feedback. May be slightly before cue if movement started during quiescence |

### Stimulus Columns

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `contrast_left` | `contrastLeft` | Contrast of stimulus at -35 degrees azimuth (left). Value is 0 when stimulus is on right, NaN for catch trials |
| `contrast_right` | `contrastRight` | Contrast of stimulus at +35 degrees azimuth (right). Value is 0 when stimulus is on left, NaN for catch trials |
| `probability_left` | `probabilityLeft` | Prior probability that stimulus appears left. Values: 0.2, 0.5, or 0.8 (biasedChoiceWorld) or based on recent bias (trainingChoiceWorld) |

### Response and Outcome Columns

| NWB Column | IBL Source | Description |
|------------|------------|-------------|
| `choice` | `choice` | Mouse response: -1 = CCW wheel turn (move stimulus right), +1 = CW wheel turn (move stimulus left), 0 = timeout (no response within 60s) |
| `feedback_type` | `feedbackType` | Trial outcome: +1 = correct response (reward), -1 = incorrect response or timeout (white noise) |
| `reward_volume` | `rewardVolume` | Volume of sugar water delivered (uL). 0 for incorrect trials. Typically 1.5-3 uL, constant within session |

### Available but Not Currently Included in NWB

#### Available via ONE API

| IBL Source | Description | Typical Values | ONE Dataset |
|------------|-------------|----------------|-------------|
| `quiescencePeriod` | Duration of the quiescence period before go cue (seconds). Mouse must hold wheel still during this period | 0.4-0.7s (exponential distribution, mean ~0.53s) | `_ibl_trials.quiescencePeriod.npy` |

This field is loaded automatically by `SessionLoader` and could be added to the NWB conversion:

```python
from brainbox.io.one import SessionLoader

session_loader = SessionLoader(one=one, eid=session_id)
session_loader.load_trials()
trials = session_loader.trials

# quiescencePeriod is available
print(trials['quiescencePeriod'].describe())
```

#### NOT Available in Database (Extracted but Not Saved)

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

#### `get_metadata()`
Loads trial column metadata from [trials.yml](../IBL-to-nwb/src/ibl_to_nwb/_metadata/trials.yml), which contains human-readable descriptions for each column.

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

### Choice Values
| Value | Meaning | Wheel Direction | Stimulus Movement |
|-------|---------|-----------------|-------------------|
| -1 | Left choice | Counter-clockwise | Stimulus moves right |
| +1 | Right choice | Clockwise | Stimulus moves left |
| 0 | No-go / Timeout | No movement to threshold | N/A |

### Feedback Type Values
| Value | Meaning | Consequence |
|-------|---------|-------------|
| +1 | Correct | Sugar water reward delivered |
| -1 | Incorrect/Timeout | White noise burst, 2s timeout |

### Probability Left Values (biasedChoiceWorld)
| Value | Block Type | Stimulus More Likely On |
|-------|------------|------------------------|
| 0.2 | Right-biased block | Right side (80%) |
| 0.5 | Neutral block | Equal (50/50) |
| 0.8 | Left-biased block | Left side (80%) |

### Contrast Interpretation
| contrast_left | contrast_right | Trial Type |
|---------------|----------------|------------|
| > 0 | 0 | Left stimulus trial |
| 0 | > 0 | Right stimulus trial |
| NaN | NaN | Catch trial (no stimulus) |

---

## Proposal: Tidy Data Format Improvements

This section proposes improvements to the trials table structure following [tidy data principles](https://vita.had.co.nz/papers/tidy-data.pdf) (Wickham, 2014). The goal is to make the data more self-documenting, easier to analyze, and aligned with best practices for tabular data.

### Motivation

The current implementation preserves IBL's internal numeric encodings (e.g., `-1/0/+1` for choice). While this maintains compatibility with existing IBL analysis code, it has drawbacks:

1. **Not self-documenting**: Users must consult documentation to understand what `-1` means
2. **Error-prone**: Easy to confuse `-1` (left) with `+1` (right)
3. **Violates tidy data principle**: "Each variable forms a column" - but `contrast_left` and `contrast_right` encode two pieces of information (contrast value AND stimulus side) across two columns
4. **Query complexity**: Filtering requires numeric comparisons rather than semantic queries

### Proposed Changes

#### 1. Temporal Column Ordering

**Current order** (arbitrary):
```
feedback_times, response_times, stimOff_times, stimOn_times, goCue_times, firstMovement_times
```

**Proposed order** (chronological within a trial):
```
go_cue_time, stim_on_time, first_movement_time, response_time, feedback_time, stim_off_time
```

| Order | Column | Typical Timing (relative to stim_on) |
|-------|--------|--------------------------------------|
| 1 | `go_cue_time` | ~0 ms (simultaneous with stimulus) |
| 2 | `stim_on_time` | 0 ms (reference point) |
| 3 | `first_movement_time` | +200 ms |
| 4 | `response_time` | +593 ms |
| 5 | `feedback_time` | +593 ms |
| 6 | `stim_off_time` | +1950 ms |

**Rationale**: Chronological ordering makes the trial structure immediately apparent and aids understanding of the temporal sequence of events.

#### 2. Categorical Choice Values

**Current**:
| Value | Meaning |
|-------|---------|
| -1 | Left choice (CCW wheel turn) |
| 0 | No-go / Timeout |
| +1 | Right choice (CW wheel turn) |

**Proposed**:
| Value | Meaning |
|-------|---------|
| `"left"` | Left choice (CCW wheel turn) |
| `"no_go"` | No-go / Timeout |
| `"right"` | Right choice (CW wheel turn) |

**Rationale**: String values are self-documenting. Queries become `choice == "left"` instead of `choice == -1`, reducing cognitive load and potential errors.

#### 3. Categorical Feedback Type

**Current**:
| Value | Meaning |
|-------|---------|
| +1 | Correct response |
| -1 | Incorrect response or timeout |

**Proposed**:
| Value | Meaning |
|-------|---------|
| `"correct"` | Correct response (reward delivered) |
| `"incorrect"` | Incorrect response or timeout (white noise) |

**Rationale**: Same as choice - semantic clarity over numeric encoding.

#### 4. Consolidated Contrast Columns (Tidy Format)

**Current structure** (wide format, violates tidy principles):
| contrast_left | contrast_right | Interpretation |
|---------------|----------------|----------------|
| 0.25 | 0 | Left stimulus at 25% |
| 0 | 1.0 | Right stimulus at 100% |
| NaN | NaN | Catch trial |

**Proposed structure** (tidy format):
| contrast | stimulus_side | Interpretation |
|----------|---------------|----------------|
| 0.25 | `"left"` | Left stimulus at 25% |
| 1.0 | `"right"` | Right stimulus at 100% |
| NaN | `"none"` | Catch trial |

**Rationale**:
- **Tidy data principle**: Each variable should form a column. Currently, stimulus side is implicitly encoded by which column has a non-zero value.
- **Reduced redundancy**: The current format always has one column at 0 when the other is non-zero - this is redundant information.
- **Simpler queries**: `stimulus_side == "left"` vs `(contrast_left > 0) | (contrast_left.notna() & contrast_right.isna())`
- **Easier aggregation**: Grouping by stimulus side becomes trivial.

### Size Impact Analysis

The proposed changes have **negligible size impact**:

| Encoding | Bytes per trial | 500 trials |
|----------|-----------------|------------|
| Current (4 float64 cols) | 32 bytes | 15.6 KiB |
| Proposed (2 strings + 1 float + 1 string) | ~30 bytes | 14.6 KiB |

String columns in HDF5/NWB are stored efficiently, and the consolidation of two contrast columns into one actually offsets any string overhead.

### Backwards Compatibility Considerations

**Challenge**: Existing IBL analysis code expects numeric encodings.

**Mitigation strategies**:
1. **Documentation**: Clear mapping between old and new values
2. **Utility functions**: Provide conversion functions in ibllib for users who need numeric format
3. **NWB is the target format**: Users accessing data via NWB are likely building new analysis pipelines anyway

### Example: Improved Query Patterns

**Current (numeric encoding)**:
```python
# Get left stimulus trials with correct responses
left_correct = trials[
    (trials['contrast_left'] > 0) &
    (trials['feedback_type'] == 1)
]

# Get trials where mouse chose left
chose_left = trials[trials['choice'] == -1]
```

**Proposed (categorical encoding)**:
```python
# Get left stimulus trials with correct responses
left_correct = trials[
    (trials['stimulus_side'] == 'left') &
    (trials['feedback_type'] == 'correct')
]

# Get trials where mouse chose left
chose_left = trials[trials['choice'] == 'left']
```

### Implementation Status

- [x] Temporal column reordering
- [x] Categorical choice values
- [x] Categorical feedback_type values
- [x] Consolidated contrast + stimulus_side columns
- [x] Update consistency checks
- [x] Remove metadata YAML (consolidated inline in interface)
- [ ] Update notebook examples

### References

- Wickham, H. (2014). Tidy Data. *Journal of Statistical Software*, 59(10), 1-23. https://doi.org/10.18637/jss.v059.i10
- NWB Best Practices: https://www.nwb.org/best-practices/

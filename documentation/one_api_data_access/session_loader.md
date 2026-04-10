# SessionLoader Documentation

## Overview

The `SessionLoader` class from `brainbox.io.one` provides a **unified interface** for loading behavioral and video data from IBL experimental sessions. It simplifies data loading by automatically handling different data types, timestamps, and providing consistent pandas DataFrame outputs.

```python
from brainbox.io.one import SessionLoader
from one.api import ONE

one = ONE()
sess_loader = SessionLoader(one=one, eid="your-session-id")
```

## Purpose and Benefits

### Why Use SessionLoader?

1. **Unified Interface**: Single object to access all session behavioral data
2. **Automatic Processing**: Handles interpolation, filtering, and timestamp alignment
3. **Consistent Format**: All data returned as pandas DataFrames with standardized 'times' columns
4. **Lazy Loading**: Data only loaded when requested
5. **Quality Control**: Built-in checks and corrections for video timestamps
6. **Progress Tracking**: Monitor which data types have been loaded

### What Data Types Does It Load?

- **Trials**: Task behavioral data (stimulus presentation, choices, outcomes)
- **Wheel**: Mouse wheel movements (position, velocity, acceleration)
- **Pose**: Camera-based pose estimation from DLC or Lightning Pose
- **Motion Energy**: ROI-based motion detection from videos
- **Pupil**: Pupil diameter measurements from left camera

## Class Structure

### Initialization Parameters

```python
SessionLoader(
    one=one,                    # ONE API instance (required)
    eid="session-uuid",         # Session ID (required if no session_path)
    session_path="/path/to/session/",  # Local session path (required if no eid)
    revision="2024-05-06"       # Data revision (optional, uses latest if None)
)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `one` | `one.api.ONE` | Yes | ONE API instance for data access |
| `eid` | `str` | Conditional | Session UUID (required if no session_path) |
| `session_path` | `str/Path` | Conditional | Local path to session (required if no eid) |
| `revision` | `str` | No | Data revision (e.g., "2024-05-06"), uses latest if None |

**Note**: If both `eid` and `session_path` are provided, `session_path` takes precedence.

### Class Attributes

```python
# Data tracking
sess_loader.data_info          # DataFrame showing what's been loaded
sess_loader.eid               # Session UUID
sess_loader.session_path      # Path to session data
sess_loader.revision          # Data revision being used

# Loaded data (initially empty DataFrames/dicts)
sess_loader.trials            # pandas.DataFrame - trial data
sess_loader.wheel             # pandas.DataFrame - wheel data
sess_loader.pose              # dict - pose data by camera
sess_loader.motion_energy     # dict - motion energy by camera
sess_loader.pupil             # pandas.DataFrame - pupil data
```

## Core Methods

### 1. `load_session_data()` - Load All Data

```python
sess_loader.load_session_data(
    trials=True,           # Load trials data
    wheel=True,           # Load wheel data
    pose=True,            # Load pose estimation
    motion_energy=True,   # Load motion energy
    pupil=True,           # Load pupil diameter
    reload=False          # Re-load already loaded data
)
```

**Purpose**: Loads multiple data types in one call with progress tracking.

### 2. `load_trials()` - Behavioral Task Data

```python
sess_loader.load_trials(collection=None)
```

**Source Files**:
- Loads ALF object: `trials`
- Primary file: `_ibl_trials.table.pqt`
- Alternative files: `trials.*.npy` (individual trial attributes)

**Returns**: `pandas.DataFrame` with columns like:
- `stimOn_times` - stimulus onset timestamps
- `choice` - animal's choice (-1, 0, 1)
- `feedbackType` - reward/punishment (1, -1)
- `contrastLeft`, `contrastRight` - stimulus contrasts
- `response_times` - reaction times
- `goCue_times` - go cue timestamps

**Collection**: Usually found in `alf/` collection

### 3. `load_wheel()` - Mouse Wheel Data

```python
sess_loader.load_wheel(
    fs=1000,              # Sampling frequency (Hz)
    corner_frequency=20,  # Low-pass filter cutoff (Hz)
    order=8,             # Filter order
    collection=None      # Data collection
)
```

**Source Files**:
- Loads ALF object: `wheel`
- Primary file: `_ibl_wheel.position.npy`
- Additional files: `_ibl_wheel.timestamps.npy`

**Returns**: `pandas.DataFrame` with columns:
- `times` - timestamps (seconds)
- `position` - wheel position (radians)
- `velocity` - wheel velocity (rad/s)
- `acceleration` - wheel acceleration (rad/s²)

**Processing**: Interpolates to uniform sampling rate, applies Butterworth low-pass filter.

**Collection**: Usually found in `alf/` collection

### 4. `load_pose()` - Pose Estimation Data

```python
sess_loader.load_pose(
    likelihood_thr=0.9,              # Likelihood threshold for filtering
    views=['left', 'right', 'body'], # Camera views to load
    tracker='dlc'                    # Tracker: 'dlc' or 'lightningPose'
)
```

**Source Files**:
- Loads ALF objects: `{view}Camera` (e.g., `leftCamera`, `rightCamera`, `bodyCamera`)
- **DLC files**:
  - `_ibl_{view}Camera.dlc.pqt` - DLC pose estimates
  - `_ibl_{view}Camera.times.npy` - video timestamps
- **Lightning Pose files**:
  - `_ibl_{view}Camera.lightningPose.pqt` - Lightning Pose estimates
  - `_ibl_{view}Camera.times.npy` - video timestamps

**Returns**: `dict` with camera keys (`leftCamera`, `rightCamera`, `bodyCamera`)
Each camera contains a `pandas.DataFrame` with:
- `times` - video timestamps
- `{bodypart}_{x/y/likelihood}` - body part coordinates and confidence

**Example**:
```python
sess_loader.pose['leftCamera'].columns
# Index(['times', 'nose_tip_x', 'nose_tip_y', 'nose_tip_likelihood', ...])
```

**Collection**: Usually found in `alf/` collection

### 5. `load_motion_energy()` - Video Motion Detection

```python
sess_loader.load_motion_energy(
    views=['left', 'right', 'body']  # Camera views to load
)
```

**Source Files**:
- Loads ALF objects: `{view}Camera`
- **Motion Energy files**:
  - `_ibl_{view}Camera.ROIMotionEnergy.npy` - motion energy values
  - `_ibl_{view}Camera.times.npy` - video timestamps

**Returns**: `dict` with camera keys, each containing `pandas.DataFrame`:
- **Left/Right cameras**: `whiskerMotionEnergy` - whisker pad motion
- **Body camera**: `bodyMotionEnergy` - whole body motion
- `times` - video timestamps

**Collection**: Usually found in `alf/` collection

### 6. `load_pupil()` - Pupil Diameter

```python
sess_loader.load_pupil(
    snr_thresh=5.0  # Signal-to-noise ratio threshold
)
```

**Source Files**:
- **Primary source** (if available):
  - `_ibl_leftCamera.features.pqt` - pre-computed pupil features
  - `_ibl_leftCamera.times.npy` - video timestamps
- **Fallback computation** (if features unavailable):
  - Uses DLC pose data from `leftCamera` to compute pupil diameter on-the-fly
  - Requires `_ibl_leftCamera.dlc.pqt` and `_ibl_leftCamera.times.npy`

**Returns**: `pandas.DataFrame` with:
- `times` - timestamps
- `pupilDiameter_raw` - raw pupil diameter
- `pupilDiameter_smooth` - smoothed pupil diameter

**Collection**: Usually found in `alf/` collection

## File Location Summary

All SessionLoader data files are typically located in the `alf/` collection with the following naming patterns:

| Data Type | File Pattern | Description |
|-----------|--------------|-------------|
| **Trials** | `_ibl_trials.table.pqt` | Behavioral trial data (primary) |
| | `trials.*.npy` | Individual trial attributes (alternative) |
| **Wheel** | `_ibl_wheel.position.npy` | Wheel position data |
| | `_ibl_wheel.timestamps.npy` | Wheel timestamps |
| **Pose** | `_ibl_{view}Camera.dlc.pqt` | DLC pose estimates |
| | `_ibl_{view}Camera.lightningPose.pqt` | Lightning Pose estimates |
| | `_ibl_{view}Camera.times.npy` | Video timestamps |
| **Motion Energy** | `_ibl_{view}Camera.ROIMotionEnergy.npy` | Motion energy data |
| | `_ibl_{view}Camera.times.npy` | Video timestamps |
| **Pupil** | `_ibl_leftCamera.features.pqt` | Pre-computed pupil features |
| | `_ibl_leftCamera.times.npy` | Video timestamps |

**Camera Views**: `{view}` can be `left`, `right`, or `body`

**Collection Path**: Files are typically found in `alf/` collection, e.g.:
- `alf/_ibl_trials.table.pqt`
- `alf/_ibl_wheel.position.npy`
- `alf/_ibl_leftCamera.dlc.pqt`

## Collection Auto-Detection

SessionLoader automatically detects the appropriate collection for each data type:

1. **Primary search**: Looks for specific dataset files (e.g., `_ibl_trials.table.pqt`)
2. **Collection inference**: If files found, uses their collection
3. **Default fallback**: If no files found, defaults to `alf/` collection
4. **Conflict handling**: If multiple collections found, raises error and prompts user to specify

This ensures SessionLoader works across different data organization schemes while maintaining backward compatibility.

## Integration with Revisions

All SessionLoader methods respect the `revision` parameter:

```python
# Load specific revision
sess_loader = SessionLoader(one=one, eid=eid, revision="2024-05-06")
sess_loader.load_session_data()

# All individual load methods also support revision
sess_loader.load_trials()  # Uses the revision specified during initialization
```

When a revision is specified, SessionLoader looks for files in the revision-specific subdirectories (e.g., `alf/#2024-05-06#/`) before falling back to the default locations.

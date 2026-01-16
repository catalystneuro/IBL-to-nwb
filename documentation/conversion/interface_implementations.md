# Interface Implementations Reference

This document details how each data interface implements the four key methods defined in `BaseIBLDataInterface`. For the specification of the interface contract, see [ibl_data_interface_design.md](ibl_data_interface_design.md).

## Quick Reference Table

| Interface | REVISION | check_availability | download_data | Data Loading |
|-----------|----------|-------------------|---------------|--------------|
| WheelInterface | 2025-05-06 | Base class | Custom (iterates files) | `one.load_object()` |
| LickInterface | 2025-05-06 | Base class | Custom (single file) | `one.load_dataset()` |
| BrainwideMapTrialsInterface | 2025-05-06 | Base class | Custom (SessionLoader) | `SessionLoader` |
| IblPoseEstimationInterface | 2025-05-06 | QC override | Custom (file discovery) | `SessionLoader` |
| PupilTrackingInterface | 2025-05-06 | QC override | Custom (load_object) | `one.load_object()` |
| RoiMotionEnergyInterface | 2025-05-06 | QC override | Custom (iterates files) | `one.load_object()` |
| IblSortingInterface | 2025-05-06 | Base class | Custom (SpikeSortingLoader) | `SpikeSortingLoader` |
| IblNIDQInterface | 2025-05-06 | Base class | Custom (with try-except) | `one.load_dataset()` |
| RawVideoInterface | 2025-05-06 | QC override | Custom (mixed) | `one.load_object()` + `one.load_dataset()` |
| PassiveIntervalsInterface | Dynamic | Base class | Custom (dynamic revision) | `one.load_dataset()` |
| PassiveReplayStimInterface | Dynamic | Base class | Custom (dynamic revision) | `one.load_dataset()` |
| SessionEpochsInterface | Dynamic | Base class | Custom (dynamic revision) | `one.load_dataset()` |
| ProbeTrajectoryInterface | None | Custom (API query) | No-op | `one.alyx.rest()` |
| IblAnatomicalLocalizationInterface | 2025-05-06 | Custom (histology QC) | Custom (SpikeSortingLoader) | `SpikeSortingLoader` |

**Note:** `download_data()` is **not** an abstract method - the base class provides a default implementation. However, all current interfaces override it for one of these reasons:
- Uses high-level abstractions (`SessionLoader`, `SpikeSortingLoader`) instead of direct ONE calls
- Needs dynamic revision resolution (passive protocol interfaces)
- Simpler implementation for single files
- Reimplements base logic with timing instrumentation

In principle, new interfaces could rely on the base class `download_data()` if their requirements fit the standard pattern.

---

## Behavioral Interfaces

### WheelInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_wheel_movement_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": [
            "alf/wheel.position.npy",
            "alf/wheel.timestamps.npy",
            "alf/wheelMoves.intervals.npy",
            "alf/wheelMoves.peakAmplitude.npy",
        ],
    },
}
```

**Why these requirements?** Wheel data has two components: (1) raw position timeseries for computing velocity/acceleration, and (2) discrete movement intervals with peak amplitudes. Both are required for complete wheel kinematics analysis.

**check_availability():** Uses base class implementation. No additional QC checks.

**download_data():** Custom implementation that calls `one.load_object()` for wheel and wheelMoves objects.

**add_to_nwbfile():**
- Loads wheel and wheelMoves via `one.load_object()`
- Computes velocity and acceleration using `brainbox.behavior.wheel.velocity_filtered()`
- Creates:
  - `SpatialSeries` for wheel position (radians)
  - `TimeSeries` for velocity and acceleration
  - `TimeIntervals` for wheel movement periods
- Adds to behavior processing module

---

### LickInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_lick_times_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": ["alf/licks.times.npy"],
    },
}
```

**Why these requirements?** Licks are discrete point events detected from tongue pose (Lightning Pose). Only timestamps are needed - no amplitude or duration data exists.

**check_availability():** Uses base class implementation.

**download_data():** Custom implementation. Uses `one.load_dataset()` directly - simpler than the base class pattern for a single file.

**add_to_nwbfile():**
- Loads lick times via `one.load_dataset()`
- Creates `ndx_events.Events` object (point events with timestamps only)
- Adds to `lick_times` processing module

---

### BrainwideMapTrialsInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_brainwide_map_trials_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "bwm_format": ["alf/trials.table.pqt"],
        "legacy_format": [
            "alf/trials.intervals.npy",
            "alf/trials.choice.npy",
            "alf/trials.feedbackType.npy",
            "alf/trials.contrastLeft.npy",
            "alf/trials.contrastRight.npy",
            "alf/trials.probabilityLeft.npy",
            "alf/trials.feedback_times.npy",
            "alf/trials.response_times.npy",
            "alf/trials.stimOn_times.npy",
            "alf/trials.goCue_times.npy",
            "alf/trials.firstMovement_times.npy",
        ],
    },
}
```

**Why these requirements?** IBL data release had format evolution. Brain-Wide Map (BWM) uses a consolidated parquet table for efficiency. Legacy sessions still have individual `.npy` files (one per trial attribute). The two format options allow the pipeline to convert both old and new sessions.

**check_availability():** Uses base class implementation. The base class tries each format option until finding one where ALL files exist.

**download_data():** Custom implementation. Uses `SessionLoader.load_trials()` high-level abstraction instead of direct ONE API calls.

**add_to_nwbfile():**
- Loads trials via `SessionLoader` instance
- Applies tidy data transformations:
  - `choice`: -1/0/+1 mapped to "left"/"no_go"/"right"
  - `feedbackType`: +1/-1 mapped to `is_mouse_rewarded` (True/False)
  - `contrastLeft`/`contrastRight` combined into `gabor_stimulus_contrast` + `gabor_stimulus_side`
  - `probabilityLeft` converted to `block_index` (increments on change) + `block_type` (categorical)
- Creates `TimeIntervals` table with `VectorData` columns
- Column definitions in static `TRIALS_COLUMNS` dict

---

## Video-Derived Interfaces

### IblPoseEstimationInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_pose_estimation_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements(camera_name):**
```python
{
    "exact_files_options": {
        "standard": [f"alf/_ibl_{camera_name}Camera.lightningPose.pqt"],
    },
}
```

**Why these requirements?** Lightning Pose produces one parquet file per camera containing tracked body parts (x, y, likelihood columns). Different cameras capture different body regions (left camera sees left paw, body camera sees full body). The `camera_name` parameter makes this interface reusable across all three camera views.

**check_availability():** **Overridden with QC filtering.** Checks `bwm_qc.json` fixture for video QC status. Sessions with CRITICAL or FAIL status are excluded. Returns `qc_status` in result dict.

**download_data():** Custom implementation. Uses `one.list_datasets()` to find matching files with fallback logic for alternative trackers (Lightning Pose vs DLC), then `one.load_dataset()` to download.

**add_to_nwbfile():**
- Loads pose data via `SessionLoader.load_pose(tracker, views)`
- Extracts body parts from DataFrame columns (x, y, likelihood per body part)
- Creates `PoseEstimationSeries` objects per body part
- Maps IBL body part names to NWB names (static dict)
- Creates `Skeleton` and `Skeletons` container
- Adds to `pose_estimation` processing module

---

### PupilTrackingInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_pupil_tracking_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements(camera_name):**
```python
{
    "exact_files_options": {
        "standard": [
            f"alf/_ibl_{camera_name}Camera.features.pqt",
            f"alf/_ibl_{camera_name}Camera.times.npy",
        ],
    },
}
```

**Why these requirements?** Pupil tracking data consists of: (1) a features parquet containing diameter measurements (raw and smoothed), and (2) timestamps shared across video frames. These form a single camera object in the ONE API. Timestamps are separate because they're shared with other camera-derived data.

**check_availability():** **Overridden with QC filtering.** Checks `bwm_qc.json` for video QC. CRITICAL/FAIL excluded.

**download_data():** Custom implementation. Calls `one.load_object()` for camera object - simpler than iterating the base class pattern.

**add_to_nwbfile():**
- Loads camera object via `one.load_object()`
- Extracts `pupilDiameter_raw` and `pupilDiameter_smooth` from features table
- Handles dimension mismatches (truncates timestamps if needed)
- Creates `TimeSeries` objects for each metric
- Adds to `video` processing module

---

### RoiMotionEnergyInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_roi_motion_energy_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements(camera_name):**
```python
{
    "exact_files_options": {
        "standard": [
            f"alf/_ibl_{camera_name}Camera.ROIMotionEnergy.npy",
            f"alf/_ibl_{camera_name}Camera.times.npy",
            f"alf/{camera_name}ROIMotionEnergy.position.npy",
        ],
    },
}
```

**Why these requirements?** Motion energy requires both data AND metadata: (1) the motion energy timeseries, (2) timestamps, and (3) ROI definition (width, height, x, y position). The ROI metadata is essential to interpret what region of the video the motion energy was computed from. Camera timestamps and ROI metadata are loaded as separate ONE objects.

**check_availability():** **Overridden with QC filtering.** Checks `bwm_qc.json`. CRITICAL/FAIL excluded.

**download_data():** Custom implementation. Calls `one.load_object()` for camera and ROIMotionEnergy objects.

**add_to_nwbfile():**
- Loads camera object and ROIMotionEnergy metadata via `one.load_object()`
- Extracts ROI position (width, height, x, y) from metadata
- Creates `TimeSeries` with computed motion energy values
- Builds description with ROI geometry and axis orientation warning
- Adds to `video` processing module

---

### RawVideoInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_raw_video_interface.py`

**REVISION:** `"2025-05-06"` (for timestamps only; video files have no revision)

**get_data_requirements(camera_name):**
```python
{
    "exact_files_options": {
        "standard": [
            f"alf/_ibl_{camera_name}Camera.times.npy",
            f"raw_video_data/_iblrig_{camera_name}Camera.raw.mp4",
        ],
    },
}
```

**Why these requirements?** Raw video needs: (1) corrected/aligned camera timestamps (processed data in `alf/`), and (2) the raw video file (immutable binary in `raw_video_data/`). These come from different collections because raw video is never reprocessed, but timestamps may be corrected during synchronization. The video file has no revision (immutable), while timestamps use the BWM revision.

**check_availability():** **Overridden with QC filtering.** Checks `bwm_qc.json`. CRITICAL/FAIL excluded.

**download_data():** Custom implementation.
- Loads camera object (timestamps) via `one.load_object()` with revision
- Loads video file via `one.load_dataset()` without revision filtering (raw files don't have revisions)

**add_to_nwbfile():**
- Loads camera times via `one.load_object()`
- Loads video file via `one.load_dataset()` (no revision)
- Copies video to DANDI-organized folder structure
- Creates `ImageSeries` with external file reference
- Adds to `nwbfile.acquisition`

---

## Electrophysiology Interfaces

### IblSortingInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_ibl_sorting_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": [
            "alf/probe*/spikes.times.npy",
            "alf/probe*/spikes.clusters.npy",
            "alf/probe*/spikes.amps.npy",
            "alf/probe*/spikes.depths.npy",
            "alf/probe*/clusters.channels.npy",
            "alf/probe*/clusters.depths.npy",
            "alf/probe*/clusters.metrics.pqt",
        ],
    },
}
```

**Why these requirements?** Complete spike sorting requires per-spike data (times, cluster assignments, amplitudes, depths) AND per-cluster data (channel assignments, depths, quality metrics). Wildcards (`probe*`) are used because sessions have variable numbers of probes (1-8). `SpikeSortingLoader` handles the loading abstraction internally.

**check_availability():** Uses base class implementation. Base class expands wildcards via regex matching.

**download_data():** Custom implementation.
- Gets `probe_name_to_probe_id_dict` from fixtures
- Loops through probes, creates `SpikeSortingLoader` per probe
- Calls `ssl.load_spike_sorting()` for each (high-level abstraction)

**add_to_nwbfile():**
- Loads IBL data via `IblSortingExtractor` (lazy loading wrapper)
- Creates electrodes table with CCF coordinates if none exists
- Maps units to electrodes using waveform peak channels
- Converts property names from IBL to NWB (static `UNITS_COLUMNS` dict)
- Handles amplitude unit conversion (Volts to microvolts)
- Sets ragged array properties (spike amplitudes, depths)
- Calls neuroconv's `add_sorting_to_nwbfile()` with waveform means

---

### IblNIDQInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_ibl_nidq_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": [
            "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.cbin",
            "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.meta",
            "raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.ch",
            "raw_ephys_data/_spikeglx_ephysData_g0_t0.wiring.json",
        ],
    },
}
```

**Why these requirements?** NIDQ (National Instruments DAQ) records analog and digital signals: (1) `.cbin` is the compressed binary data, (2) `.meta` contains SpikeGLX metadata (sample rate, gains, channel count), (3) `.ch` maps channels to names, and (4) `wiring.json` is IBL-specific metadata mapping hardware ports to behavioral device names. The wiring file is critical because different rigs have different channel assignments.

**check_availability():** Uses base class implementation.

**download_data():** Custom implementation. Downloads each NIDQ file via `one.load_dataset()`. **Note:** This interface includes try-except wrapping around individual file downloads, which deviates from the fail-fast philosophy (but still re-raises the exception after logging).

**add_to_nwbfile():**
- Inherits from NeuroConv's `SpikeGLXNIDQInterface`
- Loads `wiring.json` at init time
- Dynamically builds `digital_channel_groups` and `analog_channel_groups` from wiring
- Maps port/channel names to device labels (static `DIGITAL_DEVICE_LABELS` dict)
- Excludes laser channels from conversion
- Loads metadata from YAML file, filters to devices present in wiring

---

### IblAnatomicalLocalizationInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_ibl_anatomical_localization_interface.py`

**REVISION:** `"2025-05-06"`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": [
            "alf/probe*/electrodeSites.localCoordinates.npy",
            "alf/probe*/electrodeSites.brainLocationIds_ccf_2017.npy",
            "raw_ephys_data/probe*/*.ap.meta",
        ],
    },
}
```

**Why these requirements?** Anatomical localization requires: (1) electrode site coordinates from histology alignment (in `alf/`), (2) CCF brain region IDs for each electrode, and (3) SpikeGLX `.meta` files for electrode geometry (x, y positions within probe, channel mapping, gains). The `.meta` files are in `raw_ephys_data/` because they're recording metadata, while histology alignment results are processed data in `alf/`. Wildcards handle variable probe counts.

**check_availability():** **Custom implementation with histology QC.** Loads `bwm_histology_qc.json` fixture. Checks per-probe quality (only `histology_quality == 'alf'` included - meaning the histology alignment passed QC). Returns `available_probes`, `unavailable_probes`, `missing_files`.

**download_data():** Custom implementation.
- Loads histology QC fixture for filtering
- Uses `SpikeSortingLoader` to download histology data per probe
- Downloads SpikeGLX `.meta` files for electrode geometry
- Quality filtering: skips probes with `quality != 'alf'`

**add_to_nwbfile():**
- Requires electrodes table to exist with x, y, z, location columns
- Creates two coordinate spaces: `AllenCCFv3` and `IBLBregma`
- Creates `AnatomicalCoordinatesTable` for each space
- Adds columns: `probe_name`, `atlas_id`, `beryl_location`, `cosmos_location`
- Converts IBL coordinates to CCF coordinates using atlas
- Loads hierarchical brain region mappings (Beryl, Cosmos)
- Creates merged table for all probes
- Adds to `Localization` lab metadata

---

## Passive Protocol Interfaces

### PassiveIntervalsInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_ibl_passive_intervals_interface.py`

**REVISION:** Dynamic - queries ONE API for latest available from `["2025-12-04", "2025-12-05"]`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": ["alf/_ibl_passivePeriods.intervalsTable.csv"],
    },
}
```

**Why these requirements?** The passive periods CSV defines the temporal structure of the passive protocol phase: when spontaneous activity recording occurred and when task replay occurred. Single file containing all interval boundaries.

**check_availability():** Uses base class implementation. Revision resolution handled separately.

**download_data():** Custom implementation. Resolves revision dynamically by querying ONE API for available revisions from `REVISION_CANDIDATES`. Downloads CSV via `one.load_dataset()`.

**add_to_nwbfile():**
- Loads CSV during `__init__` (fail-fast)
- Creates custom `TimeIntervals` table in `processing/passive_protocol`
- Adds `protocol_name` column (`spontaneousActivity`, `taskReplay`)
- Parses start/stop times from CSV

---

### PassiveReplayStimInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_ibl_passive_replay_interface.py`

**REVISION:** Dynamic - queries ONE API for latest available from `["2025-12-04", "2025-12-05"]`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": [
            "alf/_ibl_passiveStims.table.csv",
            "alf/_ibl_passiveGabor.table.csv",
        ],
    },
}
```

**Why these requirements?** Task replay presents stimuli from the behavioral task: (1) `passiveStims.table.csv` contains valve clicks, tones, and noise bursts that were replayed, (2) `passiveGabor.table.csv` contains Gabor patch presentations with position, contrast, and phase. Two files because Gabor stimuli have different parameters than other stimulus types.

**check_availability():** Uses base class implementation.

**download_data():** Custom implementation. Resolves revision dynamically from `REVISION_CANDIDATES`. Downloads both CSV files via `one.load_dataset()`.

**add_to_nwbfile():**
- Loads both CSVs during `__init__` (fail-fast)
- Creates `TimeIntervals` table for task replay stimuli (valve, tone, noise)
- Adds `stim_type` column for stimulus classification
- Detects and excludes overlapping Gabor stimuli (data corruption check)
- Creates separate Gabor table with position, contrast, phase columns
- Adds both tables to `passive_protocol` processing module

---

### SessionEpochsInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_session_epochs_interface.py`

**REVISION:** Dynamic - queries ONE API for latest available from `["2025-12-04", "2025-12-05"]`

**get_data_requirements():**
```python
{
    "exact_files_options": {
        "standard": ["alf/_ibl_passivePeriods.intervalsTable.csv"],
    },
}
```

**Why these requirements?** Same file as PassiveIntervalsInterface - the passive periods CSV contains the boundaries needed to define session epochs. Reuses the same data source for a different purpose (high-level epoch structure vs detailed interval table).

**check_availability():** Uses base class implementation.

**download_data():** Custom implementation. Resolves revision dynamically from `REVISION_CANDIDATES`. Downloads CSV via `one.load_dataset()`.

**add_to_nwbfile():**
- Loads CSV during `__init__`
- Creates `nwbfile.epochs` table (high-level session structure)
- Adds `protocol_type` and `epoch_description` columns
- Creates two epochs:
  - Task epoch: 0.0 to passive_start
  - Passive epoch: passive_start to passive_end

---

## Metadata Interfaces

### ProbeTrajectoryInterface

**Location:** `src/ibl_to_nwb/datainterfaces/_probe_trajectory_interface.py`

**REVISION:** `None` (API-sourced, no file revision)

**get_data_requirements():**
```python
{
    "exact_files_options": {},  # No files - uses Alyx REST API
}
```

**Why these requirements?** Probe trajectory data (insertion coordinates, angles) is stored in the Alyx database, not as files. This is database metadata about where probes were inserted, not experimental data. Empty `exact_files_options` because no files need to be downloaded.

**check_availability():** **Custom implementation.** Queries Alyx REST API (`/trajectories` endpoint) for trajectory data per probe. No file checking - just verifies trajectory records exist in the database.

**download_data():** No-op (returns success immediately). Data comes from Alyx API at `add_to_nwbfile()` time - there's nothing to download to cache.

**add_to_nwbfile():**
- Queries Alyx REST API for trajectories via `one.alyx.rest()`
- Requires `Device` objects to exist (finds by probe name)
- Creates `IblProbeInsertionTrajectoryTable` per probe
- Columns: `trajectory_source`, `ml`, `ap`, `dv`, `depth_um`, `theta`, `phi`, `roll`
- Wraps tables in `IblProbeInsertionTrajectories` container
- Adds as lab metadata

---

## Implementation Patterns

### QC Filtering Pattern

Used by video-derived interfaces (pose, pupil, motion energy, raw video) and anatomical localization:

```python
@classmethod
def check_availability(cls, one, eid, camera_name, **kwargs):
    # Load QC fixture
    qc_data = load_fixture("bwm_qc.json")

    # Check QC status
    qc_status = qc_data.get(eid, {}).get(f"{camera_name}Camera", "NOT_SET")
    if qc_status in ["CRITICAL", "FAIL"]:
        return {
            "available": False,
            "reason": f"Video QC failed: {qc_status}",
            "qc_status": qc_status,
        }

    # Fall back to base class file checking
    return super().check_availability(one, eid, camera_name=camera_name, **kwargs)
```

### Dynamic Revision Pattern

Used by passive protocol interfaces:

```python
REVISION_CANDIDATES = ["2025-12-04", "2025-12-05"]

def _resolve_revision(self, one, eid, candidates):
    """Find the last available revision from candidates."""
    available = one.list_datasets(eid)
    for rev in reversed(candidates):
        if any(f"#{rev}#" in ds for ds in available):
            return rev
    return candidates[-1]  # Default to last
```

### Data Loading Methods Summary

| Method | When to Use | Example Interfaces |
|--------|-------------|-------------------|
| `one.load_object()` | Multi-file ALF objects | Wheel, Pupil, ROI Motion Energy |
| `one.load_dataset()` | Single files | Lick, NIDQ, Passive CSVs |
| `SessionLoader` | High-level behavioral data | Trials, Pose |
| `SpikeSortingLoader` | Spike sorting with atlas | Sorting, Anatomical Localization |
| `one.alyx.rest()` | Database queries | Probe Trajectory |

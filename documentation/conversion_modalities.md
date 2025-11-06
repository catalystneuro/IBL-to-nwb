# IBL to NWB Conversion Modalities

This document describes the data modalities converted by the IBL to NWB conversion script and how they are fetched from the ONE API.

## Overview

Two NWB file types are generated:
- **RAW** - Raw electrophysiology and videos
- **PROCESSED** - Spike-sorted data, behavioral data, and video-based tracking

**Dataset scope:** 459 Brain-Wide Map sessions (2019-11-26 to 2023-10-19)
- **Single-probe sessions:** 219 (47.7%)
- **Multi-probe sessions:** 240 (52.3%)

---

## RAW Conversion Summary

| Modality | Sub-type | Files & Method of Loading Data | Quality Control Filters | Availability (BWM Dataset) |
|----------|----------|--------------------------------|------------------------|---------------------------|
| **Raw Electrophysiology** | Per probe (probe00, probe01) | `raw_ephys_data/probe*/*.ap.cbin`, `*.lf.cbin`, `*.ap.meta`, `*.ap.ch`<br>Downloaded via ONE API during download script | None | 100% (459/459 sessions)<br>**Multi-probe:** 294 sessions (64.1%)<br>**Single-probe:** 165 sessions (35.9%) |
| **Anatomical Localization** | Per probe (probe00, probe01) | `alf/probe*/channels.localCoordinates.npy`<br>`alf/probe*/channels.mlapdv.npy`<br>`alf/probe*/channels.brainLocationIds_ccf_2017.npy`<br>`alf/probe*/electrodeSites.*`<br>**Method:** `SpikeSortingLoader` (brainbox) | **Histology quality must be 'alf'**<br>Lower quality alignments excluded<br>**QC Source:** `bwm_histology_qc.pqt` fixture | 100% (459/459 sessions)<br>**Multi-probe:** 294 sessions (64.1%)<br>**Single-probe:** 165 sessions (35.9%) |
| **Raw Video** | leftCamera | `raw_video_data/_iblrig_leftCamera.raw.mp4`<br>`alf/_ibl_leftCamera.times.npy`<br>**Method:** `one.load_dataset()` (video), `one.load_object()` (timestamps) | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture | 80.8% (371/459 sessions) |
| **Raw Video** | rightCamera | `raw_video_data/_iblrig_rightCamera.raw.mp4`<br>`alf/_ibl_rightCamera.times.npy`<br>**Method:** `one.load_dataset()` (video), `one.load_object()` (timestamps) | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture | 77.6% (356/459 sessions) |
| **Raw Video** | bodyCamera | `raw_video_data/_iblrig_bodyCamera.raw.mp4`<br>`alf/_ibl_bodyCamera.times.npy`<br>**Method:** `one.load_dataset()` (video), `one.load_object()` (timestamps) | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture<br>**Note:** Body camera added Feb 2020 (56 sessions without it) | 40.5% (186/459 sessions) |

---

## PROCESSED Conversion Summary

| Modality | Sub-type | Files & Method of Loading Data | Quality Control Filters | Availability (BWM Dataset) |
|----------|----------|--------------------------------|------------------------|---------------------------|
| **Spike Sorting** | Per probe (probe00, probe01) | `alf/probe*/spikes.times.npy`, `spikes.clusters.npy`, `spikes.amps.npy`, `spikes.depths.npy`<br>`alf/probe*/clusters.channels.npy`, `clusters.depths.npy`, `clusters.metrics.pqt`, `clusters.uuids.csv`<br>**Method:** `SpikeSortingLoader` (brainbox)<br>**Revision:** `2025-05-06` | None | 100% (459/459 sessions)<br>**Multi-probe:** 294 sessions (64.1%)<br>**Single-probe:** 165 sessions (35.9%) |
| **Behavioral Trials** | - | 13 trial files: `alf/trials.intervals.npy`, `trials.choice.npy`, `trials.feedbackType.npy`, etc.<br>**Method:** `SessionLoader.load_trials()` (brainbox)<br>**Revision:** `2025-05-06` | None | 100% (459/459 sessions) |
| **Wheel Movement** | - | `alf/wheel.position.npy`, `wheel.timestamps.npy`<br>`alf/wheelMoves.intervals.npy`, `wheelMoves.peakAmplitude.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2025-05-06` | None | 100% (459/459 sessions) |
| **Passive Intervals** | - | `alf/_ibl_passivePeriods.intervalsTable.csv`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2025-05-06` | None | 92.4% (424/459 sessions) |
| **Passive Replay Stimuli** | - | `alf/_ibl_passiveStims.table.csv`<br>`alf/_ibl_passiveGabor.table.csv`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2025-05-06` | None | 76.7% (352/459 sessions) |
| **Passive RFM** | - | `alf/_ibl_passiveRFM.times.npy`<br>`raw_passive_data/_iblrig_RFMapStim.raw.bin`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2025-05-06` | None | 76.7% (352/459 sessions) |
| **Lick Detection** | - | `alf/licks.times.npy`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2025-05-06` | None | 96.5% (443/459 sessions) |
| **Pose Estimation** | leftCamera | `alf/_ibl_leftCamera.lightningPose.pqt`<br>**Method:** `SessionLoader`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**Likelihood threshold ≥ 0.9** (low-confidence → NaN)<br>**QC Source:** `bwm_qc.json` fixture | 80.8% (371/459 sessions) |
| **Pose Estimation** | rightCamera | `alf/_ibl_rightCamera.lightningPose.pqt`<br>**Method:** `SessionLoader`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**Likelihood threshold ≥ 0.9** (low-confidence → NaN)<br>**QC Source:** `bwm_qc.json` fixture | 77.6% (356/459 sessions) |
| **Pose Estimation** | bodyCamera | `alf/_ibl_bodyCamera.lightningPose.pqt`<br>**Method:** `SessionLoader`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**Likelihood threshold ≥ 0.9** (low-confidence → NaN)<br>**QC Source:** `bwm_qc.json` fixture | 39.9% (183/459 sessions) |
| **Pupil Tracking** | leftCamera | `alf/_ibl_leftCamera.features.pqt`<br>`alf/_ibl_leftCamera.times.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture | 80.8% (371/459 sessions) |
| **Pupil Tracking** | rightCamera | `alf/_ibl_rightCamera.features.pqt`<br>`alf/_ibl_rightCamera.times.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture | 77.6% (356/459 sessions) |
| **ROI Motion Energy** | leftCamera | `alf/_ibl_leftCamera.ROIMotionEnergy.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture | 80.8% (371/459 sessions) |
| **ROI Motion Energy** | rightCamera | `alf/_ibl_rightCamera.ROIMotionEnergy.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture | 77.6% (356/459 sessions) |
| **ROI Motion Energy** | bodyCamera | `alf/_ibl_bodyCamera.ROIMotionEnergy.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2025-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**QC Source:** `bwm_qc.json` fixture | 39.9% (183/459 sessions) |

**Notes:**
- **Availability percentages:** Exact values from complete analysis of all 459 BWM sessions (Nov 2019 - Oct 2023). Core interfaces (Trials, Wheel, SpikeSorting, AnatomicalLocalization) are 100% available across all sessions.
- **Revision `2025-05-06`** is the Brain-Wide Map standard, set via class-level `REVISION` attribute in each interface
- **Quality control data sources:**
  - **Video QC:** Loaded from `bwm_qc.json` fixture
    - JSON file mapping `eid → camera → QC status` (PASS/WARNING/FAIL/CRITICAL)
    - Originally generated from Alyx database session QC metadata via `one.alyx.rest('sessions', 'read', id=eid)['extended_qc']`
    - Precomputed snapshot cached as fixture file to avoid slow API calls during conversion
  - **Histology QC:** Loaded from `bwm_histology_qc.pqt` fixture
    - Parquet table with columns: `eid`, `pid`, `probe_name`, `histology_quality`, `has_histology_files`
    - Originally generated from Alyx probe insertion metadata via `one.alyx.rest('insertions', 'read', id=pid)['json']['extended_qc']`
    - Quality levels: `'alf'` (best, final processed files exist) > `'resolved'` (good, alignment finalized) > `'aligned'` (partial) > `'traced'` (minimal)
    - Created by [`create_histology_qc_table.py`](../src/ibl_to_nwb/fixtures/create_histology_qc_table.py) script
  - Both fixtures are precomputed snapshots from Alyx REST API that avoid slow database calls during conversion
- **Quality control filters:**
  - **Anatomical localization:** Histology quality must be 'alf' - lower quality alignments excluded (checked in `check_availability()`)
  - **Camera-based data (videos, pose, pupil, ROI):** Video QC filtering - excludes CRITICAL/FAIL videos from `bwm_qc.json` (checked in `check_availability()`)
  - **Pose estimation likelihood filtering:** Additional quality filtering applied during data loading
    - Applied via `SessionLoader.load_pose()` which uses default `likelihood_thr=0.9` parameter
    - Internally calls `likelihood_threshold()` function from brainbox
    - For each body part (e.g., `nose_tip`, `paw_l`), checks the `{bodypart}_likelihood` column
    - If `likelihood < 0.9`, sets both `{bodypart}_x` and `{bodypart}_y` to `NaN` for that frame
    - Example: If `nose_tip_likelihood[100] = 0.7`, then `nose_tip_x[100]` and `nose_tip_y[100]` become `NaN`
    - Likelihood values themselves are still stored in NWB for transparency
    - **Both current branch and Georg's branch use this same 0.9 threshold** - it's the `SessionLoader` default
    - **Note:** This filtering happens during data loading in conversion, not in `check_availability()` (see architectural note below)
  - **All other modalities:** No quality filtering - data either exists or conversion fails (fail-fast principle)
- **Architectural note (difference from Georg's branch - `revision_2`):**
  - **Shared behavior:** Both branches use the same likelihood threshold (0.9) applied via `SessionLoader.load_pose()` during data loading
  - **Key difference - WHEN pose data is loaded:**
    - **Current approach (HeberVto's refactoring):** `check_availability()` checks QC metadata only (video QC status from `bwm_qc.json`), does NOT load pose data
      - Pose data loaded once during conversion in `add_to_nwbfile()`
      - Pros: Fast availability checks (no data loading), clear separation between availability and conversion, data loaded only once
      - Cons: Does not catch corrupted files or format issues until conversion time
    - **Georg's approach (`revision_2` branch):** Used `check_camera_health_by_loading()` which loaded pose data during availability check
      - Pose data loaded twice: once in `check_availability()` via `check_camera_health_by_loading()`, once in `add_to_nwbfile()`
      - Pros: Catches corrupted files, format errors, and loading issues early before conversion starts
      - Cons: Slower (loads data twice), mixes availability logic with data validation, higher memory usage
  - **Design decision:** We prioritized performance and architectural clarity. QC metadata is trusted to be accurate, and any file corruption or format issues will surface during conversion with clear error messages. The likelihood filtering works identically in both approaches.
- **Video QC rationale:** Sessions with CRITICAL or FAIL video quality produce unreliable camera-based analyses. QC filtering ensures high-quality pose tracking, pupil measurements, and motion energy data.
- **Optional modalities** are checked for availability and gracefully excluded if missing:
  - **Always required (100%):** Trials, Wheel, SpikeSorting, AnatomicalLocalization - conversion fails if missing
  - **Mostly available (90-100%):** Licks (~96%), PassiveIntervals (~92%)
  - **Sometimes available (<90%):** PassiveReplay (~68%), PassiveRFM (~68%), camera-based data (36-78% depending on camera view)
  - All optional data uses `check_availability()` before download/conversion to avoid failures
- **Multi-probe sessions:** 294 of 459 sessions (64.1%) have two probes; remaining 165 sessions (35.9%) have single probe
- **All quality sessions use Lightning Pose** - no DLC fallback needed for sessions passing quality requirements

### Temporal Trends in Data Availability

Data availability improved significantly over the project timeline (2019-11-26 to 2023-10-19):

**Body Camera Introduction**
- **First appearance:** 2020-02-18 (body camera added mid-project)
- **Before this date:** 56 sessions (100%) without body camera
- **After this date:** 403 sessions (46.2% with body camera)
- **Overall change:** +18.5% from early to late sessions

**NIDQ File Availability**
- **Overall:** 83.4% (383/459 sessions)
- **Early period** (before 2020-07): 57.3% (59/103 sessions)
- **Mid period** (2020-07 to 2020-12): 87.5% (112/128 sessions)
- **Late period** (2021-01 onwards): 93.0% (212/228 sessions)
- **Overall improvement:** +19.1% from early to late half, reflecting protocol standardization

**Video Infrastructure Improvements**
- **Left camera:** +14.7% improvement (73.5% early → 88.2% late)
- **Right camera:** +7.3% improvement (73.9% early → 81.2% late)
- **Body camera:** +18.5% improvement (31.3% early → 49.8% late)

These temporal patterns reflect the natural maturation of a large-scale neuroscience project: early sessions served as pilot/ramp-up phase while protocols were established, and later sessions benefited from standardized procedures and improved infrastructure. For NWB conversion, this means **checking availability before writing each interface** is critical, as not all modalities are present across all sessions.

### Most Commonly Missing Modalities (Across All 459 Sessions)

1. **Body camera data** (60.1% missing) - roi_motion_energy_body, pose_estimation_body, video_body
2. **Passive replay/RFM** (23.3% missing) - passive_replay, passive_rfm
3. **Right camera data** (22.4% missing) - video_right, pose_estimation_right, pupil_tracking_right, roi_motion_energy_right
4. **Left camera data** (19.2% missing) - video_left, pose_estimation_left, pupil_tracking_left, roi_motion_energy_left
5. **NIDQ files** (16.6% missing) - NIDQ sync signals (optional for raw conversions)

**Key takeaway:** Body camera and passive protocols are the most variable modalities. All other modalities (trials, wheel, spike sorting, anatomical localization, licks) are >95% available.

---

## Major Architecture Differences: Heberto's vs Georg's Branch

This section documents the key architectural differences between the two conversion implementations to preserve design rationale and facilitate understanding of the codebase evolution.

### 1. **Code Organization & Modularity**

| Aspect | Georg's Branch (`revision_2`) | Heberto's Branch (current) |
|--------|-------------------------------|----------------------------|
| **Main conversion file** | Single `bwm_to_nwb.py` (~700 lines) | Modular structure: `conversion/processed.py`, `conversion/raw.py`, `conversion/download.py` |
| **Interface organization** | Interfaces directly called in conversion script | Centralized `conversion/__init__.py` with public API functions |
| **Code reuse** | Helper functions in main file | Separation of concerns: download, conversion, and utilities |
| **Extensibility** | Requires modifying main script | Modular API makes it easy to add/modify interfaces |

**Design rationale (Heberto):** Breaking monolithic conversion into separate modules improves maintainability, testability, and allows team members to work on different parts without conflicts.

---

### 2. **Data Availability Checking**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **Pose estimation check** | `check_camera_health_by_loading()` - loads data | `check_availability()` - metadata check only |
| **Data loading frequency** | Twice (once in check, once in conversion) | Once (only during conversion) |
| **File existence check** | `one.list_datasets()` with pattern matching | `check_availability()` with declarative requirements |
| **Error detection timing** | Early (during planning phase) | Late (during conversion phase) |
| **Performance** | Slower due to defensive loading | Faster due to metadata-only checks |

**Trade-off:** Georg prioritized safety (catch errors early), Heberto prioritized performance (trust QC metadata).

---

### 3. **Interface API Design**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **Data requirements** | Implicit (hardcoded in conversion script) | Explicit (`get_data_requirements()` class method) |
| **Availability API** | Custom functions per modality | Standardized `check_availability()` across all interfaces |
| **Download API** | Integrated with conversion | Separate `download_data()` class method |
| **Parameter passing** | `camera_name`, `revision` passed at runtime | Class-level attributes (`REVISION`, `CAMERA_VIEW`) |

**Example - Georg's approach:**
```python
# Hardcoded file patterns in conversion script
pose_files = one.list_datasets(eid=eid, filename="*.dlc*")
for pose_file in pose_files:
    camera_name = get_camera_name_from_file(pose_file)
    if check_camera_health_by_loading(one, eid, revision):
        data_interfaces.append(IblPoseEstimationInterface(camera_name, one, eid))
```

**Example - Heberto's approach:**
```python
# Declarative requirements in interface class
requirements = IblPoseEstimationInterface.get_data_requirements(camera_name)
if IblPoseEstimationInterface.check_availability(one, eid, camera_name)["available"]:
    data_interfaces.append(IblPoseEstimationInterface(camera_name, one, eid))
```

**Design rationale (Heberto):** Explicit API contract makes requirements self-documenting and enables automated tooling (dependency analysis, download planning).

---

### 4. **Quality Control Integration**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **QC check location** | Inline in conversion script | Encapsulated in `check_availability()` methods |
| **QC logic visibility** | Scattered across conversion code | Centralized in interface classes |
| **Adding new QC** | Modify conversion script | Modify interface `check_availability()` |
| **Histology QC** | Not explicitly checked | Pre-computed `bwm_histology_qc.pqt` with structured checks |

**Design rationale (Heberto):** Encapsulating QC in interfaces follows single-responsibility principle - each interface knows its own quality requirements.

---

### 5. **Revision Handling**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **Revision specification** | Parameter passed through function calls (`revision=None` by default) | Class-level `REVISION = "2025-05-06"` constant |
| **Dynamic vs Fixed** | Uses `one.list_revisions(session)[-1]` if `revision=None` (latest available) | Always uses fixed "2025-05-06" (BWM standard) |
| **Revision consistency** | Can vary per session if not specified | Guaranteed identical across all sessions |
| **Reproducibility** | Different researchers may get different revisions | All researchers get identical data version |
| **Flexibility** | Can override per session (e.g., special case for one EID) | Must change class attribute to use different revision |

**Trade-off:** Georg's approach is more flexible (can use latest data), Heberto's approach ensures reproducibility (pin to specific BWM release for published dataset).

**Design rationale (Heberto):** Fixed revision guarantees that all 459 sessions use the same data version, ensuring consistency across the entire NWB dataset and enabling reproducible science.

---

### 6. **Error Handling Philosophy**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **Availability check errors** | Broad `except:` catches all exceptions → returns `False` | No try-except - let exceptions propagate with context |
| **Missing data** | Returns boolean only (`True`/`False`) | Returns dict with reason (`{"available": False, "reason": "..."}`) |
| **Corrupted files** | Caught early but reason unknown (silent) | Surface during conversion with full error context |
| **Error diagnostics** | "Data unavailable" (no details why) | Explicit reason: "Video quality control failed: CRITICAL" |
| **Debugging** | Must re-run to find root cause | Error message identifies exact problem |

**Example - Georg's approach (silent fallback):**
```python
def check_camera_health_by_loading(one, session, revision):
    try:
        session_loader = SessionLoader(one, session, revision)
        session_loader.load_pose(tracker='lightningPose')
        return True
    except:  # Catches ALL exceptions - network errors, file corruption, missing files, etc.
        return False  # User only knows "False" - no idea WHY it failed
```

**Problems with silent fallback:**
- Missing file → `False` (no error message)
- Network timeout → `False` (no error message)
- Corrupted file → `False` (no error message)
- Wrong revision → `False` (no error message)

All different problems look identical!

**Example - Heberto's approach (explicit errors):**
```python
@classmethod
def check_availability(cls, one, eid, camera_name):
    # Video QC check - explicit reason
    if video_qc_status in ['CRITICAL', 'FAIL']:
        return {
            "available": False,
            "reason": f"Video quality control failed: {video_qc_status}",
            "qc_status": video_qc_status
        }

    # File existence check - explicit reason
    files_exist = check_files_exist(...)
    if not files_exist:
        return {
            "available": False,
            "reason": "Required pose estimation files not found",
            "missing_files": [...]
        }
```

**Benefits of explicit errors:**
- Missing file → Clear message: "Required pose estimation files not found"
- Bad QC → Clear message: "Video quality control failed: CRITICAL"
- Can distinguish between different failure modes
- Enables automated retry logic (e.g., retry network errors but not QC failures)

**Design rationale (Heberto):** Structured error reporting with explicit reasons enables better diagnostics, faster debugging, and automated error recovery strategies.

---

### 7. **AWS Deployment Infrastructure**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **AWS support** | Not present | Complete `_aws_run/` infrastructure |
| **EC2 automation** | Manual | `launch_ec2_instances.py` with auto-configuration |
| **Session distribution** | Manual splitting | Automatic shard assignment via IMDSv2 tags |
| **Monitoring** | Manual | `monitor.py` with real-time progress tracking |
| **Error recovery** | Manual intervention | `tracking.json` for restart capability |

**New capabilities (Heberto):**
- Automated EC2 fleet launching with proper networking
- Session shard assignment (e.g., "0-13" for 459 sessions / 35 instances)
- Real-time monitoring and log aggregation
- DANDI upload verification pipeline
- Cost analysis and optimization tools

---

### 8. **Testing & Validation**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **Stub mode** | Basic duration limiting | Comprehensive stub testing with cache-awareness |
| **Diagnostics** | Inline logging | Dedicated `diagnose_session_data_availability.py` |
| **Consistency checks** | Not present | `check_nwbfile_for_consistency()` comparing NWB vs ONE |
| **ONE API patches** | Not present | `one_patches.py` fixing cache validation issues |

---

### 9. **Documentation**

| Aspect | Georg's Branch | Heberto's Branch |
|--------|----------------|------------------|
| **Modality documentation** | Not present | This comprehensive `conversion_modalities.md` |
| **Architecture rationale** | In code comments | Explicit documentation sections |
| **QC sources** | Undocumented | Documented with Alyx REST API origins |
| **Design decisions** | Implicit | Explicit with trade-offs explained |

---

### Summary: Complementary Strengths

- **Georg's approach:** Defensive, safety-first, catches edge cases early, proven in production
- **Heberto's approach:** Modular, scalable, performance-optimized, better architectural separation, production-ready AWS infrastructure

Both approaches successfully convert the IBL Brain-Wide Map dataset to NWB. The current branch builds on Georg's foundation while refactoring for production-scale deployment (459 sessions × 2 files = 918 NWB files) on AWS infrastructure.

---

## Session and Subject Metadata

**Fetch:**
```python
session_metadata = one.alyx.rest("sessions", "list", id=eid)[0]
lab_metadata = one.alyx.rest("labs", "list", name=session_metadata["lab"])[0]
subject_metadata = one.alyx.rest("subjects", "list", nickname=session_metadata["subject"])[0]
```

**Includes:** Session start time, lab, institution, task protocol, subject demographics, water restriction info

---

## Data Loading Philosophy

All modalities follow a **fail-fast principle**: data either exists or conversion fails with clear error messages. There are no silent fallbacks or quality compromises:

- **Required modalities** (trials, wheel, spike sorting, etc.) will fail conversion if data is missing
- **Optional modalities** (passive protocols, licks, cameras) are checked for availability and gracefully excluded if missing
- **No silent quality degradation** - we don't fall back to lower-quality alternatives
- **Lightning Pose only** - all quality sessions in BWM dataset use Lightning Pose; no DLC fallback needed

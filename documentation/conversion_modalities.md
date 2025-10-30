# IBL to NWB Conversion Modalities

This document describes the data modalities converted by the IBL to NWB conversion script and how they are fetched from the ONE API.

## Overview

Two NWB file types are generated:
- **RAW** - Raw electrophysiology and videos
- **PROCESSED** - Spike-sorted data, behavioral data, and video-based tracking

---

## RAW Conversion Summary

| Modality | Sub-type | Files & Method of Loading Data | Quality Control Filters | Availability (BWM Dataset) |
|----------|----------|--------------------------------|------------------------|---------------------------|
| **Raw Electrophysiology** | Per probe (probe00, probe01) | `raw_ephys_data/probe*/*.ap.cbin`, `*.lf.cbin`, `*.ap.meta`, `*.ap.ch`<br>Downloaded via ONE API during download script | None | 100% (459/459 sessions)<br>**Multi-probe:** 294 sessions (64.1%)<br>**Single-probe:** 165 sessions (35.9%) |
| **Anatomical Localization** | Per probe (probe00, probe01) | `alf/probe*/channels.localCoordinates.npy`<br>`alf/probe*/channels.mlapdv.npy`<br>`alf/probe*/channels.brainLocationIds_ccf_2017.npy`<br>`alf/probe*/electrodeSites.*`<br>**Method:** `SpikeSortingLoader` (brainbox) | **Histology quality must be 'alf' or 'resolved'**<br>Lower quality alignments excluded | 100% (459/459 sessions)<br>**Multi-probe:** 294 sessions (64.1%)<br>**Single-probe:** 165 sessions (35.9%) |
| **Raw Video** | leftCamera | `raw_video_data/_iblrig_leftCamera.raw.mp4`<br>`alf/_ibl_leftCamera.times.npy`<br>**Method:** `one.load_dataset()` (video), `one.load_object()` (timestamps) | **Video QC: excludes CRITICAL/FAIL** | 95.2% (437/459 sessions) |
| **Raw Video** | rightCamera | `raw_video_data/_iblrig_rightCamera.raw.mp4`<br>`alf/_ibl_rightCamera.times.npy`<br>**Method:** `one.load_dataset()` (video), `one.load_object()` (timestamps) | **Video QC: excludes CRITICAL/FAIL** | 94.3% (433/459 sessions) |
| **Raw Video** | bodyCamera | `raw_video_data/_iblrig_bodyCamera.raw.mp4`<br>`alf/_ibl_bodyCamera.times.npy`<br>**Method:** `one.load_dataset()` (video), `one.load_object()` (timestamps) | **Video QC: excludes CRITICAL/FAIL** | 56.6% (260/459 sessions) |

---

## PROCESSED Conversion Summary

| Modality | Sub-type | Files & Method of Loading Data | Quality Control Filters | Availability (BWM Dataset) |
|----------|----------|--------------------------------|------------------------|---------------------------|
| **Spike Sorting** | Per probe (probe00, probe01) | `alf/probe*/spikes.times.npy`, `spikes.clusters.npy`, `spikes.amps.npy`, `spikes.depths.npy`<br>`alf/probe*/clusters.channels.npy`, `clusters.depths.npy`, `clusters.metrics.pqt`, `clusters.uuids.csv`<br>**Method:** `SpikeSortingLoader` (brainbox)<br>**Revision:** `2024-05-06` | None | 100% (459/459 sessions)<br>**Multi-probe:** 294 sessions (64.1%)<br>**Single-probe:** 165 sessions (35.9%) |
| **Behavioral Trials** | - | 13 trial files: `alf/trials.intervals.npy`, `trials.choice.npy`, `trials.feedbackType.npy`, etc.<br>**Method:** `SessionLoader.load_trials()` (brainbox)<br>**Revision:** `2024-05-06` | None | 100% (459/459 sessions) |
| **Wheel Movement** | - | `alf/wheel.position.npy`, `wheel.timestamps.npy`<br>`alf/wheelMoves.intervals.npy`, `wheelMoves.peakAmplitude.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2024-05-06` | None | 100% (459/459 sessions) |
| **Passive Intervals** | - | `alf/_ibl_passivePeriods.intervalsTable.csv`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2024-05-06` | None | 92.4% (424/459 sessions) |
| **Passive Replay Stimuli** | - | `alf/_ibl_passiveStims.table.csv`<br>`alf/_ibl_passiveGabor.table.csv`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2024-05-06` | None | 76.7% (352/459 sessions) |
| **Passive RFM** | - | `alf/_ibl_passiveRFM.times.npy`<br>`raw_passive_data/_iblrig_RFMapStim.raw.bin`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2024-05-06` | None | 76.7% (352/459 sessions) |
| **Lick Detection** | - | `alf/licks.times.npy`<br>**Method:** `one.load_dataset()`<br>**Revision:** `2024-05-06` | None | 96.5% (443/459 sessions) |
| **Pose Estimation** | leftCamera | `alf/_ibl_leftCamera.lightningPose.pqt`<br>**Method:** `SessionLoader`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**Likelihood threshold ≥ 0.9** (low-confidence → NaN) | 95.4% (438/459 sessions) |
| **Pose Estimation** | rightCamera | `alf/_ibl_rightCamera.lightningPose.pqt`<br>**Method:** `SessionLoader`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**Likelihood threshold ≥ 0.9** (low-confidence → NaN) | 94.3% (433/459 sessions) |
| **Pose Estimation** | bodyCamera | `alf/_ibl_bodyCamera.lightningPose.pqt`<br>**Method:** `SessionLoader`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL**<br>**Likelihood threshold ≥ 0.9** (low-confidence → NaN) | 56.6% (260/459 sessions) |
| **Pupil Tracking** | leftCamera | `alf/_ibl_leftCamera.features.pqt`<br>`alf/_ibl_leftCamera.times.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL** | 95.2% (437/459 sessions) |
| **Pupil Tracking** | rightCamera | `alf/_ibl_rightCamera.features.pqt`<br>`alf/_ibl_rightCamera.times.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL** | 94.3% (433/459 sessions) |
| **ROI Motion Energy** | leftCamera | `alf/_ibl_leftCamera.ROIMotionEnergy.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL** | 95.2% (437/459 sessions) |
| **ROI Motion Energy** | rightCamera | `alf/_ibl_rightCamera.ROIMotionEnergy.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL** | 94.3% (433/459 sessions) |
| **ROI Motion Energy** | bodyCamera | `alf/_ibl_bodyCamera.ROIMotionEnergy.npy`<br>**Method:** `one.load_object()`<br>**Revision:** `2024-05-06` | **Video QC: excludes CRITICAL/FAIL** | 55.8% (256/459 sessions) |

**Notes:**
- **Revision `2024-05-06`** is the Brain-Wide Map standard, set via class-level `REVISION` attribute in each interface
- **Quality control filters:**
  - **Anatomical localization:** Histology quality must be 'alf' or 'resolved' - lower quality alignments excluded
  - **Camera-based data (videos, pose, pupil, ROI):** Video QC filtering - excludes CRITICAL/FAIL videos from `bwm_qc.json`
  - **Pose estimation:** Additional likelihood threshold ≥ 0.9 applied via `SessionLoader` - low-confidence body part estimates set to NaN
  - **All other modalities:** No quality filtering - data either exists or conversion fails (fail-fast principle)
- **Video QC rationale:** Sessions with CRITICAL or FAIL video quality produce unreliable camera-based analyses. QC filtering ensures high-quality pose tracking, pupil measurements, and motion energy data.
- **Optional modalities** (passive protocols, licks) are checked for availability and excluded if missing
- **Multi-probe sessions:** 294 of 459 sessions (64.1%) have two probes; remaining 165 sessions (35.9%) have single probe
- **All quality sessions use Lightning Pose** - no DLC fallback needed for sessions passing quality requirements

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

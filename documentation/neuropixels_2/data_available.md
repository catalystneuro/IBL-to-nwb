# Neuropixels 2.0 Development Data

## Session Information

| Field | Value |
|-------|-------|
| Subject | KM_038 |
| Lab | steinmetzlab |
| Date | 2025-05-19 |
| Session | 001 |
| Total Size | 187 GB |
| Path | `/media/heberto/Expansion/ibl_cache/steinmetzlab/Subjects/KM_038/2025-05-19/001/` |

## Probe Configuration

This session uses **NP2.4** (Neuropixels 2.0 4-shank) probes. The session contains 3 physical probes, each with 4 shanks, resulting in 12 virtual probes:

| Physical Probe | Serial Number | Shanks |
|---------------|---------------|--------|
| probe00 | 22420022291 | a, b, c, d |
| probe01 | 19122510753 | a, b, c, d |
| probe02 | 22420019583 | a, b, c, d |

## Key Difference from Neuropixels 1.0

In standard Neuropixels 1.0 recordings, all channel data is stored in a single compressed file per probe. For Neuropixels 2.0 multi-shank probes, the IBL data pipeline stores **compressed data separately for each shank**.

### File Organization

```
raw_ephys_data/
    probe00a/
        _spikeglx_ephysData_g0_t0.imec0.ap.cbin   # AP band for shank a
        _spikeglx_ephysData_g0_t0.imec0.ap.meta
        _spikeglx_ephysData_g0_t0.imec0.lf.cbin   # LF band for shank a
    probe00b/
        _spikeglx_ephysData_g0_t0.imec0.ap.cbin   # AP band for shank b
        ...
    probe00c/
        ...
    probe00d/
        ...
    probe01a/
        _spikeglx_ephysData_g0_t0.imec1.ap.cbin   # Different imec index
        ...
    ...
```

Note: The `.meta` files share the same imec index within a physical probe (e.g., all probe00 shanks use `imec0`), but each shank has its own compressed binary file (`.cbin`).

## Raw Ephys Data Sizes (per shank)

| Shank | Size |
|-------|------|
| probe00a | 11 GB |
| probe00b | 11 GB |
| probe00c | 12 GB |
| probe00d | 11 GB |
| probe01a | 15 GB |
| probe01b | 16 GB |
| probe01c | 16 GB |
| probe01d | 16 GB |
| probe02a | 12 GB |
| probe02b | 12 GB |
| probe02c | 12 GB |
| probe02d | 12 GB |

## NIDQ Data

The session also includes NIDQ (National Instruments DAQ) synchronization data:

- `_spikeglx_ephysData_g0_t0.nidq.cbin` (277 MB)
- `_spikeglx_ephysData_g0_t0.nidq.meta`
- `_spikeglx_ephysData_g0_t0.nidq.wiring.json`
- Sync files: `_spikeglx_sync.{channels,polarities,times}.npy`

## Processed Data (ALF)

The session contains processed ALF data organized in the `alf/` folder.

### Data Availability Summary

| Data Source | Available | Location | Notes |
|-------------|-----------|----------|-------|
| **Raw Ephys (AP)** | YES | `raw_ephys_data/probe*/*.ap.cbin` | 12 shanks, 30 kHz |
| **Raw Ephys (LF)** | YES | `raw_ephys_data/probe*/*.lf.cbin` | 12 shanks, 2.5 kHz |
| **NIDQ (sync)** | YES | `raw_ephys_data/*.nidq.{cbin,meta,wiring.json}` | Behavioral sync |
| **Spike Sorting** | YES | `alf/probe*/iblsorter/` | Full iblsorter output per shank |
| **Waveforms** | YES | `alf/probe*/iblsorter/waveforms.*` | Templates and traces |
| **Pose Estimation** | YES | `alf/_ibl_*Camera.lightningPose.pqt` | All 3 cameras |
| **Camera Times** | YES | `alf/_ibl_*Camera.times.npy` | All 3 cameras |
| **ROI Motion Energy** | YES | `alf/*Camera.ROIMotionEnergy.npy` | All 3 cameras |
| **Licks** | YES | `alf/licks.times.npy` | Lick detection times |
| **Wheel Position** | YES | `alf/task_00/_ibl_wheel.{position,timestamps}.npy` | Rotary encoder |
| **Wheel Moves** | YES | `alf/task_00/_ibl_wheelMoves.*` | Movement intervals |
| **Trials** | YES | `alf/task_00/_ibl_trials.table.pqt` | Behavioral trials |
| **Raw Videos** | NO | - | Not downloaded/available |
| **Anatomical Localization** | NO | - | No histology data yet |

### Detailed File Listings

#### Pose Estimation (Lightning Pose)
```
alf/_ibl_bodyCamera.lightningPose.pqt    (3.3 MB)
alf/_ibl_leftCamera.lightningPose.pqt    (139 MB)
alf/_ibl_rightCamera.lightningPose.pqt   (322 MB)
```

#### Camera Timestamps
```
alf/_ibl_bodyCamera.times.npy    (1.1 MB)
alf/_ibl_leftCamera.times.npy    (2.3 MB)
alf/_ibl_rightCamera.times.npy   (5.6 MB)
```

#### ROI Motion Energy
```
alf/bodyCamera.ROIMotionEnergy.npy   (1.1 MB)
alf/leftCamera.ROIMotionEnergy.npy   (2.3 MB)
alf/rightCamera.ROIMotionEnergy.npy  (5.6 MB)
```

#### Behavioral Data (task_00)
```
alf/task_00/_ibl_trials.table.pqt
alf/task_00/_ibl_trials.goCueTrigger_times.npy
alf/task_00/_ibl_trials.stimOff_times.npy
alf/task_00/_ibl_trials.stimOnTrigger_times.npy
alf/task_00/_ibl_wheel.position.npy      (9.8 MB)
alf/task_00/_ibl_wheel.timestamps.npy    (9.8 MB)
alf/task_00/_ibl_wheelMoves.intervals.npy
alf/task_00/_ibl_wheelMoves.peakAmplitude.npy
```

#### Spike Sorting (per shank, example: probe00a)
```
alf/probe00a/iblsorter/
    spikes.times.npy           (17.7 MB)
    spikes.clusters.npy        (4.4 MB)
    spikes.amps.npy            (8.9 MB)
    spikes.depths.npy          (8.9 MB)
    clusters.metrics.pqt
    clusters.waveforms.npy     (2.2 MB)
    waveforms.traces.npy       (1.4 GB)  # Full waveform traces
    waveforms.table.pqt
    waveforms.templates.npy
    channels.localCoordinates.npy
    channels.rawInd.npy
```

### Missing Data Sources

#### Raw Videos
The `raw_video_data/` folder does not exist. Video files (`.mp4`) are not available on the server yet. The experiment description indicates cameras were configured:
- Body camera: 640x512 @ 30 fps
- Left camera: 1280x1024 @ 60 fps
- Right camera: 640x512 @ 150 fps

#### Anatomical Localization
No histology/trajectory data is available:
- No `channels.brainLocationIds_ccf_2017.npy`
- No `channels.mlapdv.npy`
- No `probeTrajectory.*` files

This data requires histology processing which may not be complete for this session.

## Tasks Configuration

From `_ibl_experiment.description.yaml`:
```yaml
tasks:
- _iblrig_tasks_ephysChoiceWorld:
    collection: raw_task_data_00
    sync_label: bpod
- _iblrig_tasks_passiveChoiceWorld:
    collection: raw_task_data_01
    sync_label: bpod
```

The session has two task phases:
1. **ephysChoiceWorld** - Active behavioral task
2. **passiveChoiceWorld** - Passive visual stimulation

## Development Considerations

When implementing NWB conversion for Neuropixels 2.0:

1. The converter must handle per-shank file organization rather than a single file per probe
2. Each shank should be treated as a separate recording device in NWB
3. The probe geometry and channel mappings differ from NP1.0
4. Spike sorting data is organized by shank, not by physical probe
5. Pose estimation data is available and can be included (Lightning Pose)
6. NIDQ sync data is available for temporal alignment
7. Raw videos are NOT available - skip video interfaces
8. Anatomical localization is NOT available - skip brain region annotations

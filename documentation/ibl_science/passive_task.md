# IBL Passive Task Documentation

## Overview

The **IBL Passive Task** is a critical experimental protocol that occurs after the main behavioral task in Brain Wide Map (BWM) sessions. It's designed to characterize neural responses to sensory stimuli without behavioral demands, providing essential baseline measurements for understanding brain function.

## Scientific Purpose

**Why the Passive Task Matters:**
- **Functional Brain Mapping**: Identifies sensory response properties across brain regions
- **Task vs. Passive Comparison**: Reveals how behavioral engagement modulates neural responses
- **Receptive Field Characterization**: Maps spatial visual preferences of neurons
- **Baseline Neural Activity**: Provides spontaneous activity measurements
- **Cross-modal Integration**: Studies interactions between visual and auditory processing

## Experimental Design

### Timeline Structure
```
[Main 2AFC Task] → [Passive Protocol]
                   ↓
[Spontaneous] → [RFM] → [Task Replay] → [Spontaneous]
   Period         Grid    (Visual +      Period
                  Stim.   Auditory)
```

### Session Context
- **When**: Immediately follows the main decision-making task
- **Duration**: Typically 10-20 minutes total
- **Animal State**: Animal remains head-fixed but behaviorally passive
- **Recording**: Continuous neural recording throughout

## Three Main Protocol Components

### 1. **Spontaneous Activity (SP)**

**Purpose**: Record baseline neural activity without external stimulation

**Protocol**:
- **Duration**: Several minutes of quiet periods
- **Conditions**: No visual or auditory stimuli
- **Environment**: Gray screen, minimal environmental stimulation

**Scientific Value**:
- Intrinsic neural dynamics and correlations
- Baseline firing rates across brain regions
- Resting-state network activity

**Data Files**:
- Primary: `_ibl_passivePeriods.intervalsTable.csv`
- Contains start/stop times for spontaneous periods

### 2. **Receptive Field Mapping (RFM)**

**Purpose**: Map visual receptive fields across recorded neurons

**Visual Stimulus Protocol**:
- **Stimulus**: Small squares (pixels) on a grid
- **Colors**: White squares (ON) and black squares (OFF) on gray background
- **Grid**: 15×15 pixel array covering central visual field
- **Timing**: ~60 Hz presentation rate
- **Pattern**: Systematic coverage of visual space

**Technical Details**:
- Screen: iPad positioned in front of animal
- Synchronization: Frame2TTL signals for precise timing
- Coverage: Central ~30° of visual field

**Scientific Applications**:
- Visual receptive field mapping
- Center-surround organization
- ON/OFF response characterization
- Retinotopic organization analysis

**Data Files**:
- Timing: `_ibl_passiveRFM.times.npy`
- Stimulus data: `_iblrig_RFMapStim.raw.bin` (15×15×n_frames array)

### 3. **Task Replay (TR)**

**Purpose**: Present task stimuli without behavioral demands for comparison

#### Visual Component: Gabor Patches
- **Stimuli**: Same Gabor patches used in main task
- **Parameters**: Various contrasts, positions, and spatial phases
- **Purpose**: Compare task-engaged vs. passive visual responses

#### Auditory Component: Sounds
- **Go Cue Tones**: Same tone frequencies used in main task
- **Noise Bursts**: White noise stimuli
- **Purpose**: Compare task-engaged vs. passive auditory responses

**Scientific Value**:
- Task modulation effects on sensory responses
- Attention-dependent neural changes
- Context-dependent processing

**Data Files**:
- Visual events: `_ibl_passiveGabor.table.csv`
- Auditory events: `_ibl_passiveStims.table.csv`

## IBL-to-NWB Conversion Interface

The conversion to NWB format is handled by the `PassivePeriodDataInterface` and its sub-interfaces:

### Main Interface: `PassivePeriodDataInterface`

**Purpose**: Detects available passive datasets and coordinates conversion

**Datasets Checked**:
| Dataset | File | Purpose | Required |
|---------|------|---------|----------|
| `has_passive` | `_ibl_passivePeriods.intervalsTable.csv` | Epoch timing | No |
| `has_replay` | `_ibl_passiveGabor.table.csv` | Visual task replay | No |
| `has_rfm` | `_ibl_passiveRFM.times.npy` | Receptive field mapping | No |

**Additional Files Loaded**:
- `_ibl_passiveStims.table.csv` - Auditory task replay events
- `_iblrig_RFMapStim.raw.bin` - RFM stimulus position data

### Sub-Interfaces and NWB Conversion

#### 1. `PassiveEpochsInterface`
**Converts**: Passive period timing → NWB Epochs

**Source Data**: `_ibl_passivePeriods.intervalsTable.csv`

**NWB Output**:
- **Location**: `nwbfile.epochs` table
- **Epochs Created**:
  - `"experiment"` (normal): 0.0 to start of passive protocol
  - `"spontaneousActivity"` (passive): Spontaneous periods
  - `"RFM"` (passive): Receptive field mapping period
  - `"taskReplay"` (passive): Task replay period

**Custom Columns**:
- `protocol_type`: "normal" or "passive"
- `protocol_name`: Specific protocol identifier

#### 2. `TaskReplayInterface`
**Converts**: Task replay events → NWB TimeIntervals

**Source Data**:
- `_ibl_passiveStims.table.csv` (auditory events)
- `_ibl_passiveGabor.table.csv` (visual events)

**NWB Output**:
- **Location**: `passive` processing module
- **Tables Created**:

**Passive Stimulation Table** (`passive_task_replay`):
- Auditory events: valve clicks, tones, noise bursts
- Columns: `start_time`, `stop_time`, `stim_type`
- `stim_type` values: "valve", "tone", "noise"

**Gabor Events Table** (`gabor_table`):
- Visual Gabor patch presentations
- Columns: `start_time`, `stop_time`, `position`, `contrast`, `phase`

#### 3. `ReceptiveFieldMappingInterface`
**Converts**: RFM data → NWB TimeSeries

**Source Data**:
- `_ibl_passiveRFM.times.npy` (timestamps)
- `_iblrig_RFMapStim.raw.bin` (stimulus data)

**NWB Output**:
- **Location**: `passive` processing module
- **Object**: `rfm_stim` TimeSeries
- **Data**: 15×15 pixel grid stimulus patterns over time
- **Timestamps**: Frame presentation times
- **Unit**: "px" (pixels)

## Data Analysis Applications

### Spontaneous Activity Analysis
```python
# Load passive epochs and find spontaneous periods
epochs = nwbfile.epochs.to_dataframe()
spont_epochs = epochs[epochs['protocol_name'] == 'spontaneousActivity']

# Analyze neural activity during spontaneous periods
spont_start = spont_epochs['start_time'].iloc[0]
spont_stop = spont_epochs['stop_time'].iloc[0]
spont_spikes = spikes[(spikes['times'] >= spont_start) & (spikes['times'] <= spont_stop)]
```

### Receptive Field Mapping
```python
# Load RFM stimulus data
rfm_stim = nwbfile.processing['passive']['rfm_stim']
stim_data = rfm_stim.data[:]  # Shape: (n_frames, 15, 15)
stim_times = rfm_stim.timestamps[:]

# Compute receptive fields
from brainbox.task.passive import get_on_off_times_and_positions
rf_times, rf_positions, rf_frames = get_on_off_times_and_positions(rfm_data)
```

### Task vs. Passive Comparison
```python
# Load task replay events
passive_gabors = nwbfile.processing['passive']['gabor_table'].to_dataframe()

# Compare responses to same stimulus in different contexts
task_responses = analyze_task_gabor_responses(spikes, trials)
passive_responses = analyze_passive_gabor_responses(spikes, passive_gabors)
modulation_index = (task_responses - passive_responses) / (task_responses + passive_responses)
```

## File Structure Summary

### Original IBL Data
```
alf/
├── _ibl_passivePeriods.intervalsTable.csv    # Epoch timing
├── _ibl_passiveRFM.times.npy                 # RFM timestamps
├── _ibl_passiveGabor.table.csv               # Visual task replay
└── _ibl_passiveStims.table.csv               # Auditory task replay

raw_passive_data/
└── _iblrig_RFMapStim.raw.bin                 # RFM stimulus data
```

### NWB Conversion Output
```
NWBFile
├── epochs                           # Passive period timing
│   ├── experiment (normal)
│   ├── spontaneousActivity (passive)
│   ├── RFM (passive)
│   └── taskReplay (passive)
└── processing
    └── passive                      # Passive stimulation module
        ├── passive_task_replay      # Auditory events table
        ├── gabor_table             # Visual events table
        └── rfm_stim                # RFM stimulus timeseries
```

## Technical Implementation Notes

### Data Availability
- **Optional**: All passive datasets are optional - conversion handles missing data gracefully
- **Detection**: Interface checks for file presence before attempting to load
- **Fallback**: Missing components are skipped without errors

### Timing Precision
- All timestamps synchronized to electrophysiology recording clock
- Frame2TTL signals ensure precise visual stimulus timing
- Audio events aligned to FPGA timing system

### Data Integrity
- RFM data reshaped to (n_frames, 15, 15) array for analysis
- Event sorting by start time for chronological organization
- Custom NWB columns preserve original data relationships

## Scientific Applications

The IBL Passive Task data enables:

1. **Sensory Processing Studies**: Understanding how brain regions respond to visual and auditory stimuli
2. **Attention Research**: Comparing neural responses during engaged vs. passive states
3. **Functional Mapping**: Identifying receptive field properties across brain areas
4. **Network Analysis**: Studying spontaneous correlations and intrinsic connectivity
5. **Individual Differences**: Characterizing variation in sensory processing across animals
6. **Development Studies**: Tracking changes in sensory responses over time

The conversion to NWB format preserves all essential information while providing standardized access for computational analysis and data sharing across the neuroscience community.
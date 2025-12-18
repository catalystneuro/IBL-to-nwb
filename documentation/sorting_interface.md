# IBL Sorting Interface Documentation

This document provides comprehensive documentation for the `IblSortingInterface`, which handles the conversion of IBL spike-sorted electrophysiology data to NWB format.

## Table of Contents

1. [Overview](#overview)
2. [Spike Sorting Background](#spike-sorting-background)
   - [What is Spike Sorting?](#what-is-spike-sorting)
   - [IBL Spike Sorting Pipeline](#ibl-spike-sorting-pipeline)
   - [Quality Control Metrics](#quality-control-metrics)
3. [Units Table Columns Reference](#units-table-columns-reference)
4. [Data Extraction with ibllib](#data-extraction-with-ibllib)
5. [Interface Implementation](#interface-implementation)
6. [References](#references)

---

## Overview

The `IblSortingInterface` converts spike-sorted electrophysiology data from IBL Neuropixels recordings into the NWB units table format. This interface handles data from the standardized IBL spike sorting pipeline (iblsorter/pykilosort), ensuring consistent representation of neural activity across all Brain-Wide Map sessions.

**Key characteristics:**
- Adds ~20 columns to the NWB units table (spike times + quality metrics + metadata)
- Supports multi-probe sessions with automatic unit ID management
- Uses revision `2025-05-06` for Brain-Wide Map standard data
- Links units to electrodes table for anatomical localization
- Available for 100% of the 459 BWM sessions (all sessions have spike sorting)

---

## Spike Sorting Background

### What is Spike Sorting?

Spike sorting is the computational process of identifying and classifying action potentials (spikes) from extracellular electrophysiology recordings. The goal is to:

1. **Detect spikes**: Identify voltage deflections that represent neural action potentials
2. **Extract features**: Characterize each spike by its waveform shape across channels
3. **Cluster spikes**: Group spikes from the same neuron based on waveform similarity
4. **Assign identities**: Label each cluster as a putative single neuron (unit)

The result is a set of "units" - each representing the activity of a single (or small group of) neurons - with associated spike times and quality metrics.

### IBL Spike Sorting Pipeline

IBL uses a standardized spike sorting pipeline based on Kilosort 2.5:

| Component | Details |
|-----------|---------|
| **Algorithm** | iblsorter (formerly pykilosort) - Python implementation of Kilosort 2.5 |
| **Probe type** | Neuropixels 1.0 (384 recording channels, 10 reference channels) |
| **Sampling rate** | 30 kHz |
| **High-pass filter** | 300 Hz cutoff for spike detection |
| **Drift correction** | IBL-specific optimizations for chronic recordings |
| **Curation** | Fully automated (no manual curation) |

#### Processing Steps

```
Raw Data → Preprocessing → Spike Detection → Feature Extraction → Clustering → Quality Metrics
   ↓            ↓               ↓                  ↓                 ↓              ↓
 .cbin      Filtering      Threshold         PCA/Template        Kilosort      IBL metrics
           Whitening       Detection          Matching           Algorithm     + labeling
           CAR
```

1. **Preprocessing**: Common average referencing (CAR), whitening, high-pass filtering
2. **Spike Detection**: Threshold-based detection on whitened data
3. **Feature Extraction**: Template matching with learned spike templates
4. **Clustering**: Iterative template matching and merging (Kilosort algorithm)
5. **Quality Metrics**: Automated quality assessment (no manual curation)

### Quality Control Metrics

IBL uses three primary metrics to determine unit quality, following the methodology described in the [IBL spike sorting white paper](https://doi.org/10.6084/m9.figshare.19705522):

#### 1. Sliding Refractory Period Violation (slidingRP_viol)

Tests whether the unit has an acceptable level of refractory period violations using a sliding threshold approach.

| Aspect | Details |
|--------|---------|
| **Method** | Hill et al. (2011) sliding refractory period algorithm |
| **Rationale** | Accounts for firing rate when assessing violations |
| **Pass criterion** | Less than maximum contamination at any refractory period value |
| **Note** | Low firing rate units will fail regardless of violations |

#### 2. Noise Cutoff

Determines whether the amplitude distribution is truncated (spikes missing due to detection threshold).

| Aspect | Details |
|--------|---------|
| **Method** | Compare lower quartile to upper quartile statistics |
| **Rationale** | Gaussian assumption-free test for amplitude floor |
| **Pass criterion** | Lower quartile within acceptable distance from upper quartile mean |

#### 3. Amplitude Threshold

Simple threshold on median spike amplitude.

| Aspect | Details |
|--------|---------|
| **Threshold** | 50 uV median amplitude |
| **Rationale** | Ensures unit is distinguishable from noise |

#### Quality Labels

IBL provides **two complementary quality labels** for each unit:

##### 1. IBL Quality Score (`ibl_quality_score`)

The `ibl_quality_score` column indicates the proportion of IBL's quality metrics passed:

| Label Value | Interpretation | Common Usage |
|-------------|----------------|--------------|
| 1.0 | All 3 metrics passed | "Good" unit - high confidence single neuron |
| 0.67 | 2 of 3 metrics passed | Intermediate quality |
| 0.33 | 1 of 3 metrics passed | Low quality |
| 0.0 | No metrics passed | "Noise" or multi-unit activity |

##### 2. Kilosort2 Label (`kXilosort2_label`)

The `kilosort2_label` column contains the original classification from the Kilosort2 spike sorting algorithm:

| Label Value | Interpretation |
|-------------|----------------|
| `"good"` | Well-isolated single unit (high waveform similarity, low contamination) |
| `"mua"` | Multi-unit activity (multiple neurons merged into one cluster) |
| `"noise"` | Non-neural activity (artifacts, electrical noise) |

**Relationship between labels**: The `kilosort2_label` is Kilosort's initial classification, while `ibl_quality_score` is IBL's standardized post-processing score. They may disagree - for example, a unit labeled "good" by Kilosort might have `ibl_quality_score=0.67` if it fails one of IBL's stricter quality metrics. Both are provided to allow users to choose their preferred filtering criteria.

---

## Units Table Columns Reference

The interface adds the following columns to the NWB units table. Each column includes detailed descriptions of what the metric measures, the intuition behind it, and whether it's available in [SpikeInterface](https://spikeinterface.readthedocs.io/en/stable/modules/qualitymetrics.html).

### Quick Reference Table

| NWB Column | Category | SpikeInterface |
|------------|----------|----------------|
| `spike_times` | Core | Yes (built-in) |
| `spike_amplitudes_V` | Core | Yes (`spike_amplitudes`) |
| `spike_relative_depths_um` | Core | Yes (`spike_locations`) |
| `maximum_amplitude_channel` | Location | Yes (`extremum_channel`) |
| `mean_relative_depth_um` | Location | Partial |
| `amplitude_max_V` | Amplitude | No (IBL-specific) |
| `amplitude_min_V` | Amplitude | No (IBL-specific) |
| `amplitude_median_V` | Amplitude | Yes (`amplitude_median`) |
| `amplitude_std_dB` | Amplitude | Partial (`amplitude_cv`) |
| `ibl_quality_score` | Quality | No (IBL composite) |
| `kilosort2_label` | Quality | No (Kilosort-specific) |
| `sliding_rp_violation` | Quality | Yes (`sliding_rp_violations`) |
| `noise_cutoff` | Quality | Yes (`amplitude_cutoff`) |
| `isi_violations_ratio` | Quality | Yes (`isi_violations_ratio`) |
| `rp_violation` | Quality | Yes (`rp_violations`) |
| `missed_spikes_estimate` | Quality | Yes (`amplitude_cutoff`) |
| `spike_count` | Activity | Yes (implicit) |
| `firing_rate` | Activity | Yes (`firing_rate`) |
| `presence_ratio` | Activity | Yes (`presence_ratio`) |
| `presence_ratio_std` | Activity | No (IBL-specific) |
| `drift_um_per_hour` | Activity | No (IBL-specific) |
| `cluster_uuid` | ID | N/A |
| `probe_name` | ID | N/A |

**Important Notes on Units:**
- **Amplitude columns are in Volts (V)**, not microvolts. IBL stores amplitudes in Volts.
- **`drift_um_per_hour`** is cumulative depth change rate, not absolute drift (see detailed description below).

---

### Core Spike Data

#### `spike_times`

| Property | Value |
|----------|-------|
| **IBL Source** | `spikes.times.npy` |
| **Units** | Seconds from session start |
| **SpikeInterface** | Yes (built-in) |

**What it measures**: The precise timestamp of each action potential detected and assigned to this unit.

**Intuition**: Spike times are the fundamental output of spike sorting - they represent when each neuron fired. All downstream analyses (firing rates, correlations, decoding) depend on accurate spike time estimation.

---

#### `spike_amplitudes_V`

| Property | Value |
|----------|-------|
| **IBL Source** | `spikes.amps.npy` |
| **Units** | Volts (V) |
| **SpikeInterface** | Yes (`spike_amplitudes` extension) |

**What it measures**: The peak-to-trough amplitude of each individual spike's waveform on the maximum amplitude channel.

**Intuition**: Spike amplitudes vary naturally due to distance from electrode, bursting behavior (sodium channel inactivation), and electrode drift. Tracking per-spike amplitudes allows detection of these phenomena and helps identify amplitude-based contamination.

**Why it varies**: Even spikes from the same neuron can have different amplitudes depending on the exact position of the action potential initiation site relative to the electrode.

**Note on units**: IBL stores amplitudes in Volts. Typical values are in the range 3e-5 to 3e-4 V (30-300 uV).

---

#### `spike_relative_depths_um`

| Property | Value |
|----------|-------|
| **IBL Source** | `spikes.depths.npy` |
| **Units** | Micrometers (um) |
| **SpikeInterface** | Yes (`spike_locations` extension) |

**What it measures**: The estimated depth along the probe shank for each spike, computed from the center of mass of the waveform across channels.

**Intuition**: Per-spike depth estimates are used to compute drift metrics. If a unit's spikes gradually shift in depth over time, this indicates probe drift relative to the brain tissue.

---

### Unit Location Properties

#### `maximum_amplitude_channel`

| Property | Value |
|----------|-------|
| **IBL Source** | `clusters.channels.npy` |
| **Units** | Channel index (0-383) |
| **SpikeInterface** | Yes (`get_extremum_channel`) |

**What it measures**: The electrode channel on which this unit's average waveform has the largest amplitude.

**Intuition**: The maximum amplitude channel indicates which electrode was closest to the neuron's soma. This is used to link units to brain regions (via the electrode's anatomical coordinates) and to identify electrode groups.

---

#### `mean_relative_depth_um`

| Property | Value |
|----------|-------|
| **IBL Source** | `clusters.depths.npy` |
| **Units** | Micrometers (um) |
| **SpikeInterface** | Partial (via `spike_locations`) |

**What it measures**: The average depth along the probe for all spikes assigned to this unit. Depth 0 is the probe tip, with positive values toward the brain surface.

**Intuition**: Combined with histology data (which maps probe trajectory through brain regions), this depth determines the unit's anatomical location and cortical layer assignment.

---

### Amplitude Statistics

**Note**: IBL stores all amplitude values in **Volts**, not microvolts. Typical neural spike amplitudes are in the range 3e-5 to 3e-4 V (30-300 uV).

#### `amplitude_max_V`

| Property | Value |
|----------|-------|
| **IBL Source** | `amp_max` |
| **Units** | Volts (V) |
| **SpikeInterface** | No (IBL-specific) |

**What it measures**: The maximum spike amplitude observed for this unit across all its spikes.

**Intuition**: Helps identify signal quality ceiling and outlier detection. Extremely high maximum amplitudes might indicate noise or artifact contamination.

---

#### `amplitude_min_V`

| Property | Value |
|----------|-------|
| **IBL Source** | `amp_min` |
| **Units** | Volts (V) |
| **SpikeInterface** | No (IBL-specific) |

**What it measures**: The minimum spike amplitude observed for this unit.

**Intuition**: Critical for assessing detection threshold proximity. If minimum amplitude is close to the detection threshold, many spikes may have been missed (false negatives).

---

#### `amplitude_median_V`

| Property | Value |
|----------|-------|
| **IBL Source** | `amp_median` |
| **Units** | Volts (V) |
| **SpikeInterface** | Yes (`amplitude_median`) |

**What it measures**: The geometric median of all spike amplitudes, computed in log-space.

**Intuition**: A robust measure of typical spike size that resists outliers. IBL uses a 50 uV (5e-5 V) threshold - units below this are likely noise or very distant neurons.

**Quality criterion**: Units must have `amplitude_median_V >= 5e-5` (50 uV) to pass IBL's amplitude threshold.

---

#### `amplitude_std_dB`

| Property | Value |
|----------|-------|
| **IBL Source** | `amp_std_dB` |
| **Units** | Decibels (dB) |
| **SpikeInterface** | Partial (`amplitude_cv`) |

**What it measures**: The standard deviation of log-transformed spike amplitudes.

**Intuition**: Amplitude variability in dB captures multiplicative noise (variations proportional to amplitude). High variability (>6 dB) may indicate drift, bursting, or contamination.

---

### Quality Metrics

#### `ibl_quality_score`

| Property | Value |
|----------|-------|
| **IBL Source** | `label` |
| **Units** | Proportion (0.0-1.0) |
| **SpikeInterface** | No (IBL-specific composite) |

**What it measures**: The proportion of IBL's three quality criteria passed: (1) sliding RP violation, (2) noise cutoff, (3) amplitude threshold.

**Intuition**: Rather than a single metric, IBL tests three independent aspects of unit quality:
- **Contamination** (false positives): Are there refractory period violations?
- **Completeness** (false negatives): Is the amplitude distribution truncated?
- **Signal quality**: Is the amplitude above noise floor?

| Score | Interpretation |
|-------|----------------|
| 1.0 | All 3 tests passed - high confidence single neuron |
| 0.67 | 2/3 passed - use with caution |
| 0.33 | 1/3 passed - likely contaminated or incomplete |
| 0.0 | All failed - exclude from analyses |

---

#### `kilosort2_label`

| Property | Value |
|----------|-------|
| **IBL Source** | `ks2_label` |
| **Values** | "good", "mua", "noise" |
| **SpikeInterface** | No (Kilosort-specific) |

**What it measures**: The original classification from the Kilosort2 algorithm during clustering.

**Intuition**:
- **"good"**: Well-isolated single unit with consistent waveform
- **"mua"**: Multi-unit activity - spikes from multiple neurons that couldn't be separated
- **"noise"**: Non-neural activity (electrical artifacts, movement)

**Note**: `kilosort2_label` and `ibl_quality_score` may disagree. A Kilosort "good" unit might fail IBL's stricter tests.

---

#### `sliding_rp_violation`

| Property | Value |
|----------|-------|
| **IBL Source** | `slidingRP_viol` |
| **Units** | Binary pass/fail (0.0 or 1.0) |
| **SpikeInterface** | Yes (`sliding_rp_violations`) |

**What it measures**: Binary pass/fail metric using a sliding refractory period algorithm that accounts for firing rate.

**Intuition**: Neurons have a biological refractory period (~1-2 ms) during which they cannot fire again. Violations indicate contamination from other neurons.

**Key insight**: Unlike simple ISI violation counts, this metric accounts for firing rate. A unit with 10 violations out of 100,000 spikes is much cleaner than one with 10 violations out of 1,000 spikes. Low firing rate units may fail regardless of actual contamination.

**Algorithm**:
1. Tests multiple refractory period durations (0.5-10 ms)
2. For each duration, calculates maximum allowed violations given firing rate
3. Unit passes (1.0) if contamination is below threshold at any tested refractory period

**Reference**: Developed by IBL, adapted from Hill et al. (2011). This is the primary metric used in IBL's `ibl_quality_score` calculation.

---

#### `noise_cutoff`

| Property | Value |
|----------|-------|
| **IBL Source** | `noise_cutoff` |
| **Units** | Standard deviations |
| **SpikeInterface** | Yes (`amplitude_cutoff`) |

**What it measures**: How many standard deviations the lower tail of the amplitude distribution deviates from expectations.

**Intuition**: A well-recorded unit should have a smooth, symmetric amplitude distribution. If it's "cut off" at the low end (truncated), spikes are being missed at the detection threshold.

**Calculation**:
1. Smooth the amplitude histogram
2. Compute statistics of upper quartile
3. Measure how far lower quartile deviates

**Interpretation**:
- Values near 0: Distribution is symmetric, few spikes missed
- Large values: Lower tail truncated, many spikes missed

---

#### `isi_violations_ratio`

| Property | Value |
|----------|-------|
| **IBL Source** | `contamination` |
| **Units** | Ratio (can exceed 1.0) |
| **SpikeInterface** | Yes (`isi_violations_ratio`) - exact match |

**What it measures**: Ratio of observed ISI violations to expected violations, using the Steinmetz/cortex-lab implementation.

**Intuition**: If all spikes truly come from one neuron, there should be almost no ISI violations (spikes within the ~1.5 ms refractory period). Violations indicate contamination from other neurons.

**Formula** (Steinmetz version):
```
C = n_violations / (firing_rate^2 * 2 * refractory_period * recording_duration)
```

**Key features**:
- Removes duplicate spikes (within `min_isi`) before counting violations
- Uses explicit recording time bounds (`min_time` to `max_time`)
- Computes a direct ratio that can exceed 1.0
- **Counts spikes that are violated** (i.e., spikes that have another spike within the refractory period)

**Interpretation**:
- 0.0: No violations, perfectly clean
- 0.05: ~5% contamination
- 0.10: ~10% (typical threshold for "good" units)
- >1.0: Possible if contaminants correlate with unit

---

#### `rp_violation`

| Property | Value |
|----------|-------|
| **IBL Source** | `contamination_alt` |
| **Units** | Proportion (bounded) |
| **SpikeInterface** | Yes (`rp_violations`) - aligned naming |

**What it measures**: Original Hill et al. (2011) contamination estimate using quadratic formula solving.

**Intuition**: Models contamination as mixing two independent Poisson processes (true unit + contaminant). The quadratic formula arises from the expected ISI violations when two spike trains are combined.

**Formula** (Hill et al. 2011 original):
```
c = (T * n_violations) / (2 * rp * N^2)
C = min(abs(roots([-1, 1, c])))  # Solves: -x^2 + x + c = 0
```

**Key difference from `isi_violations_ratio`**: This metric **counts the number of violations** (pairs of spikes within the refractory period), whereas `isi_violations_ratio` counts **spikes that are violated**. For example, if 3 spikes occur within a refractory period window, `isi_violations_ratio` counts 2 violated spikes, while `rp_violation` counts 3 violations as pairs.

**Comparison between `isi_violations_ratio` and `rp_violation`**:

| Aspect | `isi_violations_ratio` | `rp_violation` |
|--------|------------------------|----------------|
| **Origin** | Steinmetz/cortex-lab (UMS) | Hill et al. (2011) / Llobet |
| **What it counts** | Spikes that are violated | Number of violations |
| **Duplicate handling** | Removes duplicates first | Uses raw ISI violations |
| **Time basis** | Explicit min/max time | First to last spike |
| **Output range** | Unbounded (can exceed 1.0) | Bounded by quadratic solution |

**When they disagree**:
- `isi_violations_ratio >> rp_violation`: Contamination may be **correlated** with the unit (e.g., nearby bursting neuron firing in sync)
- `rp_violation >> isi_violations_ratio`: Edge case with very few violations

**Practical note**: Most IBL analyses use `ibl_quality_score` which relies on `sliding_rp_violation` (a more sophisticated method). These contamination metrics are supplementary for users wanting finer-grained quality control.

---

#### `missed_spikes_estimate`

| Property | Value |
|----------|-------|
| **IBL Source** | `missed_spikes_est` |
| **Units** | Proportion (0.0-1.0) |
| **SpikeInterface** | Yes (`amplitude_cutoff`) |

**What it measures**: Estimated fraction of spikes not detected due to amplitude threshold.

**Intuition**: Spike amplitudes should follow a roughly symmetric distribution. If the lower half is missing (cut off by detection threshold), we estimate missing spikes by mirroring the upper half.

**Interpretation**:
- 0.0: No spikes missing
- 0.1: ~10% missed
- 0.3+: Substantial loss, firing rate underestimated

---

### Activity Statistics

#### `spike_count`

| Property | Value |
|----------|-------|
| **IBL Source** | `spike_count` |
| **Units** | Count |
| **SpikeInterface** | Yes (implicit) |

**What it measures**: Total number of spikes assigned to this unit.

**Intuition**: Spike count determines statistical power. Very low counts (<100) make quality metrics unreliable.

**Typical values**: 1,000-100,000 spikes; high-firing interneurons can exceed 500,000.

---

#### `firing_rate`

| Property | Value |
|----------|-------|
| **IBL Source** | `firing_rate` |
| **Units** | Hz (spikes/second) |
| **SpikeInterface** | Yes (`firing_rate`) |

**What it measures**: Average spikes per second across the entire session.

**Intuition**: Both very high (>50 Hz) and very low (<0.1 Hz) rates can indicate problems. Different neuron types have characteristic firing rates.

**Quality interpretation**:
- >100 Hz: May indicate contamination
- <0.1 Hz: May indicate incomplete detection
- Most cortical neurons: 1-10 Hz

---

#### `presence_ratio`

| Property | Value |
|----------|-------|
| **IBL Source** | `presence_ratio` |
| **Units** | Proportion (0.0-1.0) |
| **SpikeInterface** | Yes (`presence_ratio`) |

**What it measures**: Fraction of time bins (default 60s) in which the unit fired at least once.

**Intuition**: A real neuron should fire throughout the recording. Low presence may indicate drift (neuron moved out of range), cell death, or sorting errors.

**Quality threshold**: Stable units have presence ratio > 0.9 (90%).

---

#### `presence_ratio_standard_deviation`

| Property | Value |
|----------|-------|
| **IBL Source** | `presence_ratio_std` |
| **Units** | Standard deviation |
| **SpikeInterface** | No (IBL-specific) |

**What it measures**: Variability of spike counts across 10-second bins.

**Intuition**: Distinguishes between:
- Stable units (low SD)
- Task-modulated units (high SD, scientifically relevant)
- Drifting units (high SD, often decreasing trend)

---

#### `drift_um`

| Property | Value |
|----------|-------|
| **IBL Source** | `drift` |
| **Units** | Micrometers (um) |
| **SpikeInterface** | Yes (`drift_ptp`, `drift_std`, `drift_mad`) |

**What it measures**: Average positional drift across the recording session.

**Intuition**: Probe movement relative to brain causes amplitude changes and can confuse spike sorting. Sources include brain pulsation, tissue settling, and thermal drift.

**Typical values**:
- Well-controlled: < 10 um
- Moderate: 10-30 um
- Problematic: > 50 um

---

### Identification

#### `cluster_id`

| Property | Value |
|----------|-------|
| **IBL Source** | Cluster index |
| **Units** | Index |
| **SpikeInterface** | N/A |

**What it measures**: Original numeric ID assigned during spike sorting.

**Intuition**: Probe-specific (resets for each probe). Use `cluster_id` + `probe_name` to match back to IBL files.

---

#### `cluster_uuid`

| Property | Value |
|----------|-------|
| **IBL Source** | `clusters.uuids.csv` |
| **Units** | UUID string |
| **SpikeInterface** | N/A |

**What it measures**: Globally unique identifier assigned by IBL.

**Intuition**: Enables linking NWB data back to IBL's database. Use for reproducibility and citing specific units in publications.

---

#### `probe_name`

| Property | Value |
|----------|-------|
| **IBL Source** | Computed |
| **Values** | "probe00", "probe01", etc. |
| **SpikeInterface** | N/A |

**What it measures**: Name of the Neuropixels probe from which this unit was recorded.

**Intuition**: IBL often uses multiple probes. Combined with `cluster_id`, uniquely identifies units within a session

---

## Data Extraction with ibllib

### Primary Extraction Method

The interface uses `SpikeSortingLoader` from `brainbox.io.one` to load spike sorting data:

```python
from brainbox.io.one import SpikeSortingLoader
from one.api import ONE

one = ONE()
ssl = SpikeSortingLoader(eid=session_id, pname="probe00", one=one, revision="2025-05-06")

# Load all spike sorting data
spikes, clusters, channels = ssl.load_spike_sorting()

# spikes: dict with 'times', 'clusters', 'amps', 'depths'
# clusters: dict with 'channels', 'depths', 'metrics', 'uuids'
# channels: dict with 'x', 'y', 'z', 'acronym', 'atlas_id', etc.
```

### Data Files

The interface loads from these ALF (Alyx File) format files:

#### Spike Files (per probe)
| File | Shape | Description |
|------|-------|-------------|
| `spikes.times.npy` | `(n_spikes,)` | Spike timestamps in seconds |
| `spikes.clusters.npy` | `(n_spikes,)` | Cluster ID for each spike |
| `spikes.amps.npy` | `(n_spikes,)` | Spike amplitudes in microvolts |
| `spikes.depths.npy` | `(n_spikes,)` | Spike depths in micrometers |

#### Cluster Files (per probe)
| File | Shape | Description |
|------|-------|-------------|
| `clusters.channels.npy` | `(n_clusters,)` | Maximum amplitude channel per cluster |
| `clusters.depths.npy` | `(n_clusters,)` | Mean depth per cluster |
| `clusters.metrics.pqt` | DataFrame | All quality metrics (Parquet format) |
| `clusters.uuids.csv` | `(n_clusters,)` | Unique identifiers |

#### Typical File Paths
```
alf/probe00/pykilosort/spikes.times.npy
alf/probe00/pykilosort/spikes.clusters.npy
alf/probe00/pykilosort/clusters.metrics.pqt
alf/probe00/channels.localCoordinates.npy
```

### Revision System

IBL uses a revision system for processed data. The sorting interface uses revision `2025-05-06`, which is the Brain-Wide Map standard revision. This ensures:
- Consistent spike sorting parameters across all sessions
- Reproducible quality metrics
- Standardized cluster assignments

---

## Interface Implementation

### Class Definition

```python
class IblSortingInterface(BaseSortingExtractorInterface, BaseIBLDataInterface):
    """Interface for spike sorting data (revision-dependent processed data)."""

    REVISION: str | None = "2025-05-06"  # BWM standard revision
```

**Source file**: [_ibl_sorting_interface.py](../IBL-to-nwb/src/ibl_to_nwb/datainterfaces/_ibl_sorting_interface.py)

### Key Methods

#### `get_data_requirements()`
Declares the exact files needed for spike sorting data per probe.

#### `download_data()`
Downloads spike sorting data using `SpikeSortingLoader` for each probe in the session.

#### `get_metadata()`
Loads unit property metadata from [ecephys.yml](../IBL-to-nwb/src/ibl_to_nwb/_metadata/ecephys.yml), which contains descriptions for each column.

#### `add_to_nwbfile()`
Adds the units table to the NWB file with automatic electrode linking. Supports:
- `stub_test=True` for quick testing with limited units
- `skip_properties` for memory optimization

### Usage Example

```python
from one.api import ONE
from ibl_to_nwb.datainterfaces import IblSortingInterface

one = ONE()
session_id = "your_session_eid_here"

# Create interface
sorting_interface = IblSortingInterface(one=one, session=session_id)

# Download data
sorting_interface.download_data(one=one, eid=session_id)

# Add to NWB file (electrodes table must exist first)
nwbfile = ...  # Your NWBFile instance with electrodes table
metadata = sorting_interface.get_metadata()
sorting_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)
```

### Memory Optimization

For large sessions (~2000 units, ~60M spikes), the ragged spike-level properties can use significant memory:

```python
# Skip memory-intensive ragged arrays (~10 GB savings)
sorting_interface.add_to_nwbfile(
    nwbfile=nwbfile,
    metadata=metadata,
    skip_properties=["spike_amplitudes_uv", "spike_relative_depths_um"]
)
```

| Property | Memory Usage | Notes |
|----------|--------------|-------|
| `spike_amplitudes_uv` | ~5 GB | Per-spike amplitude values |
| `spike_relative_depths_um` | ~5 GB | Per-spike depth values |
| All other properties | ~100 MB | Unit-level aggregates |

Skipping these properties preserves:
- All spike times
- All unit-level quality metrics
- Brain region annotations
- Mean amplitude and depth (unit-level)

### Stub Testing

For quick testing without loading all units:

```python
sorting_interface.add_to_nwbfile(
    nwbfile=nwbfile,
    metadata=metadata,
    stub_test=True,
    stub_units=10  # Only first 10 units per probe
)
```

---

## References

### Primary Publications

1. **IBL Spike Sorting White Paper**: International Brain Laboratory. "Spike sorting pipeline for the International Brain Laboratory." *FigShare* (2022).
   - DOI: [10.6084/m9.figshare.19705522](https://doi.org/10.6084/m9.figshare.19705522)
   - Full methodology and parameter choices

2. **Brain-Wide Map**: International Brain Laboratory, et al. "Reproducibility of in-vivo electrophysiological measurements in mice." *bioRxiv* (2022).
   - DOI: [10.1101/2022.05.09.491042](https://doi.org/10.1101/2022.05.09.491042)
   - Reproducibility analysis across laboratories

3. **Quality Metrics**: Hill, D.N., Mehta, S.B., & Bhattacharyya, A. "Quality metrics to accompany spike sorting of extracellular signals." *J Neurosci* 31 (2011): 8699-8705.
   - DOI: [10.1523/JNEUROSCI.0971-11.2011](https://doi.org/10.1523/JNEUROSCI.0971-11.2011)
   - Foundation for contamination and refractory period metrics

4. **Kilosort**: Pachitariu, M., et al. "Kilosort: realtime spike-sorting for extracellular electrophysiology with hundreds of channels." *bioRxiv* (2016).
   - DOI: [10.1101/061481](https://doi.org/10.1101/061481)
   - Original algorithm

### Data Resources

- **IBL Data Portal**: [data.internationalbrainlab.org](https://data.internationalbrainlab.org)
- **FigShare Dataset**: [10.6084/m9.figshare.21400815.v6](https://doi.org/10.6084/m9.figshare.21400815.v6)
- **ONE API Documentation**: [int-brain-lab.github.io/ONE](https://int-brain-lab.github.io/ONE/)

### Software Documentation

- **iblsorter**: [github.com/int-brain-lab/iblsorter](https://github.com/int-brain-lab/iblsorter)
- **ibllib**: [int-brain-lab.github.io/iblenv](https://int-brain-lab.github.io/iblenv/)
- **NeuroConv**: [neuroconv.readthedocs.io](https://neuroconv.readthedocs.io/)
- **SpikeInterface**: [spikeinterface.readthedocs.io](https://spikeinterface.readthedocs.io/)

---

## Appendix: Column Value Interpretations

### IBL Quality Score Values (`ibl_quality_score`)

| Value | Metrics Passed | Typical Interpretation |
|-------|----------------|------------------------|
| 1.0 | 3/3 | High-confidence single unit ("good") |
| 0.67 | 2/3 | Intermediate quality |
| 0.33 | 1/3 | Low quality, possibly multi-unit |
| 0.0 | 0/3 | Noise or highly contaminated |

### Kilosort2 Label Values (`kilosort2_label`)

| Value | Meaning | Description |
|-------|---------|-------------|
| `"good"` | Single unit | Well-isolated, consistent waveform shape |
| `"mua"` | Multi-unit activity | Multiple neurons merged, or poorly isolated |
| `"noise"` | Non-neural | Electrical artifacts, movement artifacts |

### Filtering for Good Units

```python
# Using NWB - IBL quality metric (recommended)
units_df = nwbfile.units.to_dataframe()
good_units = units_df[units_df['ibl_quality_score'] == 1.0]

# Using NWB - Kilosort2 classification
good_units_ks = units_df[units_df['kilosort2_label'] == 'good']

# Using both criteria (most conservative)
best_units = units_df[(units_df['ibl_quality_score'] == 1.0) & (units_df['kilosort2_label'] == 'good')]

# Using ONE API directly (note: ONE uses 'label' as the column name)
good_units = clusters['metrics']['label'] == 1.0
```

### Multi-Probe Sessions

For sessions with multiple probes, unit IDs are globally unique:

| Probe | Unit ID Range | Cluster ID Range |
|-------|---------------|------------------|
| probe00 | 0 to N-1 | 0 to N-1 |
| probe01 | N to N+M-1 | 0 to M-1 (resets) |

Use `probe_name` column to identify which probe a unit belongs to:

```python
# Get units from probe01 only
probe01_units = units_df[units_df['probe_name'] == 'probe01']
```

### Brain Region Access

Brain region information is accessed via the electrodes table link:

```python
# Get brain region for each unit
unit_electrode_indices = nwbfile.units['electrodes'][:]
for i, unit_id in enumerate(nwbfile.units.id[:]):
    electrode_idx = unit_electrode_indices[i][0]
    brain_region = nwbfile.electrodes['location'][electrode_idx]
    print(f"Unit {unit_id}: {brain_region}")
```

### Typical Values

| Metric | Typical Range | Notes |
|--------|---------------|-------|
| `firing_rate_hz` | 0.1 - 50 Hz | Most units 1-10 Hz |
| `spike_count` | 100 - 500,000 | Depends on session length and firing rate |
| `presence_ratio` | 0.5 - 1.0 | Good units typically >0.9 |
| `isi_violations_ratio` | 0.0 - 0.5 | Good units typically <0.1 |
| `median_amplitude_uv` | 50 - 500 uV | Threshold is 50 uV |
| `drift_um` | 0 - 50 um | Chronic recordings may have higher drift |

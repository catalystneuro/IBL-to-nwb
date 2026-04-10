# EphysSessionLoader

`EphysSessionLoader` extends [SessionLoader](session_loader.md) by adding spike sorting data for all probes in a session. Use it when you need both behavioral and electrophysiology data in one object.

## Quick Start

```python
from one.api import ONE
from brainbox.io.one import EphysSessionLoader

one = ONE()
loader = EphysSessionLoader(eid='your-session-uuid', one=one)

# Load all behavioral data
loader.load_session_data()

# Load spike sorting for all probes
loader.load_spike_sorting()

# Access data
trials = loader.trials           # pandas DataFrame
wheel = loader.wheel             # pandas DataFrame
spikes = loader.ephys['probe00']['spikes']
clusters = loader.ephys['probe00']['clusters']
```

## Key Differences from SessionLoader

| Feature | SessionLoader | EphysSessionLoader |
|---------|---------------|-------------------|
| Behavioral data | Yes | Yes (inherited) |
| Spike sorting | No | Yes |
| Multiple probes | N/A | All probes in session |
| Memory usage | Lower | Higher |

## Additional Methods

### `load_spike_sorting(pnames=None)`

Load spike sorting data for specified probes (or all if `pnames=None`).

```python
# Load all probes
loader.load_spike_sorting()

# Load specific probes only
loader.load_spike_sorting(pnames=['probe00', 'probe01'])
```

### `probes` property

Returns list of probe names in the session.

```python
print(loader.probes)  # ['probe00', 'probe01']
```

## Data Structure

Spike sorting data is stored in `loader.ephys` dictionary, keyed by probe name:

```python
loader.ephys['probe00']['spikes']   # Spike times, clusters, amps, depths
loader.ephys['probe00']['clusters'] # Cluster info and metrics
loader.ephys['probe00']['channels'] # Channel locations and brain regions
```

See [SpikeSortingLoader](spike_sorting_loader.md) for detailed documentation of these data structures.

## When to Use

**Use EphysSessionLoader when:**
- You need both behavioral and spike data together
- You're analyzing multiple probes in one session
- You want a single object to manage all data

**Use SessionLoader + SpikeSortingLoader separately when:**
- You only need behavioral data
- You're analyzing a single probe
- You want finer control over memory usage

## Source

`brainbox.io.one.EphysSessionLoader` (line ~1506 in ibllib)

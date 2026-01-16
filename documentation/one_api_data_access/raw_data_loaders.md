# Raw Data Loaders

Low-level functions for accessing unprocessed experimental data. Use these when you need direct access to raw files or want to build custom processing pipelines.

## Function Reference

### PyBpod Task Data (`ibllib.io.raw_data_loaders`)

| Function | Returns | Description |
|----------|---------|-------------|
| `load_bpod(session_path)` | tuple | Load both settings and trial data |
| `load_data(session_path)` | list[dict] | Trial-by-trial event data |
| `load_settings(session_path)` | dict | Task configuration and parameters |

### Camera Data (`ibllib.io.raw_data_loaders`)

| Function | Returns | Description |
|----------|---------|-------------|
| `load_camera_frameData(session_path, camera)` | DataFrame | Frame timestamps, counters, GPIO |
| `load_camera_ssv_times(session_path, camera)` | array | Timestamps from SSV file |
| `load_camera_frame_count(session_path, label)` | array | Embedded frame counters |
| `load_camera_gpio(session_path, label)` | array/dict | GPIO pin state changes |

### Rotary Encoder (`ibllib.io.raw_data_loaders`)

| Function | Returns | Description |
|----------|---------|-------------|
| `load_encoder_positions(session_path)` | DataFrame | Wheel position in ticks |
| `load_encoder_events(session_path)` | DataFrame | State machine events |
| `load_encoder_trial_info(session_path)` | DataFrame | Stimulus parameters per trial |

### DAQ Data (`ibllib.io.raw_daq_loaders`)

| Function | Returns | Description |
|----------|---------|-------------|
| `load_raw_daq_tdms(path)` | TdmsFile | Raw TDMS file object |
| `load_channels_tdms(path)` | dict | Analog and digital channels |
| `load_sync_tdms(path, sync_map)` | dict | Sync pulses (times, polarities, channels) |

### Audio and Sensors (`ibllib.io.raw_data_loaders`)

| Function | Returns | Description |
|----------|---------|-------------|
| `load_mic(session_path)` | array | Microphone WAV data |
| `load_ambient_sensor(session_path)` | DataFrame | Temperature, pressure, humidity |

## Example Usage

```python
from ibllib.io.raw_data_loaders import load_data, load_encoder_positions

session_path = '/path/to/session'

# Load raw trial data (list of dicts, one per trial)
trials = load_data(session_path, task_collection='raw_behavior_data')

# Load raw wheel encoder data
wheel_df = load_encoder_positions(session_path)
```

## Pros and Cons

**Pros:**
- Direct access to unprocessed data
- No automatic processing overhead
- Full control over data handling
- Useful for debugging and custom pipelines

**Cons:**
- Requires manual timestamp alignment
- No automatic format conversion
- Must handle version differences manually
- No convenience features (filtering, interpolation)

## When to Use

- Building custom processing pipelines
- Debugging data quality issues
- Accessing data not available in high-level loaders
- When you need raw timestamps before synchronization

## Source

- `ibllib.io.raw_data_loaders` - Behavioral raw data
- `ibllib.io.raw_daq_loaders` - DAQ/TDMS files

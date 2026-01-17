# Path Handling

This document explains how paths are managed during conversion and common pitfalls to avoid.

## Path Dictionary Structure

All paths in the conversion pipeline are managed through a centralized `setup_paths()` function that returns a dictionary with predefined keys. This ensures consistency across the codebase.

**Location**: `src/ibl_to_nwb/utils/paths.py`

```python
from ibl_to_nwb.utils.paths import setup_paths

paths = setup_paths(one=one, eid=eid, base_path=base_path)
```

### Available Path Keys

| Key | Description | Example Value |
|-----|-------------|---------------|
| `output_folder` | Where NWB files are written | `~/ibl_bmw_to_nwb/nwbfiles` |
| `session_folder` | ONE cache location for session | `~/.one/cache/lab/subject/date/number` |
| `session_decompressed_ephys_folder` | This session's decompressed ephys | `~/ibl_bmw_to_nwb/decompressed_ephys/{eid}` |
| `spikeglx_source_folder` | Raw ephys data for SpikeGLX | `{session_decompressed_ephys_folder}/raw_ephys_data` |

## Common Mistake: Using Non-Existent Keys

The path dictionary has a **fixed set of keys**. Using a key that doesn't exist will raise a `KeyError` at runtime, but typos in string keys may not be caught by linters.

### Wrong

```python
# "session_scratch_folder" does not exist in the paths dictionary
scratch_ephys_folder = paths["session_scratch_folder"] / "raw_ephys_data"
```

### Correct

```python
# Use the actual key name from setup_paths()
scratch_ephys_folder = paths["session_decompressed_ephys_folder"] / "raw_ephys_data"
```

**Why this matters**: Using non-existent keys will cause `KeyError` at runtime, and string-based dictionary keys won't be caught by linters or type checkers.

## Path Key Reference

When working with decompressed ephys data, always use these keys:

| Operation | Use This Key |
|-----------|--------------|
| Check if decompressed bins exist | `paths["session_decompressed_ephys_folder"]` |
| Decompress .cbin files to | `paths["session_decompressed_ephys_folder"]` |
| Clean up macOS hidden files | `paths["session_decompressed_ephys_folder"]` |
| Find SpikeGLX source data | `paths["spikeglx_source_folder"]` |

## Best Practices

1. **Always check `paths.py`** before using a path key to verify it exists
2. **Never construct paths manually** for locations that have dedicated keys
3. **Use the most specific key available** (e.g., `spikeglx_source_folder` rather than building it from `session_decompressed_ephys_folder`)
4. **Add new keys to `setup_paths()`** if you need a new standard path, rather than constructing it ad-hoc in conversion code

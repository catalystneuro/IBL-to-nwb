# Waveform sampling_rate Attribute Bug

## Summary

The `sampling_rate` attribute on `Units.waveform_mean` is not written to HDF5 files when using neuroconv's `configure_backend()` or `configure_and_write_nwbfile()`. This is due to a bug in `ndx-events` that overrides pynwb's `VectorDataMap`.

## Root Cause

When `ndx-events` is imported, it registers a custom `VectorDataMap` for all `VectorData` objects:

https://github.com/rly/ndx-events/blob/32e647e/src/pynwb/ndx_events/io/events.py#L52-L71

This replaces pynwb's built-in `VectorDataMap` from `pynwb/io/core.py`, which contains the logic to map `Units.waveform_rate` to `waveform_mean.attrs['sampling_rate']`:

https://github.com/NeurodataWithoutBorders/pynwb/blob/4b7f5516f0e517a5450e7af0857e2d72f2bb5045/src/pynwb/io/core.py#L45-L51

The ndx-events `VectorDataMap` only handles `AnnotatedEventsTable.resolution` and calls `super().get_attr_value()` for everything else, which goes to `hdmf.build.ObjectMapper` instead of pynwb's mapper, bypassing the Units-specific handling.

## Impact

- `waveform_mean.attrs['sampling_rate']` is not written (should be 30000.0 Hz for Neuropixels)
- `spike_times.attrs['resolution']` is not written (should be 1/30000.0 seconds)

## Reproduction

See `build/reproduce_sampling_rate_bug.py` for a minimal reproduction script.

## Workaround

After writing the NWB file, manually set the attributes using h5py:

```python
import h5py

with h5py.File(nwbfile_path, "a") as hf:
    if "units/waveform_mean" in hf:
        hf["units/waveform_mean"].attrs["sampling_rate"] = 30000.0
    if "units/spike_times" in hf:
        hf["units/spike_times"].attrs["resolution"] = 1.0 / 30000.0
```

This workaround is implemented in `ibl_to_nwb/conversion/processed.py` and should be removed once ndx-events is integrated into NWB core.

Note: The `unit` attribute is intentionally left as 'volts' to comply with the NWB schema, even though the actual data is in microvolts. This is documented in the waveform_mean description.

## Related Issue: waveform_unit Fixed to 'volts'

There is a separate issue where `Units.waveform_unit` has no effect on the serialized `unit` attribute. The NWB schema defines `unit` with a fixed value (`value: volts`), and hdmf enforces this by short-circuiting attribute resolution when `spec.value` is set.

See `build/waveform_unit_issue.md` for details and links to the relevant code in nwb-schema and hdmf.

## Potential Fixes

For the ndx-events bug, the fix should be one of:

1. Have ndx-events inherit from `pynwb.io.core.VectorDataMap` instead of `hdmf.build.ObjectMapper`
2. Have ndx-events include the pynwb Units handling in its `get_attr_value` method
3. Register a more specific mapper instead of overriding all `VectorData` objects

Once ndx-events is integrated into NWB core, this issue should be resolved and the workaround in `processed.py` can be removed.

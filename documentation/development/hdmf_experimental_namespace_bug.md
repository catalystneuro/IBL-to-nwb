# hdmf-experimental Namespace Bug

## Summary

NWB files written with hdmf < 5.0 incorrectly tag `DynamicTableRegion` and `VectorData`
objects with `namespace="hdmf-experimental"` instead of `namespace="hdmf-common"`. This
causes MatNWB (MATLAB) to fail with:

```
Undefined variable "types" or class "types.hdmf_experimental.DynamicTableRegion"
```

Files load fine in Python (PyNWB) but are unreadable in MATLAB.

See: [MatNWB issue #304](https://github.com/NeurodataWithoutBorders/matnwb/issues/304)

## Root Cause

In hdmf < 5.0, the `hdmf-experimental` namespace was used for types that were later
promoted to `hdmf-common`. When writing NWB files, hdmf tagged `DynamicTableRegion`
and `VectorData` objects with `namespace="hdmf-experimental"`. MatNWB does not have
type definitions for this namespace, so it cannot resolve these references.

## Fix Applied (January 2, 2026)

A post-write HDF5 patch (`fix_nwb_namespace.py`) was added in commit `4c5e19b` that:

1. Opens the NWB file with `h5py` in append mode
2. Visits all HDF5 objects
3. For any object where `attrs["namespace"] == "hdmf-experimental"` and
   `attrs["neurodata_type"]` is `DynamicTableRegion` or `VectorData`:
   changes `attrs["namespace"]` to `"hdmf-common"`

This patch was applied to **all raw and processed NWB files** during conversion, before
upload to DANDI. It was called in both `convert_single_bwm_to_nwb.py` and
`convert_bwm_to_nwb.py` after each file was written.

## What Remains in the Files

The patch changes the `namespace` attribute on individual datasets but does **not** remove
the `specifications/hdmf-experimental` group from the HDF5 file. This group is inert
metadata that no object references. It does not affect readability in PyNWB or MatNWB.

To verify a file was properly patched, check that no datasets reference the old namespace:

```python
import h5py

def check_hdmf_experimental_refs(nwbfile_path):
    """Check if any objects still reference hdmf-experimental namespace."""
    bad_refs = []
    with h5py.File(nwbfile_path, "r") as f:
        def visitor(name, obj):
            if obj.attrs.get("namespace") == "hdmf-experimental":
                bad_refs.append((name, obj.attrs.get("neurodata_type")))
        f.visititems(visitor)
    return bad_refs
```

## Resolution with hdmf >= 5.0 (March 2026)

With the upgrade to hdmf 5.0, the `hdmf-experimental` namespace is no longer used.
New files written with hdmf >= 5.0 correctly use `namespace="hdmf-common"` for all
`DynamicTableRegion` and `VectorData` objects, and do not include the
`specifications/hdmf-experimental` group at all.

The `fix_nwb_namespace.py` script was removed in commit `db44e12` (March 3, 2026) as
it is no longer needed.

## Testing with MatNWB

To verify files are readable in MATLAB:

```matlab
% Install MatNWB (if not already installed)
% See: https://github.com/NeurodataWithoutBorders/matnwb

% Read a processed NWB file from DANDI
nwbfile = nwbRead('path/to/file.nwb');

% Access the units table (contains DynamicTableRegion columns)
units = nwbfile.units;
disp(units);

% Access electrodes table
electrodes = nwbfile.general_extracellular_ephys_electrodes;
disp(electrodes);
```

If the file still has unpatched `hdmf-experimental` references, the `nwbRead` call will
fail with the `types.hdmf_experimental.DynamicTableRegion` error.

## Status of Files on DANDI (Dandiset 000409)

### Raw files (459 total)
- All 459 files have the `specifications/hdmf-experimental` group (harmless, inert)
- All 459 files had the namespace attributes patched via `fix_nwb_namespace.py` before upload
- 4 files (NYU-11, NYU-12) are from an earlier conversion and need re-conversion for
  other reasons (missing `probe_name` column)

### Processed files
- Files converted before March 2026 were patched with `fix_nwb_namespace.py`
- Files converted with hdmf >= 5.0 (March 2026 onward) do not have the issue at all

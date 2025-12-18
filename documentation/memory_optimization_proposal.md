# Memory Optimization Proposal for IBL NWB Conversion

## Background

### Problem Statement

The IBL to NWB conversion process exhibits extremely high memory consumption when writing spike sorting data to NWB files. Memory profiling revealed peak memory usage of **23.4 GB** with total allocations of **215.2 GB** during the conversion of a single session.

### Profiling Methodology

Memory profiling was performed using `memray` with native tracking enabled:

```bash
memray run --native --output ./memray_output.bin profile_memory.py
memray flamegraph memray_output.bin
```

The profiled code primarily exercises the `IblSortingInterface.add_to_nwbfile()` method, which writes spike-sorted unit data (spike times, amplitudes, depths, and metadata) to the NWB Units table.

### Key Findings

The flamegraph analysis revealed that **15.9 GB (68% of peak memory)** is allocated within a single function: `_add_units_table_to_nwbfile()` in neuroconv's spikeinterface module.

#### Top Memory Allocations

1. **`units_table.add_column()` → 9.9 GB (42% of peak)**
   - Location: `neuroconv/tools/spikeinterface/spikeinterface.py:1719`
   - Root cause: `list(itertools.chain.from_iterable(flatten_data))` in `hdmf/common/table.py:902`
   - Creates a giant flattened Python list from ragged arrays containing spike amplitudes and depths for all units

2. **`units_table.add_unit()` → 5.0 GB (21% of peak)**
   - Location: `neuroconv/tools/spikeinterface/spikeinterface.py:1686`
   - Called in a loop for each unit (~hundreds of iterations)
   - Each call triggers `extend_data()` → `list.extend()` → `PyMem_Realloc`
   - Repeated list reallocations as internal storage grows

3. **`units_table.to_dataframe()` → 1.0 GB (4% of peak)**
   - Location: `neuroconv/tools/spikeinterface/spikeinterface.py:1703`
   - Creates a temporary pandas DataFrame from the entire Units table
   - Used only to build a `unit_name → electrode_index` mapping

4. **`IblSortingExtractor.__init__()` → 143.8 GB (cumulative allocations)**
   - Location: `ibl_to_nwb/datainterfaces/_ibl_sorting_extractor.py:81`
   - Uses `np.where()` in a loop for each cluster, creating massive temporary boolean arrays
   - Note: This is total cumulative allocation; most is freed before peak

### Root Cause Analysis

HDMF's `DynamicTable` implementation is extremely memory-inefficient for large datasets with ragged arrays:

1. **Incremental row additions cause O(n²) behavior**: Each `add_unit()` call extends internal Python lists, triggering repeated memory reallocations

2. **Unnecessary list conversions**: Neuroconv converts numpy arrays to Python lists (`.tolist()`), then HDMF flattens them into even larger lists

3. **DataFrame materialization**: The entire table is converted to pandas just to build a simple index mapping

4. **No batch operation support**: HDMF's API encourages row-by-row insertion rather than bulk operations

For IBL data with millions of spikes across hundreds of units, these inefficiencies compound to create massive temporary memory allocations.

### Backend Independence (HDF5 vs Zarr)

**Critical insight:** These memory issues are **backend-independent** and will affect both HDF5 and Zarr workflows equally.

The memory problems occur during **in-memory table construction**, before data is written to any backend:

1. When `pynwb.misc.Units()` is created, internal data storage starts as Python lists
2. All `add_unit()` and `add_column()` operations manipulate these in-memory lists
3. Only during the final `write()` call does HDMF serialize data to HDF5/Zarr

Verification:
```python
import pynwb
units_table = pynwb.misc.Units(name="units", description="Test")
print(type(units_table.id.data))  # <class 'list'>
```

**Backend-specific code paths:**

While `hdmf/data_utils.py` contains backend-specific branches:
- `append_data()` has Zarr support (`ZarrArray`)
- `extend_data()` has HDF5 support (`h5py.Dataset`) but **lacks Zarr support**

These code paths are only used when:
1. Opening an existing NWB file in append mode
2. Directly extending datasets that are already on disk

This is **not** the typical neuroconv workflow, which builds tables in memory first.

**Implication:** All proposed optimizations apply equally to HDF5 and Zarr backends. However, we should add Zarr support to `extend_data()` for completeness.

---

## Proposed Modifications

### HDMF Modifications (hdmf-dev/hdmf)

#### 1. Eliminate List Flattening in `add_column()`

**File:** `hdmf/common/table.py:902`

**Current Code:**
```python
flatten_data = list(itertools.chain.from_iterable(flatten_data))
```

**Problem:**
Creates a 9.9 GB Python list copy for ragged arrays by materializing the entire flattened iterator into memory at once.

**Proposed Fix (Option A):** Use generator-based approach
```python
# Keep as generator until written to HDF5 backend
flatten_data = itertools.chain.from_iterable(flatten_data)
# Modify downstream code to handle generators
```

**Proposed Fix (Option B):** Pre-allocate numpy array
```python
# Calculate total length first
total_length = sum(len(arr) for arr in flatten_data)
dtype = flatten_data[0].dtype if hasattr(flatten_data[0], 'dtype') else None

# Pre-allocate flat array
flat_array = np.empty(total_length, dtype=dtype)
offset = 0
for arr in flatten_data:
    length = len(arr)
    flat_array[offset:offset+length] = arr
    offset += length
flatten_data = flat_array
```

**Expected Impact:** ~9.9 GB memory reduction

**Difficulty:** Medium (requires testing with HDF5 backend compatibility)

---

#### 2. Optimize `extend_data()` for Lists

**File:** `hdmf/data_utils.py:62`

**Current Code:**
```python
if isinstance(data, (list, DataIO)):
    data.extend(arg)
    return data
```

**Problem:**
Repeated `list.extend()` calls in a loop cause O(n²) memory reallocations as Python lists grow incrementally.

**Proposed Fix:** Add batch extension method
```python
def extend_data_batch(data, args_list):
    """
    Extend data with multiple arrays at once to avoid repeated reallocation.

    Parameters
    ----------
    data : list, DataIO, numpy.ndarray, h5py.Dataset
        The array to extend
    args_list : list of arrays
        Multiple arrays to add to data in one operation

    Returns
    -------
    Extended data
    """
    if isinstance(data, list):
        # Single allocation for all items
        data.extend(itertools.chain.from_iterable(args_list))
        return data
    elif isinstance(data, np.ndarray):
        return np.vstack([data] + args_list)
    elif isinstance(data, h5py.Dataset):
        total_new_rows = sum(len(arg) for arg in args_list)
        shape = list(data.shape)
        old_size = shape[0]
        shape[0] += total_new_rows
        data.resize(shape)

        offset = old_size
        for arg in args_list:
            length = len(arg)
            data[offset:offset+length] = arg
            offset += length
        return data
    else:
        # Fallback to sequential
        for arg in args_list:
            data = extend_data(data, arg)
        return data
```

**Expected Impact:** ~3-4 GB memory reduction

**Difficulty:** Medium (backward compatible, needs API addition)

---

#### 2b. Add Missing Zarr Support to `extend_data()`

**File:** `hdmf/data_utils.py:62`

**Current Code:**
```python
elif isinstance(data, h5py.Dataset):
    shape = list(data.shape)
    shape[0] += len(arg)
    data.resize(shape)
    data[-len(arg):] = arg
    return data
else:
    msg = "Data cannot extend object of type '%s'" % type(data)
    raise ValueError(msg)
```

**Problem:**
`extend_data()` supports HDF5 datasets but not Zarr arrays, despite `append_data()` having Zarr support.

**Proposed Fix:**
```python
elif isinstance(data, h5py.Dataset):
    shape = list(data.shape)
    shape[0] += len(arg)
    data.resize(shape)
    data[-len(arg):] = arg
    return data
elif ZARR_INSTALLED and isinstance(data, ZarrArray):
    # Zarr arrays support append operation
    data.append(arg, axis=0)
    return data
else:
    msg = "Data cannot extend object of type '%s'" % type(data)
    raise ValueError(msg)
```

**Note:** This would only be used if writing directly to an open Zarr file (not typical workflow), but adds completeness and parity with `append_data()`.

**Expected Impact:** No memory reduction (code path not used in current workflow), but improves backend parity

**Difficulty:** Low (mirrors existing `append_data()` implementation)

---

#### 3. Add Batch `add_rows()` Method to DynamicTable

**File:** `hdmf/common/table.py` (add new method to DynamicTable class)

**Current Approach:**
```python
for row_data in rows:
    table.add_row(**row_data)  # O(n²) behavior
```

**Proposed Addition:**
```python
@docval({'name': 'rows', 'type': list, 'doc': 'List of dictionaries, each containing row data'},
        {'name': 'enforce_unique_id', 'type': bool, 'default': False,
         'doc': 'Enforce that all IDs are unique'},
        allow_extra=True)
def add_rows(self, **kwargs):
    """
    Add multiple rows to the table at once for better performance.

    This method is more efficient than calling add_row() in a loop as it
    minimizes memory reallocations by batch-processing the data.

    Parameters
    ----------
    rows : list of dict
        Each dict contains column_name: value pairs for one row
    enforce_unique_id : bool, optional
        If True, raise error if any row ID already exists in table

    Examples
    --------
    >>> table.add_rows([
    ...     {'spike_times': [0.1, 0.2], 'unit_name': 'unit1'},
    ...     {'spike_times': [0.3, 0.4], 'unit_name': 'unit2'}
    ... ])
    """
    rows, enforce_unique_id = getargs('rows', 'enforce_unique_id', kwargs)

    if not rows:
        return

    # Validate all rows first
    for data in rows:
        self._validate_new_row(data)
        self._add_extra_predefined_columns(data)

    # Collect IDs
    n_new_rows = len(rows)
    new_ids = []
    for i, data in enumerate(rows):
        row_id = data.get('id', len(self) + i)
        if enforce_unique_id and row_id in self.id:
            raise ValueError(f"id {row_id} already in the table")
        new_ids.append(row_id)

    # Extend id column once
    self.id.extend(new_ids)

    # Extend each column once with all data
    for colname in self.__colids:
        col = self.__df_cols[self.__colids[colname]]
        col_values = [row.get(colname) for row in rows]

        if isinstance(col, VectorIndex):
            # VectorIndex needs special handling for ragged arrays
            for value in col_values:
                col.add_vector(value)
        else:
            # Use batch extend (requires modification #2)
            if hasattr(col, 'extend'):
                col.extend(col_values)
            else:
                for value in col_values:
                    col.add_row(value)
```

**Expected Impact:** ~1-2 GB memory reduction (eliminates per-row overhead)

**Difficulty:** High (new API, requires thorough testing)

---

#### 4. Add Capacity Preallocation to Data.extend()

**File:** `hdmf/container.py:996`

**Current Code:**
```python
def extend(self, arg):
    """
    The extend_data method adds all the elements of the iterable arg to the
    end of the data of this Data container.
    """
    self._validate_new_data(arg)
    self.__data = extend_data(self.__data, arg)
```

**Proposed Enhancement:**
```python
@docval({'name': 'arg', 'type': (list, np.ndarray, DataIO, 'array_data'),
         'doc': 'The iterable to add to the end of this VectorData'},
        {'name': 'reserve_capacity', 'type': int, 'default': None,
         'doc': 'Expected final total size to preallocate (optimization hint)'},
        allow_extra=True)
def extend(self, **kwargs):
    """
    Add all elements of the iterable arg to the end of the data.

    Parameters
    ----------
    arg : list, np.ndarray, DataIO, or array_data
        The iterable to add to the end of this VectorData
    reserve_capacity : int, optional
        Hint for the expected total final size. If provided and current data
        is a Python list, this will preallocate space to reduce reallocations.
    """
    arg, reserve_capacity = getargs('arg', 'reserve_capacity', kwargs)

    self._validate_new_data(arg)

    # Preallocate if hint provided and data is a list
    if reserve_capacity and isinstance(self.__data, list):
        current_size = len(self.__data)
        if reserve_capacity > current_size:
            # Preallocate by extending list with placeholders
            # (these will be overwritten by extend_data)
            growth = reserve_capacity - current_size
            if growth > len(arg) * 10:  # Only if significant future growth expected
                self.__data.extend([None] * (growth - len(arg)))

    self.__data = extend_data(self.__data, arg)
```

**Expected Impact:** ~1 GB memory reduction (fewer reallocations)

**Difficulty:** Low (backward compatible, optional parameter)

---

### NeuroConv Modifications (catalystneuro/neuroconv)

#### 5. Use Batch `add_rows()` Instead of Loop

**File:** `neuroconv/tools/spikeinterface/spikeinterface.py:1686`

**Current Code:**
```python
for row in range(len(unit_ids)):
    spike_times = []
    for segment_index in range(sorting.get_num_segments()):
        segment_spike_times = sorting.get_unit_spike_train(
            unit_id=unit_ids[row], segment_index=segment_index, return_times=True
        )
        spike_times.append(segment_spike_times)
    spike_times = np.concatenate(spike_times)

    if waveform_means is not None:
        unit_kwargs["waveform_mean"] = waveform_means[row]
        if waveform_sds is not None:
            unit_kwargs["waveform_sd"] = waveform_sds[row]
    if unit_electrode_indices is not None:
        unit_kwargs["electrodes"] = unit_electrode_indices[row]

    units_table.add_unit(spike_times=spike_times, **unit_kwargs, enforce_unique_id=True)
```

**Proposed Refactor:**
```python
# Collect all rows first
rows_to_add = []

for row in range(len(unit_ids)):
    spike_times = []
    for segment_index in range(sorting.get_num_segments()):
        segment_spike_times = sorting.get_unit_spike_train(
            unit_id=unit_ids[row], segment_index=segment_index, return_times=True
        )
        spike_times.append(segment_spike_times)
    spike_times = np.concatenate(spike_times)

    unit_kwargs = {"spike_times": spike_times}

    if waveform_means is not None:
        unit_kwargs["waveform_mean"] = waveform_means[row]
        if waveform_sds is not None:
            unit_kwargs["waveform_sd"] = waveform_sds[row]
    if unit_electrode_indices is not None:
        unit_kwargs["electrodes"] = unit_electrode_indices[row]

    # Add any other properties from properties_to_add_by_rows
    for property in properties_to_add_by_rows - {"id"}:
        if property in data_to_add:
            unit_kwargs[property] = data_to_add[property]["data"][row]

    rows_to_add.append(unit_kwargs)

# Add all rows at once (requires HDMF modification #3)
if hasattr(units_table, 'add_rows'):
    units_table.add_rows(rows_to_add, enforce_unique_id=True)
else:
    # Fallback for older HDMF versions
    for unit_kwargs in rows_to_add:
        units_table.add_unit(**unit_kwargs, enforce_unique_id=True)
```

**Expected Impact:** ~4-5 GB memory reduction (eliminates incremental reallocation)

**Difficulty:** High (requires HDMF modification #3, needs version checking)

---

#### 6. Keep Numpy Arrays Instead of Converting to Lists

**File:** `neuroconv/tools/spikeinterface/spikeinterface.py:1742`

**Current Code:**
```python
else:
    dtype = np.ndarray
    extended_data = np.empty(shape=unit_table_size, dtype=dtype)
    for index, value in enumerate(data):
        index_in_extended_data = indices_for_new_data[index]
        extended_data[index_in_extended_data] = value.tolist()  # Conversion here!

    for index in indices_for_null_values:
        null_value = []
        extended_data[index] = null_value

    cols_args["data"] = extended_data
    units_table.add_column(property, **cols_args)
```

**Proposed Fix:**
```python
else:
    dtype = np.ndarray
    extended_data = np.empty(shape=unit_table_size, dtype=dtype)
    for index, value in enumerate(data):
        index_in_extended_data = indices_for_new_data[index]
        # Keep as numpy array instead of converting to list
        extended_data[index_in_extended_data] = value

    for index in indices_for_null_values:
        # Use empty numpy array instead of Python list for consistency
        null_value = np.array([])
        extended_data[index] = null_value

    cols_args["data"] = extended_data
    units_table.add_column(property, **cols_args)
```

**Complementary HDMF Fix:**
Modify `hdmf/common/table.py:902` to handle numpy object arrays:
```python
# Before flattening, check if data contains numpy arrays
if len(flatten_data) > 0 and isinstance(flatten_data[0], np.ndarray):
    # Use numpy concatenate instead of list flattening
    flatten_data = np.concatenate(flatten_data)
else:
    flatten_data = list(itertools.chain.from_iterable(flatten_data))
```

**Expected Impact:** ~2-3 GB memory reduction (avoids list conversion overhead)

**Difficulty:** Medium (requires coordination between neuroconv and hdmf)

---

#### 7. Eliminate Unnecessary `to_dataframe()` Call

**File:** `neuroconv/tools/spikeinterface/spikeinterface.py:1703`

**Current Code:**
```python
# Build a channel name to electrode table index map
table_df = units_table.to_dataframe().reset_index()
unit_name_to_electrode_index = {
    unit_name: table_df.query(f"unit_name=='{unit_name}'").index[0]
    for unit_name in unit_name_array
}
```

**Problem:**
Creates a 1 GB pandas DataFrame copy of the entire Units table just to build a simple index mapping.

**Proposed Fix:**
```python
# Build a channel name to electrode table index map
# Access unit_name column directly without DataFrame conversion
unit_names_col = units_table['unit_name'][:]

# Build mapping using direct array access
unit_name_to_electrode_index = {}
for unit_name in unit_name_array:
    # Find index where unit_name matches
    idx = np.where(unit_names_col == unit_name)[0]
    if len(idx) > 0:
        unit_name_to_electrode_index[unit_name] = int(idx[0])
    else:
        raise ValueError(f"Unit name '{unit_name}' not found in units table")

# More efficient alternative using a single pass
unit_name_to_electrode_index = {
    name: idx
    for idx, name in enumerate(unit_names_col)
    if name in unit_name_array
}
```

**Expected Impact:** ~1 GB memory reduction

**Difficulty:** Low (straightforward refactor, no dependencies)

---

#### 8. Add Chunked Writing Option

**File:** `neuroconv/tools/spikeinterface/spikeinterface.py:1487`

**Proposed Addition:**
```python
def _add_units_table_to_nwbfile(
    sorting: BaseSorting,
    nwbfile: pynwb.NWBFile,
    unit_ids: list[str | int] | None = None,
    property_descriptions: dict | None = None,
    skip_properties: list[str] | None = None,
    units_table_name: str = "units",
    unit_table_description: str | None = None,
    write_in_processing_module: bool = False,
    waveform_means: np.ndarray | None = None,
    waveform_sds: np.ndarray | None = None,
    unit_electrode_indices: list[list[int]] | None = None,
    null_values_for_properties: dict | None = None,
    chunk_size: int | None = None,  # NEW PARAMETER
):
    """
    ...existing docstring...

    chunk_size : int, optional
        If provided, write units in chunks of this size to reduce peak memory usage.
        For large datasets (>10k units), recommended value is 100-500.
        Default is None (write all units at once).
    """

    if unit_ids is None:
        unit_ids = sorting.unit_ids

    # If chunking requested, process in batches
    if chunk_size is not None and len(unit_ids) > chunk_size:
        for i in range(0, len(unit_ids), chunk_size):
            chunk_unit_ids = unit_ids[i:i + chunk_size]

            # Get chunk-specific data
            chunk_waveform_means = waveform_means[i:i + chunk_size] if waveform_means is not None else None
            chunk_waveform_sds = waveform_sds[i:i + chunk_size] if waveform_sds is not None else None
            chunk_electrode_indices = unit_electrode_indices[i:i + chunk_size] if unit_electrode_indices is not None else None

            # Recursively call with chunk (no chunking on recursive call)
            _add_units_table_to_nwbfile(
                sorting=sorting,
                nwbfile=nwbfile,
                unit_ids=chunk_unit_ids,
                property_descriptions=property_descriptions,
                skip_properties=skip_properties,
                units_table_name=units_table_name,
                unit_table_description=unit_table_description,
                write_in_processing_module=write_in_processing_module,
                waveform_means=chunk_waveform_means,
                waveform_sds=chunk_waveform_sds,
                unit_electrode_indices=chunk_electrode_indices,
                null_values_for_properties=null_values_for_properties,
                chunk_size=None,  # Disable chunking for recursive call
            )
        return

    # ... rest of existing implementation ...
```

**Usage Example:**
```python
sorting_interface.add_to_nwbfile(
    nwbfile=nwbfile,
    metadata=metadata,
    chunk_size=100  # Process 100 units at a time
)
```

**Expected Impact:** Variable reduction (scales with chunk size; chunk_size=100 could reduce peak by ~10-15 GB)

**Difficulty:** Low (works with existing HDMF, pure workaround)

---

## Summary of Modifications

| # | Modification | Package | Files | Memory Saved | Difficulty | Dependencies |
|---|---|---|---|---|---|---|
| 1 | Eliminate list flattening | hdmf | `common/table.py:902` | ~9.9 GB | Medium | None |
| 2 | Optimize extend_data | hdmf | `data_utils.py:62` | ~3-4 GB | Medium | None |
| 2b | Add Zarr support to extend_data | hdmf | `data_utils.py:62` | None (parity fix) | Low | None |
| 3 | Add batch add_rows() | hdmf | `common/table.py` (new method) | ~1-2 GB | High | None |
| 4 | Preallocate extend | hdmf | `container.py:996` | ~1 GB | Low | None |
| 5 | Use batch add_rows | neuroconv | `spikeinterface.py:1686` | ~4-5 GB | High | Requires #3 |
| 6 | Keep numpy arrays | neuroconv + hdmf | `spikeinterface.py:1742` + `table.py:902` | ~2-3 GB | Medium | Coordination |
| 7 | Skip to_dataframe | neuroconv | `spikeinterface.py:1703` | ~1 GB | Low | None |
| 8 | Chunked writing | neuroconv | `spikeinterface.py:1487` | Variable (10-15 GB) | Low | None |

**Total Potential Reduction:** ~22-30 GB of total allocations, reducing peak from 23.4 GB → ~5-10 GB

---

## Implementation Roadmap

### Phase 1: Quick Wins (Low-Hanging Fruit)
**Timeline:** 1-2 weeks

These can be implemented independently without breaking changes:

1. **Modification #7** (NeuroConv): Skip to_dataframe
   - Single file change
   - No dependencies
   - Immediate ~1 GB savings

2. **Modification #8** (NeuroConv): Chunked writing
   - Workaround that works with current HDMF
   - Configurable via parameter
   - Immediate ~10-15 GB peak reduction

3. **Modification #4** (HDMF): Preallocate extend
   - Backward compatible
   - Optional parameter
   - ~1 GB savings

4. **Modification #2b** (HDMF): Add Zarr support to extend_data
   - Backend parity fix
   - Low risk
   - No immediate memory impact

**Expected Phase 1 Impact:** Peak memory 23.4 GB → ~12-15 GB

---

### Phase 2: Medium Complexity
**Timeline:** 1-2 months

Requires coordination but no breaking API changes:

4. **Modification #1** (HDMF): Eliminate list flattening
   - Needs testing with HDF5 backend
   - May require changes to backend write logic
   - ~9.9 GB savings

5. **Modification #6** (NeuroConv + HDMF): Keep numpy arrays
   - Requires both packages to coordinate
   - Changes data representation
   - ~2-3 GB savings

6. **Modification #2** (HDMF): Optimize extend_data
   - New function, keep old for compatibility
   - ~3-4 GB savings

**Expected Phase 2 Impact:** Peak memory ~12-15 GB → ~5-8 GB

---

### Phase 3: Long-Term Architecture
**Timeline:** 2-3 months

Requires API additions and thorough testing:

7. **Modification #3** (HDMF): Add batch add_rows()
   - New API method
   - Extensive testing needed
   - ~1-2 GB savings

8. **Modification #5** (NeuroConv): Use batch add_rows
   - Depends on #3
   - Requires version detection
   - ~4-5 GB savings

**Expected Final Impact:** Peak memory ~5-8 GB

---

## Testing Strategy

### Memory Benchmarks

Create standardized memory benchmarks for:

1. **Small dataset** (~10 units, ~10k spikes each)
   - Baseline for regression testing
   - Should run quickly in CI

2. **Medium dataset** (~100 units, ~100k spikes each)
   - Typical experimental session
   - Target for optimization validation

3. **Large dataset** (~500 units, ~1M spikes each)
   - IBL brain-wide map scale
   - Stress test for modifications

### Verification

Each modification should include:

1. **Unit tests** for new functionality
2. **Integration tests** with existing code
3. **Memory profiling** before/after with `memray`
4. **Benchmark comparison** against baseline
5. **HDF5 output validation** (ensure file integrity)

### Compatibility

- Maintain backward compatibility where possible
- Use feature detection for new APIs (`hasattr` checks)
- Document minimum required versions

---

## Additional Considerations

### Alternative: Direct HDF5 Writing

A more radical approach would be to bypass HDMF's in-memory table construction entirely and write directly to HDF5:

```python
# Pseudocode
with h5py.File(nwb_path, 'a') as f:
    units_group = f.create_group('units')

    # Pre-calculate sizes
    total_spikes = sum(len(get_spike_times(uid)) for uid in unit_ids)

    # Create datasets with final size
    spike_times_ds = units_group.create_dataset(
        'spike_times',
        shape=(total_spikes,),
        dtype='f8'
    )
    spike_times_index_ds = units_group.create_dataset(
        'spike_times_index',
        shape=(len(unit_ids),),
        dtype='i8'
    )

    # Fill in one pass
    offset = 0
    for i, uid in enumerate(unit_ids):
        times = get_spike_times(uid)
        spike_times_ds[offset:offset+len(times)] = times
        offset += len(times)
        spike_times_index_ds[i] = offset
```

**Pros:**
- Minimal memory footprint (streaming)
- Complete control over allocation
- Can use HDF5 compression

**Cons:**
- Bypasses HDMF validation
- Loses abstraction layer
- Harder to maintain NWB schema compliance
- Significant development effort

This should be considered only if the above modifications prove insufficient.

---

## References

- [Memray Documentation](https://bloomberg.github.io/memray/)
- [HDMF Repository](https://github.com/hdmf-dev/hdmf)
- [NeuroConv Repository](https://github.com/catalystneuro/neuroconv)
- [NWB Format Specification](https://nwb-schema.readthedocs.io/)
- IBL Conversion Repository (internal)

---

## Appendix: Profiling Commands

```bash
# Run memory profiling
memray run --native --output ./memray_output.bin script.py

# Generate flamegraph
memray flamegraph memray_output.bin

# View statistics
memray stats memray_output.bin

# Generate table view
memray table memray_output.bin
```

### Example Profile Script

```python
from pathlib import Path
from one.api import ONE
from ibl_to_nwb.datainterfaces import IblSortingInterface
import datetime

# Setup
cache_dir = Path("/path/to/cache")
one = ONE(base_url='https://openalyx.internationalbrainlab.org',
          cache_dir=cache_dir, silent=True)

eid = "fece187f-b47f-4870-a1d6-619afe942a7d"
revision = "2024-05-06"

# Create interface
sorting_interface = IblSortingInterface(
    one=one,
    session=eid,
    revision=revision,
)

# Create NWBFile
metadata = sorting_interface.get_metadata()
metadata["NWBFile"]["session_start_time"] = datetime.datetime.now()

nwbfile = sorting_interface.create_nwbfile(metadata=metadata)

# This is where memory profiling focuses
sorting_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)
```

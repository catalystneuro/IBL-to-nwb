# Memory Issue Reproduction Demo

This directory contains a minimal script to reproduce the HDMF memory issues documented in `memory_optimization_proposal.md`.

## Quick Start

### 1. Run with memray profiling

```bash
# Install memray if needed
pip install memray

# Run the script with memory profiling
memray run --native --output issue_demo.bin reproduce_memory_issue.py
```

### 2. Analyze the results

```bash
# View statistics
memray stats issue_demo.bin

# Generate interactive flamegraph
memray flamegraph issue_demo.bin

# Open the generated HTML in browser
firefox memray-flamegraph-issue_demo.html
```

## What to Look For

The script demonstrates three main memory issues:

### Phase 1: `add_unit()` Loop (Lines 59-71)
- **Problem**: Each call extends internal Python lists, causing O(n²) reallocations
- **In flamegraph**: Look for `extend_data` → `list.extend` → `PyMem_Realloc`
- **Expected allocation**: ~50-100 MB for 300 units

### Phase 2: `add_column()` with Ragged Arrays (Lines 78-95)
- **Problem**: Creates giant flattened list via `list(itertools.chain.from_iterable())`
- **In flamegraph**: Look for `add_column` → `chain.from_iterable` → `list___init___impl`
- **Expected allocation**: ~200-400 MB for 300 units × 10k spikes

### Phase 3: `to_dataframe()` (Lines 100-103)
- **Problem**: Creates entire pandas DataFrame copy of table
- **In flamegraph**: Look for `to_dataframe` → pandas operations
- **Expected allocation**: ~100-200 MB

## Scaling the Test

Edit the configuration variables in `reproduce_memory_issue.py`:

```python
NUM_UNITS = 300          # Try 500, 1000 to see memory scale
SPIKES_PER_UNIT = 10000  # Try 50000, 100000 for IBL-scale data
NUM_PROPERTIES = 2       # Number of ragged properties
```

### Example: IBL-scale test

```python
NUM_UNITS = 500          # Typical IBL session
SPIKES_PER_UNIT = 50000  # More realistic spike counts
```

Expected peak memory: **~5-8 GB** (demonstrates the real issue)

## Expected Output

### Console Output

```
Creating Units table with 300 units, ~10000 spikes each
Expected data size: ~0.02 GB per property
================================================================================

Phase 1: Adding units one by one (demonstrates add_unit memory issue)
--------------------------------------------------------------------------------
  Added 50/300 units...
  Added 100/300 units...
  ...
✓ Added all 300 units
  Current table size: 300 rows
  Data type: <class 'list'>  ← Note: Python list, not HDF5!
...
```

### Memray Stats Output

```
📏 Total allocations:
    XXXXX

📦 Total memory allocated:
    X.XXX GB

📈 Peak memory usage:
    XXX MB

🥇 Top 5 largest allocating locations (by size):
    - add_column:/path/to/hdmf/common/table.py:902 -> X.XX GB
    - extend_data:/path/to/hdmf/data_utils.py:62 -> X.XX GB
    ...
```

## Comparison with Real IBL Data

| Metric | Demo Script (300 units) | Real IBL (500 units) |
|--------|------------------------|---------------------|
| Units | 300 | 500 |
| Spikes/unit | 10,000 | 30,000-100,000 |
| Peak memory | ~500 MB | ~23 GB |
| File size | ~70 MB | ~2-5 GB |
| Memory/File ratio | ~7x | ~10-15x |

The ratio shows memory overhead is much worse than the final file size!

## Files Generated

- `issue_demo.bin` - Memray capture file
- `memray-flamegraph-issue_demo.html` - Interactive visualization
- `/tmp/test_memory_issue.nwb` - Output NWB file

## Next Steps

After confirming the issue, see `memory_optimization_proposal.md` for:
- Detailed explanation of root causes
- 8 proposed modifications to HDMF and NeuroConv
- Implementation roadmap
- Expected memory reductions

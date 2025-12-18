"""
Minimal script to reproduce HDMF memory issues with DynamicTable.

This script demonstrates the memory inefficiency of HDMF's DynamicTable
when adding units with ragged arrays (spike times, amplitudes, depths).

Run with memray:
    memray run --native --output issue_demo.bin reproduce_memory_issue.py
    memray flamegraph issue_demo.bin
    memray stats issue_demo.bin
"""

import numpy as np
import pynwb
from datetime import datetime

# Configuration: adjust these to see memory scaling
NUM_UNITS = 300  # Number of units to add
SPIKES_PER_UNIT = 10000  # Average spikes per unit
NUM_PROPERTIES = 2  # Number of ragged array properties (spike_amplitudes, spike_depths)

print(f"Creating Units table with {NUM_UNITS} units, ~{SPIKES_PER_UNIT} spikes each")
print(f"Expected data size: ~{NUM_UNITS * SPIKES_PER_UNIT * 8 / 1e9:.2f} GB per property")
print("=" * 80)

# Create NWBFile
nwbfile = pynwb.NWBFile(
    session_description='Memory test',
    identifier='test_memory',
    session_start_time=datetime.now()
)

# Create Units table
units_table = pynwb.misc.Units(name='units', description='Test units table')
nwbfile.units = units_table

print("\nPhase 1: Adding units one by one (demonstrates add_unit memory issue)")
print("-" * 80)

# Simulate spike data for all units
np.random.seed(42)
all_spike_times = []
all_spike_amplitudes = []
all_spike_depths = []

for unit_idx in range(NUM_UNITS):
    # Generate random spike data
    n_spikes = np.random.poisson(SPIKES_PER_UNIT)
    spike_times = np.sort(np.random.rand(n_spikes) * 1000)  # 0-1000 seconds
    spike_amplitudes = np.random.randn(n_spikes) * 50 + 100  # μV
    spike_depths = np.random.rand(n_spikes) * 3000  # μm along probe

    all_spike_times.append(spike_times)
    all_spike_amplitudes.append(spike_amplitudes)
    all_spike_depths.append(spike_depths)

    # This is where memory blows up - each add_unit extends internal lists
    units_table.add_unit(
        spike_times=spike_times,
        # We'll add these as ragged columns later to show the column memory issue
    )

    if (unit_idx + 1) % 50 == 0:
        print(f"  Added {unit_idx + 1}/{NUM_UNITS} units...")

print(f"✓ Added all {NUM_UNITS} units")
print(f"  Current table size: {len(units_table)} rows")
print(f"  Data type: {type(units_table.id.data)}")

# Phase 2: Add ragged array columns (demonstrates add_column memory issue)
print("\nPhase 2: Adding ragged array columns (demonstrates add_column memory issue)")
print("-" * 80)

# Convert to numpy object array (list of arrays)
spike_amplitudes_ragged = np.array(all_spike_amplitudes, dtype=object)
spike_depths_ragged = np.array(all_spike_depths, dtype=object)

print(f"  Adding spike_amplitudes column...")
# This creates a HUGE temporary list via list(itertools.chain.from_iterable())
units_table.add_column(
    name='spike_amplitudes',
    description='Amplitude of each spike',
    data=spike_amplitudes_ragged,
    index=True  # Ragged array, needs VectorIndex
)
print(f"  ✓ Added spike_amplitudes")

print(f"  Adding spike_depths column...")
units_table.add_column(
    name='spike_depths',
    description='Depth of each spike along probe',
    data=spike_depths_ragged,
    index=True
)
print(f"  ✓ Added spike_depths")

# Phase 3: Demonstrate to_dataframe memory issue
print("\nPhase 3: Converting to DataFrame (demonstrates to_dataframe memory issue)")
print("-" * 80)

print("  Creating DataFrame from table...")
df = units_table.to_dataframe()
print(f"  ✓ DataFrame created with shape {df.shape}")

# Phase 4: Write to file (this is fast, memory already allocated)
print("\nPhase 4: Writing to HDF5")
print("-" * 80)

output_path = "/tmp/test_memory_issue.nwb"
print(f"  Writing to {output_path}...")

with pynwb.NWBHDF5IO(output_path, mode='w') as io:
    io.write(nwbfile)

print(f"  ✓ File written successfully")

# Print summary
import os
file_size_mb = os.path.getsize(output_path) / 1e6
print("\n" + "=" * 80)
print("Summary:")
print(f"  Units: {NUM_UNITS}")
print(f"  Total spikes: {sum(len(st) for st in all_spike_times):,}")
print(f"  File size: {file_size_mb:.1f} MB")
print(f"  Peak memory: (check memray output)")
print("=" * 80)

print("\nTo analyze memory:")
print("  memray stats issue_demo.bin")
print("  memray flamegraph issue_demo.bin")

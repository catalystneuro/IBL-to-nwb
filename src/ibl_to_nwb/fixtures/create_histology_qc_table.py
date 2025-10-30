"""
Create a pre-computed histology QC table for fast anatomical localization availability checks.

This script queries the Alyx database for all BWM probe insertions and extracts histology
quality information, creating a lookup table that can be used for fast QC filtering without
API calls during conversion.
"""

from pathlib import Path
import pandas as pd
from one.api import ONE
from tqdm import tqdm
import csv

# Setup - use relative path from script location
script_dir = Path(__file__).parent
fixtures_path = script_dir
cache_dir = Path('/media/heberto/Expansion/ibl_cache')
one = ONE(base_url='https://openalyx.internationalbrainlab.org', cache_dir=cache_dir, silent=True)

# Load the BWM probe insertions table
print("Loading BWM probe insertions...")
bwm_df = pd.read_parquet(fixtures_path / "bwm_df.pqt")
print(f"Found {len(bwm_df)} probe insertions across {bwm_df['eid'].nunique()} sessions")

# Output file
output_csv = fixtures_path / "bwm_histology_qc.csv"

# CSV column names
fieldnames = [
    'eid',
    'pid',
    'probe_name',
    'histology_quality',
    'has_histology_files',
    'tracing_exists',
    'alignment_resolved',
    'alignment_count'
]

print(f"\nStreaming results to: {output_csv}")
print("Querying histology quality for each probe insertion...\n")

# Open CSV file and write header, then stream rows one by one
with open(output_csv, 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()

    # Process each probe insertion
    for idx, row in tqdm(bwm_df.iterrows(), total=len(bwm_df)):
        eid = row['eid']
        pid = row['pid']
        probe_name = row['probe_name']

        result = {
            'eid': eid,
            'pid': pid,
            'probe_name': probe_name,
            'histology_quality': None,
            'has_histology_files': False,
            'tracing_exists': None,
            'alignment_resolved': None,
            'alignment_count': None,
        }

        # Check if histology files exist (electrodeSites.* = final 'alf' quality data)
        datasets = one.list_datasets(eid)
        histology_patterns = [
            f'alf/{probe_name}/electrodeSites.localCoordinates.npy',
            f'alf/{probe_name}/electrodeSites.mlapdv.npy',
            f'alf/{probe_name}/electrodeSites.brainLocationIds_ccf_2017.npy',
        ]

        has_alf_files = all(
            any(pattern in str(d) for d in datasets)
            for pattern in histology_patterns
        )
        result['has_histology_files'] = has_alf_files

        # Get histology quality directly from Alyx insertion metadata (fast - no file downloads!)
        insertion = one.alyx.rest('insertions', 'read', id=pid)
        extended_qc = insertion.get('json', {}).get('extended_qc', {})

        result['tracing_exists'] = extended_qc.get('tracing_exists')
        result['alignment_resolved'] = extended_qc.get('alignment_resolved')
        result['alignment_count'] = extended_qc.get('alignment_count', 0)

        # Determine quality level
        # Quality hierarchy: 'alf' (best) > 'resolved' (good) > 'aligned' (partial) > 'traced' (minimal) > None
        if has_alf_files:
            histology_quality = 'alf'  # Best: Final processed files exist
        elif extended_qc.get('tracing_exists') and extended_qc.get('alignment_resolved'):
            histology_quality = 'resolved'  # Good: Alignment finalized
        elif extended_qc.get('alignment_count', 0) > 0:
            histology_quality = 'aligned'  # Partial: Alignment attempted
        elif extended_qc.get('tracing_exists'):
            histology_quality = 'traced'  # Minimal: Only tracing, no alignment
        else:
            histology_quality = None  # No histology

        result['histology_quality'] = histology_quality

        # Write row immediately to CSV (streaming!)
        writer.writerow(result)

# Read back for summary stats
print("\nReading results for summary...")
histology_qc_df = pd.read_csv(output_csv)

# Print summary
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"Total probe insertions: {len(histology_qc_df)}")

print(f"\nHistology files:")
print(f"  Has files: {histology_qc_df['has_histology_files'].sum()} ({100*histology_qc_df['has_histology_files'].sum()/len(histology_qc_df):.1f}%)")
print(f"  Missing:   {(~histology_qc_df['has_histology_files']).sum()} ({100*(~histology_qc_df['has_histology_files']).sum()/len(histology_qc_df):.1f}%)")

print(f"\nHistology quality distribution:")
quality_counts = histology_qc_df['histology_quality'].value_counts()
for quality, count in quality_counts.items():
    pct = 100 * count / len(histology_qc_df)
    print(f"  {str(quality):15s}: {count:3d} ({pct:5.1f}%)")

print(f"\nUsable for anatomical localization (quality='alf' or 'resolved'):")
usable = histology_qc_df['histology_quality'].isin(['alf', 'resolved'])
print(f"  Usable: {usable.sum()} ({100*usable.sum()/len(histology_qc_df):.1f}%)")

print(f"\nOutput file:")
print(f"  {output_csv}")

print("\nDone!")

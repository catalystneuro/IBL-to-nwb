"""
Compare waveform template sources: clusters.waveforms vs waveforms.templates.

This script checks if the channel 383 artifact is present in both:
- clusters.waveforms.npy (32 channels, 82 samples, proximity order)
- waveforms.templates.npy (128 channels, 40 samples, depth order)
"""

import numpy as np
from brainbox.io.one import SpikeSortingLoader
from one.api import ONE

# Configuration
SESSION_EID = "6ed57216-498d-48a6-b48b-a243a34710ea"
PROBE_NAME = "probe00"
REVISION = "2025-05-06"

# Load data from IBL
one = ONE()
ssl = SpikeSortingLoader(eid=SESSION_EID, one=one, pname=PROBE_NAME)
spikes, clusters, channels = ssl.load_spike_sorting(revision=REVISION)

# Load clusters.waveforms (32 channels, 82 samples, proximity order)
clusters_data = ssl.load_spike_sorting_object(
    "clusters",
    dataset_types=["clusters.waveformsChannels", "clusters.waveforms"],
    revision=REVISION,
)
clusters_templates = clusters_data["waveforms"] * 1e6  # Convert to uV
clusters_channels = clusters_data["waveformsChannels"]

# Load waveforms.templates (128 channels, 40 samples, depth order)
try:
    waveforms_data = ssl.load_spike_sorting_object("waveforms", revision=REVISION)
    waveforms_templates = waveforms_data["templates"] * 1e6  # Convert to uV
    has_waveforms_templates = True
    print("Successfully loaded both data sources:")
    print(f"  clusters.waveforms shape: {clusters_templates.shape}")
    print(f"  waveforms.templates shape: {waveforms_templates.shape}")
except Exception as e:
    print(f"Could not load waveforms.templates: {e}")
    has_waveforms_templates = False

max_channels = clusters["channels"]
n_clusters = len(max_channels)

# Summary statistics
print(f"\n{'='*60}")
print("Summary: Checking for NaN values in waveforms.templates")
print(f"{'='*60}")

if has_waveforms_templates:
    nan_per_cluster = np.isnan(waveforms_templates).all(axis=(1, 2))
    clusters_with_nan = np.sum(nan_per_cluster)
    clusters_with_data = n_clusters - clusters_with_nan
    print(f"Total clusters: {n_clusters}")
    print(f"Clusters with valid waveforms.templates: {clusters_with_data}")
    print(f"Clusters with all-NaN waveforms.templates: {clusters_with_nan}")

    # Find clusters that have data in both sources
    valid_cluster_indices = np.where(~nan_per_cluster)[0]
    print(f"\nFirst 10 valid cluster indices: {valid_cluster_indices[:10]}")

# Analyze clusters with ch 383 in their neighborhood
print(f"\n{'='*60}")
print("Analysis: Clusters with channel 383 in clusters.waveforms")
print(f"{'='*60}")

clusters_with_383 = []
for idx in range(n_clusters):
    if 383 in clusters_channels[idx]:
        clusters_with_383.append(idx)

print(f"\nClusters that include channel 383: {len(clusters_with_383)}")
print(f"Examples: {clusters_with_383[:10]}")

# Detailed analysis of a few clusters
for cluster_idx in clusters_with_383[:5]:
    print(f"\n--- Cluster {cluster_idx} ---")

    # clusters.waveforms analysis
    template_clusters = clusters_templates[cluster_idx]
    template_chans = clusters_channels[cluster_idx]
    ibl_max_channel = max_channels[cluster_idx]

    p2p_clusters = template_clusters.max(axis=0) - template_clusters.min(axis=0)
    actual_max_pos = np.argmax(p2p_clusters)
    ibl_max_pos = np.where(template_chans == ibl_max_channel)[0][0]
    ch383_pos = np.where(template_chans == 383)[0]

    print("clusters.waveforms:")
    print(f"  IBL max channel: {ibl_max_channel}, amplitude: {p2p_clusters[ibl_max_pos]:.1f} uV")
    print(f"  Actual max: ch {template_chans[actual_max_pos]}, amplitude: {p2p_clusters[actual_max_pos]:.1f} uV")
    if len(ch383_pos) > 0:
        print(f"  Channel 383 amplitude: {p2p_clusters[ch383_pos[0]]:.1f} uV")

    # waveforms.templates analysis
    if has_waveforms_templates:
        template_wf = waveforms_templates[cluster_idx]
        if np.isnan(template_wf).all():
            print("waveforms.templates: ALL NaN")
        else:
            p2p_wf = np.nanmax(template_wf, axis=0) - np.nanmin(template_wf, axis=0)
            valid_mask = ~np.isnan(p2p_wf)
            valid_count = valid_mask.sum()
            if valid_count > 0:
                max_amp_idx = np.nanargmax(p2p_wf)
                print("waveforms.templates:")
                print(f"  Valid channels: {valid_count}/128")
                print(f"  Max amplitude at index {max_amp_idx}: {p2p_wf[max_amp_idx]:.1f} uV")
                print(f"  Last channel (idx 127) amplitude: {p2p_wf[127]:.1f} uV")

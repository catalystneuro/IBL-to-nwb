import matplotlib.pyplot as plt
import numpy as np
from brainbox.io.one import SpikeSortingLoader
from one.api import ONE

# Configuration
SESSION_EID = "6ed57216-498d-48a6-b48b-a243a34710ea"
PROBE_NAME = "probe00"
REVISION = "2025-05-06"
CLUSTER_INDEX = 330  # Example cluster with artifact

# Load data from IBL
one = ONE()
ssl = SpikeSortingLoader(eid=SESSION_EID, one=one, pname=PROBE_NAME)
spikes, clusters, channels = ssl.load_spike_sorting(revision=REVISION)

# Load clusters.waveforms
additional_data = ssl.load_spike_sorting_object(
    "clusters",
    dataset_types=["clusters.waveformsChannels", "clusters.waveforms"],
    revision=REVISION,
)

# clusters.waveforms contains templates (mean waveforms), not individual spike waveforms
clusters_waveforms = additional_data["waveforms"] * 1e6  # Convert to uV
waveform_channels = additional_data["waveformsChannels"]
max_channels = clusters["channels"]

# Load templates.waveforms for comparison
templates_data = ssl.load_spike_sorting_object(
    "templates",
    dataset_types=["templates.waveforms"],
    revision=REVISION,
)
templates_waveforms = templates_data["waveforms"] * 1e6  # Convert to uV

# Verify clusters.waveforms == templates.waveforms
are_identical = np.allclose(clusters_waveforms, templates_waveforms, equal_nan=True)
if not are_identical:
    raise ValueError("clusters.waveforms and templates.waveforms do not match!")

# Use clusters.waveforms for analysis (they're the same)
waveform_templates = clusters_waveforms

# Analyze cluster
template = waveform_templates[CLUSTER_INDEX]
template_chans = waveform_channels[CLUSTER_INDEX]
ibl_max_channel = max_channels[CLUSTER_INDEX]

# Find actual max and IBL max positions
p2p = template.max(axis=0) - template.min(axis=0)
actual_max_pos = np.argmax(p2p)
ibl_max_pos = np.where(template_chans == ibl_max_channel)[0][0]


# Plot comparison
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
time_ms = (np.arange(82) - 41) / 30.0

# Real signal (from clusters.channels)
ax = axes[0]
trace = template[:, ibl_max_pos]
ax.plot(time_ms, trace, "k-", linewidth=1.5)
ax.fill_between(time_ms, 0, trace, where=(trace > 0), color="orange", alpha=0.7)
ax.fill_between(time_ms, 0, trace, where=(trace < 0), color="slateblue", alpha=0.7)
ax.axhline(0, color="gray", linestyle="--", linewidth=0.5)
ax.set_xlabel("Time (ms)")
ax.set_ylabel("Amplitude (uV)")
ax.set_title(f"Real signal (ch {ibl_max_channel})\nPeak-to-peak: {p2p[ibl_max_pos]:.1f} uV")

# Artifact (actual max in template)
ax = axes[1]
trace = template[:, actual_max_pos]
ax.plot(time_ms, trace, "k-", linewidth=1.5)
ax.fill_between(time_ms, 0, trace, where=(trace > 0), color="orange", alpha=0.7)
ax.fill_between(time_ms, 0, trace, where=(trace < 0), color="slateblue", alpha=0.7)
ax.axhline(0, color="gray", linestyle="--", linewidth=0.5)
ax.set_xlabel("Time (ms)")
ax.set_ylabel("Amplitude (uV)")
ax.set_title(f"Artifact (ch {template_chans[actual_max_pos]})\nPeak-to-peak: {p2p[actual_max_pos]:.1f} uV")

plt.suptitle(
    f"Cluster {CLUSTER_INDEX}: Real signal vs Artifact on channel 383\n" f"EID: {SESSION_EID}  PID: {ssl.pid}",
    fontweight="bold",
)
plt.tight_layout()
plt.savefig("waveform_template_artifact_example.png", dpi=150, bbox_inches="tight")

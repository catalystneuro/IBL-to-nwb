"""Plot spike raster by depth.

This script creates a raster plot showing spikes from good units across
task and passive epochs, organized by depth from probe tip.

Usage:
    uv run python plot_spike_raster_by_depth.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from pynwb import read_nwb

from _common import create_argument_parser, save_figure


def plot_spike_raster_by_depth(nwbfile, probe_name: str | None = None) -> plt.Figure:
    """Create spike raster plot organized by depth.

    Parameters
    ----------
    nwbfile : NWBFile
        The NWB file object (processed).
    probe_name : str, optional
        Name of the probe to plot. If None, uses the first probe.

    Returns
    -------
    plt.Figure
        The matplotlib figure.
    """
    units_df = nwbfile.units.to_dataframe()
    epochs_df = nwbfile.epochs.to_dataframe()

    if probe_name is None:
        probe_name = sorted(units_df["probe_name"].unique())[0]

    units_probe_df = units_df[units_df["probe_name"] == probe_name]

    task_epoch = epochs_df[epochs_df["protocol_type"] == "task"].iloc[0]
    passive_epoch = epochs_df[epochs_df["protocol_type"] == "passive"].iloc[0]

    task_duration = task_epoch["stop_time"] - task_epoch["start_time"]
    passive_duration = passive_epoch["stop_time"] - passive_epoch["start_time"]

    df = units_probe_df[units_probe_df["ibl_quality_score"] == 1].copy()
    n_good_units = len(df)

    units_probe = df.sort_values("distance_from_probe_tip_um")

    fig, ax = plt.subplots(figsize=(14, 8))

    ax.axvspan(
        task_epoch["start_time"],
        task_epoch["stop_time"],
        color="lightblue",
        alpha=0.3,
        label=f"Task ({task_duration/60:.1f} min)",
    )
    ax.axvspan(
        passive_epoch["start_time"],
        passive_epoch["stop_time"],
        color="lightyellow",
        alpha=0.3,
        label=f"Passive ({passive_duration/60:.1f} min)",
    )

    for _, unit in units_probe.iterrows():
        spike_times = unit["spike_times"]
        depth = unit["distance_from_probe_tip_um"]

        ax.scatter(
            spike_times,
            np.full(len(spike_times), depth),
            c="black",
            s=1.0,
            marker="|",
            linewidths=0.5,
            alpha=0.5,
        )

    ax.axvline(
        task_epoch["stop_time"],
        color="red",
        linestyle="--",
        linewidth=1.5,
        label="Task/Passive boundary",
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Distance From Probe Tip (um)")
    ax.set_title(
        f"Spike Raster by Depth - {probe_name} ({n_good_units} good units)\nSession: {nwbfile.session_id}",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_xlim(0, passive_epoch["stop_time"])
    ax.set_ylim(0, units_probe["distance_from_probe_tip_um"].max() + 100)

    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9)

    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot spike raster by depth",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating spike raster plot...")
    fig = plot_spike_raster_by_depth(nwbfile)

    output_path = save_figure(fig, "plot_spike_raster_by_depth")
    print(f"Figure saved to: {output_path}")


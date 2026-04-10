"""Plot units scatter plots.

This script creates scatter plots showing unit properties:
- Left: Amplitude vs depth colored by Kilosort2 label
- Right: Amplitude vs depth colored by firing rate (good units only)

Usage:
    uv run python plot_units_scatter.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from _common import create_argument_parser, save_figure
from pynwb import read_nwb


def plot_units_scatter(nwbfile, probe_name: str | None = None) -> plt.Figure:
    """Create units scatter plot.

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

    if probe_name is None:
        probe_name = sorted(units_df["probe_name"].unique())[0]

    units_probe_df = units_df[units_df["probe_name"] == probe_name]

    fig, axes = plt.subplots(1, 2, figsize=(12, 9), sharey=True)

    # Left plot - colored by kilosort2_label
    value_to_color = {"mua": "red", "good": "green"}

    for label, color in value_to_color.items():
        subset = units_probe_df[units_probe_df["kilosort2_label"] == label]
        axes[0].scatter(
            subset["median_spike_amplitude_uV"],
            subset["distance_from_probe_tip_um"],
            c=color,
            label=label,
            s=100,
        )
    axes[0].set_xlim([0, 800])
    axes[0].set_xlabel("median_spike_amplitude_uV")
    axes[0].set_ylabel("distance_from_probe_tip_um")
    axes[0].set_title("By Kilosort2 Label")
    axes[0].legend()

    # Right plot - colored by firing_rate (good units only)
    df_good = units_probe_df[units_probe_df["ibl_quality_score"] == 1]

    scatter = axes[1].scatter(
        df_good["median_spike_amplitude_uV"],
        df_good["distance_from_probe_tip_um"],
        c=df_good["firing_rate"],
        cmap="inferno",
        s=100,
    )
    axes[1].set_xlim([0, 800])
    axes[1].set_xlabel("median_spike_amplitude_uV")
    axes[1].set_title("By Firing Rate (Quality=1)")

    fig.colorbar(scatter, ax=axes[1], label="firing_rate (Hz)")

    fig.suptitle(f"Units Scatter - {probe_name}\nSession: {nwbfile.session_id}", fontsize=12, fontweight="bold")
    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot units scatter plots",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating units scatter plot...")
    fig = plot_units_scatter(nwbfile)

    output_path = save_figure(fig, "plot_units_scatter")
    print(f"Figure saved to: {output_path}")

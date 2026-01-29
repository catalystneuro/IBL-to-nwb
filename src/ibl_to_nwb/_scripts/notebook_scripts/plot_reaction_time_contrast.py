"""Plot reaction time by contrast.

This script creates a visualization showing median reaction time vs signed contrast
for each block type (p_left = 0.2, 0.5, 0.8).

Usage:
    uv run python plot_reaction_time_contrast.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from pynwb import read_nwb

from _common import create_argument_parser, save_figure


def plot_reaction_time_contrast(nwbfile) -> plt.Figure:
    """Create reaction time by contrast visualization.

    Parameters
    ----------
    nwbfile : NWBFile
        The NWB file object (processed).

    Returns
    -------
    plt.Figure
        The matplotlib figure.
    """
    trials_df = nwbfile.trials.to_dataframe()

    # Calculate reaction time and signed contrast
    trials_df["reaction_time"] = trials_df["wheel_movement_onset_time"] - trials_df["gabor_stimulus_onset_time"]

    # Signed contrast: positive = left stimulus, negative = right stimulus
    contrast = trials_df["gabor_stimulus_contrast"].values
    side = trials_df["gabor_stimulus_side"].values
    trials_df["signed_contrast"] = np.where(side == "left", contrast, -contrast)

    # Get unique contrasts sorted
    contrasts = sorted(trials_df["signed_contrast"].unique())

    # Define block styles
    blocks = {
        0.5: {"color": "black", "label": "p_left=0.5"},
        0.2: {"color": "tab:red", "label": "p_left=0.2"},
        0.8: {"color": "tab:blue", "label": "p_left=0.8"},
    }

    # Plot reaction time by contrast for each block
    fig, ax = plt.subplots(figsize=(8, 6))

    for p_left, style in blocks.items():
        block_trials = trials_df[trials_df["probability_left"] == p_left]

        if len(block_trials) == 0:
            continue

        # Calculate median reaction time for each contrast
        median_rt = []
        contrast_vals = []

        for c in contrasts:
            contrast_trials = block_trials[block_trials["signed_contrast"] == c]
            if len(contrast_trials) > 0:
                median_rt.append(contrast_trials["reaction_time"].median())
                contrast_vals.append(c)

        ax.plot(
            contrast_vals,
            median_rt,
            "o-",
            color=style["color"],
            label=f"{style['label']} ({len(block_trials)} trials)",
            linewidth=1.5,
            markersize=6,
        )

    # Formatting
    ax.set_xlabel("Contrasts")
    ax.set_ylabel("Reaction time (s)")
    ax.set_xlim(-110, 110)
    ax.set_ylim(0, None)
    ax.axvline(0, color="gray", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.legend(loc="upper right", fontsize=9)

    ax.set_title(f"Reaction Time by Contrast\nSession: {nwbfile.session_id}", fontsize=12, fontweight="bold")

    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot reaction time by contrast",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating reaction time plot...")
    fig = plot_reaction_time_contrast(nwbfile)

    output_path = save_figure(fig, "plot_reaction_time_contrast")
    print(f"Figure saved to: {output_path}")


"""Plot trials overview.

This script creates a visualization showing trial-by-trial performance
with signed contrast on y-axis, colored by block type and outcome.

Usage:
    uv run python plot_trials_overview.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from pynwb import read_nwb

from _common import create_argument_parser, save_figure


def plot_trials_overview(nwbfile) -> plt.Figure:
    """Create trials overview visualization.

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

    # Compute signed contrast for y-position
    contrast = trials_df["gabor_stimulus_contrast"].values
    side = trials_df["gabor_stimulus_side"].values
    signed_contrast = np.where(side == "left", contrast, -contrast)
    trials_df["signed_contrast"] = signed_contrast

    # Add jitter for overlapping points
    np.random.seed(42)
    trials_df["y_jitter"] = signed_contrast + np.random.uniform(-3, 3, len(trials_df))

    # Define block background colors
    block_bg_colors = {
        "unbiased": "#E0E0E0",
        "left_block": "#B3D9FF",
        "right_block": "#FFD9B3",
    }
    block_labels = {
        "unbiased": "Unbiased (p_left=0.5)",
        "left_block": "Left block (p_left=0.8)",
        "right_block": "Right block (p_left=0.2)",
    }

    fig, ax = plt.subplots(figsize=(14, 6))

    # Plot block backgrounds
    block_changes = trials_df["block_index"].diff().fillna(1) != 0
    block_starts = trials_df.index[block_changes].tolist()
    block_starts.append(len(trials_df))

    added_labels = set()
    for i in range(len(block_starts) - 1):
        start_index = block_starts[i]
        end_index = block_starts[i + 1]
        block_type = trials_df.loc[start_index, "block_type"]
        label = block_labels.get(block_type) if block_type not in added_labels else None
        ax.axvspan(
            start_index,
            end_index,
            color=block_bg_colors.get(block_type, "white"),
            alpha=0.5,
            zorder=0,
            label=label,
        )
        added_labels.add(block_type)

    # Plot correct trials (blue circles)
    correct = trials_df[trials_df["is_mouse_rewarded"]]
    ax.scatter(
        correct.index,
        correct["y_jitter"],
        marker="o",
        s=20,
        facecolors="none",
        edgecolors="blue",
        linewidths=1,
        label="Correct",
        zorder=2,
    )

    # Plot incorrect trials (red X)
    incorrect = trials_df[~trials_df["is_mouse_rewarded"]]
    ax.scatter(
        incorrect.index,
        incorrect["y_jitter"],
        color="red",
        marker="x",
        s=20,
        linewidths=1,
        label="Incorrect",
        zorder=2,
    )

    # Formatting
    ax.set_xlabel("Trial number")
    ax.set_ylabel("Signed contrast (%)")
    ax.set_xlim(-5, len(trials_df) + 5)
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.5, alpha=0.5)

    # Session info
    subject = nwbfile.subject.subject_id if nwbfile.subject else "Unknown"
    session_date = nwbfile.session_start_time.strftime("%Y-%m-%d")
    n_correct = len(correct)
    performance = n_correct / len(trials_df) * 100

    ax.set_title(f"{subject} - {session_date} ({len(trials_df)} trials, {performance:.1f}% correct)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9)

    plt.tight_layout(rect=[0, 0, 0.85, 1])

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot trials overview",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating trials overview plot...")
    fig = plot_trials_overview(nwbfile)

    output_path = save_figure(fig, "plot_trials_overview")
    print(f"Figure saved to: {output_path}")


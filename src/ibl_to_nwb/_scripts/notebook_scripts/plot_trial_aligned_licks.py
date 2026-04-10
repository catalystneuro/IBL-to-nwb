"""Plot trial-aligned lick counts.

This script creates a visualization showing licks aligned to feedback time,
with separate averages for correct and incorrect trials and a raster plot below.

Usage:
    uv run python plot_trial_aligned_licks.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pynapple as nap
from _common import create_argument_parser, save_figure
from pynwb import read_nwb


def plot_trial_aligned_licks(nwbfile) -> plt.Figure:
    """Create trial-aligned licks visualization.

    Parameters
    ----------
    nwbfile : NWBFile
        The NWB file object (processed).

    Returns
    -------
    plt.Figure
        The matplotlib figure.
    """
    # Get trials dataframe for metadata
    trials_df = nwbfile.trials.to_dataframe()

    # Masks for correct/incorrect
    correct_mask = trials_df["is_mouse_rewarded"].values

    # Get lick timestamps from processing module
    lick_events = nwbfile.processing["lick_times"]["EventsLickTimes"]
    lick_times = nap.Ts(t=lick_events.timestamps[:])

    # Create Ts objects for feedback times
    feedback_times = nap.Ts(t=trials_df["feedback_time"].values)
    correct_feedback_times = nap.Ts(t=trials_df.loc[correct_mask, "feedback_time"].values)
    incorrect_feedback_times = nap.Ts(t=trials_df.loc[~correct_mask, "feedback_time"].values)

    minmax = (-0.5, 1.0)
    bin_size = 0.02  # 20ms bins for counting

    # Use compute_perievent to align lick timestamps around feedback
    perievent_licks = nap.compute_perievent(lick_times, feedback_times, minmax=minmax)

    # For the average trace, we need to count licks in bins
    perievent_correct_licks = nap.compute_perievent(lick_times, correct_feedback_times, minmax=minmax)
    perievent_incorrect_licks = nap.compute_perievent(lick_times, incorrect_feedback_times, minmax=minmax)

    # Count licks in bins for average traces
    correct_counts = perievent_correct_licks.count(bin_size)
    incorrect_counts = perievent_incorrect_licks.count(bin_size)

    # Mean across trials (columns are trials in the TsGroup)
    correct_mean = np.nanmean(correct_counts.values, axis=1)
    correct_sem = np.nanstd(correct_counts.values, axis=1) / np.sqrt(correct_counts.shape[1])
    incorrect_mean = np.nanmean(incorrect_counts.values, axis=1)
    incorrect_sem = np.nanstd(incorrect_counts.values, axis=1) / np.sqrt(incorrect_counts.shape[1])

    time_counts = correct_counts.t

    # Sort trials by outcome
    sorted_trial_indices = np.argsort(correct_mask)

    # Create figure
    fig, axes = plt.subplots(2, 1, figsize=(4, 8), gridspec_kw={"height_ratios": [1, 3]}, sharex=True)

    ax_avg = axes[0]
    ax_avg.plot(time_counts, correct_mean, color="blue", linewidth=1.5, label="Correct")
    ax_avg.fill_between(time_counts, correct_mean - correct_sem, correct_mean + correct_sem, color="blue", alpha=0.3)
    ax_avg.plot(time_counts, incorrect_mean, color="red", linewidth=1.5, label="Incorrect")
    ax_avg.fill_between(
        time_counts, incorrect_mean - incorrect_sem, incorrect_mean + incorrect_sem, color="red", alpha=0.3
    )
    ax_avg.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax_avg.set_ylabel("Licks (count)")
    ax_avg.set_title("Licks", fontsize=12, fontweight="bold", loc="center")
    ax_avg.legend(loc="upper left", fontsize=8, framealpha=0.9)

    # Raster plot - plot individual lick events
    ax_raster = axes[1]

    # Plot licks as scatter points for each trial
    n_trials = len(trials_df)
    n_incorrect = (~correct_mask).sum()
    n_correct = correct_mask.sum()

    # Get lick times for each trial and plot as raster
    for i, sorted_index in enumerate(sorted_trial_indices):
        if sorted_index in perievent_licks.keys():
            trial_licks = perievent_licks[sorted_index]
            if len(trial_licks) > 0:
                ax_raster.scatter(
                    trial_licks.t, np.full(len(trial_licks), i), c="black", s=1, marker="|", linewidths=0.5
                )

    # Side color bar
    bar_width = 0.05
    ax_bar = ax_raster.inset_axes([1.02, 0, bar_width, 1])
    ax_bar.axhspan(0, n_incorrect / n_trials, color="red", alpha=0.8)
    ax_bar.axhspan(n_incorrect / n_trials, 1, color="blue", alpha=0.8)
    ax_bar.set_xlim(0, 1)
    ax_bar.set_ylim(0, 1)
    ax_bar.axis("off")
    ax_bar.text(
        1.5,
        (n_incorrect / n_trials) / 2,
        "incorrect",
        rotation=90,
        va="center",
        ha="left",
        fontsize=9,
        color="red",
        fontweight="bold",
    )
    ax_bar.text(
        1.5,
        n_incorrect / n_trials + (n_correct / n_trials) / 2,
        "correct",
        rotation=90,
        va="center",
        ha="left",
        fontsize=9,
        color="blue",
        fontweight="bold",
    )

    ax_raster.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax_raster.set_ylabel("Sorted Trial Number")
    ax_raster.set_xlabel("T from Feedback (s)")
    ax_raster.set_xlim(minmax[0], minmax[1])
    ax_raster.set_ylim(0, n_trials)

    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot trial-aligned lick counts",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating trial-aligned licks plot...")
    fig = plot_trial_aligned_licks(nwbfile)

    output_path = save_figure(fig, "plot_trial_aligned_licks")
    print(f"Figure saved to: {output_path}")

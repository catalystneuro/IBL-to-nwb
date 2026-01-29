"""Plot trial-aligned left paw speed.

This script creates a visualization showing left paw speed aligned to stimulus onset,
with separate averages for correct and incorrect trials and a raster plot below.

Usage:
    uv run python plot_trial_aligned_paw_speed.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pynapple as nap

from pynwb import read_nwb

from _common import create_argument_parser, save_figure


def plot_trial_aligned_paw_speed(nwbfile) -> plt.Figure:
    """Create trial-aligned paw speed visualization.

    Parameters
    ----------
    nwbfile : NWBFile
        The NWB file object (processed).

    Returns
    -------
    plt.Figure
        The matplotlib figure.
    """
    # Load with pynapple from memory
    data = nap.NWBFile(nwbfile)

    # Get trials dataframe for metadata
    trials_df = nwbfile.trials.to_dataframe()

    # Masks for correct/incorrect
    correct_mask = trials_df["is_mouse_rewarded"].values

    # Get left paw position and compute speed using pynapple's derivative
    left_paw = data["LeftCamera/PoseEstimationSeriesLeftPaw"]
    velocity = left_paw.derivative()
    speed_values = np.sqrt(velocity.values[:, 0] ** 2 + velocity.values[:, 1] ** 2)
    speed = nap.Tsd(t=velocity.t, d=speed_values)

    # Create Ts objects for stimulus onset times
    stim_times = nap.Ts(t=trials_df["gabor_stimulus_onset_time"].values)
    correct_stim_times = nap.Ts(t=trials_df.loc[correct_mask, "gabor_stimulus_onset_time"].values)
    incorrect_stim_times = nap.Ts(t=trials_df.loc[~correct_mask, "gabor_stimulus_onset_time"].values)

    # Use pynapple's compute_perievent_continuous to align speed around stimulus onset
    minmax = (-0.5, 1.0)

    perievent_all = nap.compute_perievent_continuous(speed, stim_times, minmax=minmax)
    perievent_correct = nap.compute_perievent_continuous(speed, correct_stim_times, minmax=minmax)
    perievent_incorrect = nap.compute_perievent_continuous(speed, incorrect_stim_times, minmax=minmax)

    # Compute mean and SEM
    correct_mean = np.nanmean(perievent_correct.values, axis=1)
    correct_sem = np.nanstd(perievent_correct.values, axis=1) / np.sqrt(
        np.sum(~np.isnan(perievent_correct.values), axis=1)
    )
    incorrect_mean = np.nanmean(perievent_incorrect.values, axis=1)
    incorrect_sem = np.nanstd(perievent_incorrect.values, axis=1) / np.sqrt(
        np.sum(~np.isnan(perievent_incorrect.values), axis=1)
    )

    time = perievent_correct.t

    # Sort trials by outcome for raster
    sorted_indices = np.argsort(correct_mask)
    perievent_sorted = perievent_all.values[:, sorted_indices]

    # Create figure
    fig, axes = plt.subplots(2, 1, figsize=(4, 8), gridspec_kw={"height_ratios": [1, 3]}, sharex=True)

    ax_avg = axes[0]
    ax_avg.plot(time, correct_mean, color="blue", linewidth=1.5, label="Correct")
    ax_avg.fill_between(time, correct_mean - correct_sem, correct_mean + correct_sem, color="blue", alpha=0.3)
    ax_avg.plot(time, incorrect_mean, color="red", linewidth=1.5, label="Incorrect")
    ax_avg.fill_between(time, incorrect_mean - incorrect_sem, incorrect_mean + incorrect_sem, color="red", alpha=0.3)
    ax_avg.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax_avg.set_ylabel("Speed (px/s)")
    ax_avg.set_title("Left paw speed", fontsize=12, fontweight="bold", loc="center")
    ax_avg.legend(loc="upper left", fontsize=8, framealpha=0.9)

    ax_raster = axes[1]
    n_trials = perievent_sorted.shape[1]
    n_incorrect = (~correct_mask).sum()
    n_correct = correct_mask.sum()

    im = ax_raster.imshow(
        perievent_sorted.T,
        aspect="auto",
        cmap="gray_r",
        extent=[time[0], time[-1], 0, n_trials],
        vmin=0,
        vmax=np.nanpercentile(perievent_sorted, 95),
        origin="lower",
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
        1.5, (n_incorrect / n_trials) / 2, "incorrect", rotation=90, va="center", ha="left", fontsize=9, color="red", fontweight="bold"
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
    ax_raster.set_xlabel("T from Stim On (s)")

    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot trial-aligned left paw speed",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating trial-aligned paw speed plot...")
    fig = plot_trial_aligned_paw_speed(nwbfile)

    output_path = save_figure(fig, "plot_trial_aligned_paw_speed")
    print(f"Figure saved to: {output_path}")


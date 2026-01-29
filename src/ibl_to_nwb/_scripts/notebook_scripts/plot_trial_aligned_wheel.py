"""Plot trial-aligned wheel velocity.

This script creates a visualization showing wheel velocity aligned to first movement onset,
sorted by choice (left/right) with a raster plot below.

Usage:
    uv run python plot_trial_aligned_wheel.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pynapple as nap

from pynwb import read_nwb

from _common import create_argument_parser, save_figure


def plot_trial_aligned_wheel(nwbfile) -> plt.Figure:
    """Create trial-aligned wheel velocity visualization.

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

    # Masks for left/right choices
    left_choice_mask = trials_df["mouse_wheel_choice"].values == "left"
    right_choice_mask = trials_df["mouse_wheel_choice"].values == "right"

    # Get wheel velocity (in rad/s)
    wheel_velocity = data["WheelVelocitySmoothed"]

    # Create Ts objects for first movement times, separated by choice
    movement_times = nap.Ts(t=trials_df["wheel_movement_onset_time"].values)
    left_movement_times = nap.Ts(t=trials_df.loc[left_choice_mask, "wheel_movement_onset_time"].values)
    right_movement_times = nap.Ts(t=trials_df.loc[right_choice_mask, "wheel_movement_onset_time"].values)

    minmax = (-0.5, 1.0)

    perievent_all = nap.compute_perievent_continuous(wheel_velocity, movement_times, minmax=minmax)
    perievent_left = nap.compute_perievent_continuous(wheel_velocity, left_movement_times, minmax=minmax)
    perievent_right = nap.compute_perievent_continuous(wheel_velocity, right_movement_times, minmax=minmax)

    # Compute mean and SEM
    left_mean = np.nanmean(perievent_left.values, axis=1)
    left_sem = np.nanstd(perievent_left.values, axis=1) / np.sqrt(np.sum(~np.isnan(perievent_left.values), axis=1))
    right_mean = np.nanmean(perievent_right.values, axis=1)
    right_sem = np.nanstd(perievent_right.values, axis=1) / np.sqrt(np.sum(~np.isnan(perievent_right.values), axis=1))

    time = perievent_left.t

    # Sort trials by choice for raster (left first, then right)
    sorted_indices = np.argsort(right_choice_mask)  # False (left) first, then True (right)

    # Handle case where perievent_all has no data
    if perievent_all.values.size == 0:
        print("Warning: No perievent data available for wheel velocity")
        # Create empty raster data
        perievent_sorted = np.full((len(time), len(trials_df)), np.nan)
    else:
        perievent_sorted = perievent_all.values[:, sorted_indices]

    # Create figure
    fig, axes = plt.subplots(2, 1, figsize=(4, 8), gridspec_kw={"height_ratios": [1, 3]}, sharex=True)

    ax_avg = axes[0]
    ax_avg.plot(time, left_mean, color="green", linewidth=1.5, label="Left")
    ax_avg.fill_between(time, left_mean - left_sem, left_mean + left_sem, color="green", alpha=0.3)
    ax_avg.plot(time, right_mean, color="olive", linewidth=1.5, label="Right")
    ax_avg.fill_between(time, right_mean - right_sem, right_mean + right_sem, color="olive", alpha=0.3)
    ax_avg.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax_avg.axhline(0, color="gray", linestyle="-", linewidth=0.5)
    ax_avg.set_ylabel("Velocity (rad/s)")
    ax_avg.set_title("Wheel velocity", fontsize=12, fontweight="bold", loc="center")
    ax_avg.legend(loc="upper left", fontsize=8, framealpha=0.9)

    ax_raster = axes[1]
    n_trials = perievent_sorted.shape[1]
    n_left = left_choice_mask.sum()
    n_right = right_choice_mask.sum()

    im = ax_raster.imshow(
        perievent_sorted.T,
        aspect="auto",
        cmap="gray_r",
        extent=[time[0], time[-1], 0, n_trials],
        vmin=np.nanpercentile(perievent_sorted, 5),
        vmax=np.nanpercentile(perievent_sorted, 95),
        origin="lower",
    )

    # Side color bar for left/right choice
    bar_width = 0.05
    ax_bar = ax_raster.inset_axes([1.02, 0, bar_width, 1])
    ax_bar.axhspan(0, n_left / n_trials, color="green", alpha=0.8)
    ax_bar.axhspan(n_left / n_trials, 1, color="olive", alpha=0.8)
    ax_bar.set_xlim(0, 1)
    ax_bar.set_ylim(0, 1)
    ax_bar.axis("off")
    ax_bar.text(
        1.5, (n_left / n_trials) / 2, "left", rotation=90, va="center", ha="left", fontsize=9, color="green", fontweight="bold"
    )
    ax_bar.text(
        1.5,
        n_left / n_trials + (n_right / n_trials) / 2,
        "right",
        rotation=90,
        va="center",
        ha="left",
        fontsize=9,
        color="olive",
        fontweight="bold",
    )

    ax_raster.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax_raster.set_ylabel("Sorted Trial Number")
    ax_raster.set_xlabel("T from First Move (s)")

    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot trial-aligned wheel velocity",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating trial-aligned wheel velocity plot...")
    fig = plot_trial_aligned_wheel(nwbfile)

    output_path = save_figure(fig, "plot_trial_aligned_wheel")
    print(f"Figure saved to: {output_path}")


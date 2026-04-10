"""Plot psychometric curves.

This script creates psychometric curves showing P(choose right) vs contrast
for each block type (p_left = 0.2, 0.5, 0.8).

Usage:
    uv run python plot_psychometric_curves.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import psychofit as psy
from _common import create_argument_parser, save_figure
from pynwb import read_nwb


def plot_psychometric_curves(nwbfile) -> plt.Figure:
    """Create psychometric curves visualization.

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

    # Compute signed contrast
    contrast = trials_df["gabor_stimulus_contrast"].values
    side = trials_df["gabor_stimulus_side"].values
    signed_contrast = np.where(side == "left", contrast, -contrast)

    trials_df["signed_contrast"] = signed_contrast
    trials_df["chose_right"] = (trials_df["mouse_wheel_choice"] == "right").astype(int)

    # Define block types and colors
    blocks = {
        0.5: {"color": "black", "label": "p_left=0.5"},
        0.2: {"color": "tab:red", "label": "p_left=0.2"},
        0.8: {"color": "tab:blue", "label": "p_left=0.8"},
    }

    # Fit and collect data for each block
    x_fit = np.linspace(-100, 100, 200)
    block_results = {}

    for p_left, style in blocks.items():
        block_trials = trials_df[trials_df["probability_left"] == p_left]

        if len(block_trials) == 0:
            print(f"No trials for p_left={p_left}")
            continue

        # Aggregate by contrast
        grouped = (
            block_trials.groupby("signed_contrast")
            .agg(
                n_total=("chose_right", "count"),
                p_right=("chose_right", "mean"),
            )
            .reset_index()
        )

        # Fit psychometric curve
        data = np.vstack([grouped["signed_contrast"].values, grouped["n_total"].values, grouped["p_right"].values])

        pars, _ = psy.mle_fit_psycho(
            data,
            P_model="erf_psycho_2gammas",
            parstart=np.array([0.0, 40.0, 0.1, 0.1]),
            parmin=np.array([-50.0, 10.0, 0.0, 0.0]),
            parmax=np.array([50.0, 50.0, 0.2, 0.2]),
            nfits=10,
        )

        y_fit = psy.erf_psycho_2gammas(pars, x_fit)

        block_results[p_left] = {
            "grouped": grouped,
            "pars": pars,
            "y_fit": y_fit,
            "n_trials": len(block_trials),
        }

    # Plot psychometric curves for all blocks
    fig, ax = plt.subplots(figsize=(8, 6))

    for p_left, style in blocks.items():
        if p_left not in block_results:
            continue

        result = block_results[p_left]
        grouped = result["grouped"]
        color = style["color"]
        label = style["label"]

        # Fitted curve
        ax.plot(x_fit, result["y_fit"], color=color, linewidth=2, label=f"{label} fit")

        # Data points
        ax.scatter(
            grouped["signed_contrast"],
            grouped["p_right"],
            color=color,
            s=50,
            alpha=0.8,
            label=f"{label} data",
        )

    # Formatting
    ax.set_xlabel("Contrasts")
    ax.set_ylabel("Probability choosing right")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper left", fontsize=9)

    ax.set_title(f"Psychometric Curves\nSession: {nwbfile.session_id}", fontsize=12, fontweight="bold")

    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot psychometric curves",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating psychometric curves plot...")
    fig = plot_psychometric_curves(nwbfile)

    output_path = save_figure(fig, "plot_psychometric_curves")
    print(f"Figure saved to: {output_path}")

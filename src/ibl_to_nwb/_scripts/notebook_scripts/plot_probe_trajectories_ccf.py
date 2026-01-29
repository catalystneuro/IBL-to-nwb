"""Plot probe trajectories in CCFv3 space.

This script creates a visualization showing probe electrode positions
overlaid on Allen CCF reference atlas slices (coronal, sagittal, horizontal).

Usage:
    uv run python plot_probe_trajectories_ccf.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from brainglobe_atlasapi import BrainGlobeAtlas

from pynwb import read_nwb

from _common import create_argument_parser, save_figure


def plot_probe_trajectories_ccf(nwbfile) -> plt.Figure:
    """Create probe trajectory visualization in CCFv3 space.

    Parameters
    ----------
    nwbfile : NWBFile
        The NWB file object (raw or processed).

    Returns
    -------
    plt.Figure
        The matplotlib figure.
    """
    localization = nwbfile.lab_meta_data["localization"]
    anatomical_tables = localization.anatomical_coordinates_tables
    ccf_table_df = anatomical_tables["ElectrodesCCFv3"].to_dataframe()

    probe_names = sorted(ccf_table_df["probe_name"].unique())
    n_probes = len(probe_names)

    probe_colors = ["red", "blue", "green", "orange", "purple"][:n_probes]

    atlas = BrainGlobeAtlas("allen_mouse_25um")

    probe_data = {}

    for probe_name in probe_names:
        probe_table = ccf_table_df[ccf_table_df["probe_name"] == probe_name].copy()
        bg_x = probe_table["x"].values
        bg_y = probe_table["y"].values
        bg_z = probe_table["z"].values

        coronal_position = int(np.mean(bg_x))
        sagittal_position = int(np.mean(bg_z))
        horizontal_position = int(np.mean(bg_y))

        coronal_index = int(coronal_position / atlas.resolution[0])
        sagittal_index = int(sagittal_position / atlas.resolution[2])
        horizontal_index = int(horizontal_position / atlas.resolution[1])

        probe_data[probe_name] = {
            "x_px": bg_x / atlas.resolution[0],
            "y_px": bg_y / atlas.resolution[1],
            "z_px": bg_z / atlas.resolution[2],
            "coronal_position": coronal_position,
            "sagittal_position": sagittal_position,
            "horizontal_position": horizontal_position,
            "coronal_index": coronal_index,
            "sagittal_index": sagittal_index,
            "horizontal_index": horizontal_index,
        }

    fig, axes = plt.subplots(n_probes, 3, figsize=(20, 7 * n_probes))

    if n_probes == 1:
        axes = axes.reshape(1, -1)

    for row, probe_name in enumerate(probe_names):
        data = probe_data[probe_name]
        color = probe_colors[row]

        reference_coronal = atlas.reference[data["coronal_index"], :, :]
        reference_sagittal = atlas.reference[:, :, data["sagittal_index"]]
        reference_horizontal = atlas.reference[:, data["horizontal_index"], :]

        ax = axes[row, 0]
        ax.imshow(reference_coronal, cmap="gray", aspect="equal")
        ax.scatter(data["z_px"], data["y_px"], c=color, s=10, alpha=0.8)
        ax.set_xlabel("Left - Right (pixels)")
        ax.set_ylabel("Dorsal - Ventral (pixels)")
        ax.set_title(f"{probe_name} - Coronal (AP = {data['coronal_position']} um)")

        ax = axes[row, 1]
        ax.imshow(reference_sagittal.T, cmap="gray", aspect="equal")
        ax.scatter(data["x_px"], data["y_px"], c=color, s=10, alpha=0.8)
        ax.set_xlabel("Anterior - Posterior (pixels)")
        ax.set_ylabel("Dorsal - Ventral (pixels)")
        ax.set_title(f"{probe_name} - Sagittal (ML = {data['sagittal_position']} um)")

        ax = axes[row, 2]
        ax.imshow(reference_horizontal, cmap="gray", aspect="equal")
        ax.scatter(data["z_px"], data["x_px"], c=color, s=10, alpha=0.8)
        ax.set_xlabel("Left - Right (pixels)")
        ax.set_ylabel("Anterior - Posterior (pixels)")
        ax.set_title(f"{probe_name} - Horizontal (DV = {data['horizontal_position']} um)")

    fig.suptitle(f"Session: {nwbfile.session_id} - Probe Trajectories (Reference)", fontsize=14, fontweight="bold")
    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot probe trajectories in CCFv3 space",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Loading Allen CCF atlas...")
    print("Generating probe trajectories plot...")
    fig = plot_probe_trajectories_ccf(nwbfile)

    output_path = save_figure(fig, "plot_probe_trajectories_ccf")
    print(f"Figure saved to: {output_path}")


"""Plot probe anatomy with COSMOS regions.

This script creates a visualization showing probe contacts colored by brain region
using the COSMOS parcellation from the IBL anatomical localization data.

Usage:
    uv run python plot_probe_anatomy_cosmos.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from _common import create_argument_parser, save_figure
from pynwb import read_nwb

from ibl_to_nwb.utils import COSMOS_FULL_NAMES, get_cosmos_color


def plot_probe_anatomy_cosmos(nwbfile) -> plt.Figure:
    """Create probe anatomy visualization with COSMOS regions.

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
    ibl_bregma_table_df = anatomical_tables["ElectrodesIBLBregma"].to_dataframe()

    probe_names = sorted(ibl_bregma_table_df["probe_name"].unique())
    n_probes = len(probe_names)

    fig, axes = plt.subplots(1, n_probes * 2, figsize=(5 * n_probes, 12), sharey=True)

    if n_probes == 1:
        axes = [axes[0], axes[1]]

    all_unique_regions = []

    for probe_index, probe_name in enumerate(probe_names):
        ax_probe = axes[probe_index * 2]
        ax_regions = axes[probe_index * 2 + 1]

        probe_table = ibl_bregma_table_df[ibl_bregma_table_df["probe_name"] == probe_name].copy()

        probe_table["rel_x"] = [electrode["rel_x"].iloc[0] for electrode in probe_table["localized_entity"]]
        probe_table["rel_y"] = [electrode["rel_y"].iloc[0] for electrode in probe_table["localized_entity"]]

        probe_table = probe_table.sort_values("rel_y").reset_index(drop=True)

        cosmos_values = probe_table["cosmos_location"].values
        rel_x_values = probe_table["rel_x"].values
        rel_y_values = probe_table["rel_y"].values
        colors = [get_cosmos_color(c) for c in cosmos_values]

        for region in cosmos_values:
            if region not in all_unique_regions:
                all_unique_regions.append(region)

        contact_width = 12
        contact_height = 10

        for i in range(len(rel_x_values)):
            rect = plt.Rectangle(
                (rel_x_values[i] - contact_width / 2, rel_y_values[i] - contact_height / 2),
                contact_width,
                contact_height,
                facecolor=colors[i],
                edgecolor="black",
                linewidth=0.3,
            )
            ax_probe.add_patch(rect)

        x_min, x_max = probe_table["rel_x"].min(), probe_table["rel_x"].max()
        y_min, y_max = probe_table["rel_y"].min(), probe_table["rel_y"].max()
        x_margin, y_margin = 50, 100

        ax_probe.set_xlim(x_min - x_margin, x_max + x_margin)
        ax_probe.set_ylim(y_min - y_margin, y_max + y_margin)

        ax_probe.set_xticks([x_max])
        ax_probe.set_xticklabels([f"{x_max:.0f}"])
        ax_probe.set_xlabel("Relative X (um)")

        if probe_index == 0:
            ax_probe.set_ylabel("Distance to Probe Tip (um)")
        ax_probe.set_title(f"{probe_name}")
        ax_probe.set_aspect("equal", adjustable="box")

        blocks = []
        current_region = cosmos_values[0]
        block_start = rel_y_values[0]

        for i in range(1, len(cosmos_values)):
            if cosmos_values[i] != current_region:
                block_end = (rel_y_values[i - 1] + rel_y_values[i]) / 2
                blocks.append((current_region, block_start, block_end))
                current_region = cosmos_values[i]
                block_start = block_end

        blocks.append((current_region, block_start, rel_y_values[-1] + contact_height / 2))

        block_width = 1.0
        for region, y_start, y_end in blocks:
            color = get_cosmos_color(region)
            height = y_end - y_start

            rect = plt.Rectangle(
                (0, y_start),
                block_width,
                height,
                facecolor=color,
                edgecolor="black",
                linewidth=0.5,
            )
            ax_regions.add_patch(rect)

            y_center = (y_start + y_end) / 2
            display_name = COSMOS_FULL_NAMES.get(region, region)
            ax_regions.text(
                block_width + 0.1, y_center, display_name, va="center", ha="left", fontsize=9, fontweight="bold"
            )

        ax_regions.set_xlim(-0.2, 2.0)
        ax_regions.set_ylim(y_min - y_margin, y_max + y_margin)
        ax_regions.set_xticks([])
        ax_regions.set_title("Cosmos Regions")
        ax_regions.axis("off")

    plt.suptitle(f"Session: {nwbfile.session_id}", fontsize=14, fontweight="bold")
    plt.tight_layout(rect=[0, 0.08, 1, 0.96])

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot probe anatomy with COSMOS regions",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    print("Generating probe anatomy plot...")
    fig = plot_probe_anatomy_cosmos(nwbfile)

    output_path = save_figure(fig, "plot_probe_anatomy_cosmos")
    print(f"Figure saved to: {output_path}")

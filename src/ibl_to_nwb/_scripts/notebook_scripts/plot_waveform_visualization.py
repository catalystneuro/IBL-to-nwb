"""Plot waveform visualization.

This script creates a combined waveform visualization showing:
- Probe contacts with COSMOS regions
- Wiggle plots for 3 example units
- Max channel waveforms
- Heatmaps

Note: Waveform data is stored in VOLTS in the NWB file (not microvolts).
This is to comply with the NWB schema which has the unit attribute fixed to 'volts'.
For visualization, we convert to microvolts (multiply by 1e6) for better readability.

Usage:
    uv run python plot_waveform_visualization.py [nwbfile_path]
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from _common import create_argument_parser, save_figure
from matplotlib.patches import Patch
from pynwb import read_nwb

from ibl_to_nwb.utils import COSMOS_FULL_NAMES, get_cosmos_color


def get_cosmos_region_data(probe_table):
    """Extract COSMOS region blocks from probe table for visualization."""
    probe_table = probe_table.sort_values("rel_y").reset_index(drop=True)
    cosmos_values = probe_table["cosmos_location"].values
    rel_y_values = probe_table["rel_y"].values

    blocks = []
    current_region = cosmos_values[0]
    block_start = rel_y_values[0]

    for i in range(1, len(cosmos_values)):
        if cosmos_values[i] != current_region:
            block_end = (rel_y_values[i - 1] + rel_y_values[i]) / 2
            blocks.append((current_region, block_start, block_end))
            current_region = cosmos_values[i]
            block_start = block_end

    blocks.append((current_region, block_start, rel_y_values[-1] + 5))

    unique_regions = []
    for region, _, _ in blocks:
        if region not in unique_regions:
            unique_regions.append(region)

    return blocks, unique_regions


def plot_probe_regions(probe_table, ax, unit_depths=None, unit_ids=None):
    """Plot probe with COSMOS region strip and electrode contacts."""
    probe_table = probe_table.sort_values("rel_y").reset_index(drop=True)
    rel_x_values = probe_table["rel_x"].values
    rel_y_values = probe_table["rel_y"].values

    x_min, x_max = rel_x_values.min(), rel_x_values.max()
    y_min, y_max = rel_y_values.min(), rel_y_values.max()

    blocks, unique_regions = get_cosmos_region_data(probe_table)
    strip_width = x_max - x_min + 30
    strip_x = x_min - 15

    for region, y_start, y_end in blocks:
        color = get_cosmos_color(region)
        rect = plt.Rectangle(
            (strip_x, y_start), strip_width, y_end - y_start, facecolor=color, edgecolor="none", alpha=0.5
        )
        ax.add_patch(rect)

    for i in range(len(rel_x_values)):
        rect = plt.Rectangle(
            (rel_x_values[i] - 6, rel_y_values[i] - 5), 12, 10, facecolor="white", edgecolor="black", linewidth=0.3
        )
        ax.add_patch(rect)

    if unit_depths is not None and unit_ids is not None:
        for i, depth in enumerate(unit_depths):
            if i < len(unit_ids):
                ax.text(
                    x_max + 25,
                    depth,
                    str(unit_ids[i]),
                    va="center",
                    ha="left",
                    fontsize=7,
                    color="black",
                    fontweight="bold",
                )

    ax.set_xlim(x_min - 50, x_max + 50)
    ax.set_ylim(y_min - 100, y_max + 100)
    ax.set_xticks([])
    ax.set_ylabel("Depth (um)")
    ax.set_aspect("equal", adjustable="box")
    for spine in ax.spines.values():
        spine.set_visible(False)

    legend_handles = [
        Patch(
            facecolor=get_cosmos_color(r),
            edgecolor="black",
            linewidth=0.5,
            label=COSMOS_FULL_NAMES.get(r, r),
            alpha=0.5,
        )
        for r in unique_regions
    ]
    return ax, legend_handles


def plot_waveform_wiggle(waveform_uV, electrode_depths, ax, fs=30000.0, gain=0.4, channel_spacing=0.8):
    """Plot waveform as IBL-style double wiggle plot.

    Parameters
    ----------
    waveform_uV : array
        Waveform data in microvolts (num_samples, num_channels).
    electrode_depths : array
        Depth of each electrode channel.
    ax : matplotlib axis
    fs : float
        Sampling rate in Hz.
    gain : float
        Scaling factor for waveform amplitude.
    channel_spacing : float
        Vertical spacing between channels.
    """
    num_samples, num_channels = waveform_uV.shape

    # Handle mismatch between waveform channels and electrode depths
    n_electrodes = len(electrode_depths)
    if num_channels != n_electrodes:
        # Use only channels that have electrode depths
        num_channels = min(num_channels, n_electrodes)
        waveform_uV = waveform_uV[:, :num_channels]
        electrode_depths = electrode_depths[:num_channels]

    center_sample = num_samples // 2
    time_ms = (np.arange(num_samples) - center_sample) / fs * 1000

    sort_order = np.argsort(electrode_depths)
    wf_sorted = waveform_uV[:, sort_order]
    depths_sorted = electrode_depths[sort_order]

    wf_max = np.abs(wf_sorted).max()
    wf_norm = wf_sorted / wf_max * gain if wf_max > 0 else wf_sorted

    for ch in range(num_channels):
        offset = ch * channel_spacing
        trace = wf_norm[:, ch]
        ax.plot(time_ms, trace + offset, color="black", linewidth=0.5)
        ax.fill_between(time_ms, offset, trace + offset, where=(trace > 0), color="orange", alpha=0.8, linewidth=0)
        ax.fill_between(time_ms, offset, trace + offset, where=(trace < 0), color="slateblue", alpha=0.8, linewidth=0)

    ax.set_xlabel("Time (ms)")
    depth_ticks = np.linspace(depths_sorted.min(), depths_sorted.max(), 5)
    channel_positions = np.linspace(0, (num_channels - 1) * channel_spacing, 5)
    ax.set_yticks(channel_positions)
    ax.set_yticklabels([f"{d:.0f}" for d in depth_ticks])
    ax.set_ylabel("Distance from tip (um)")


def get_max_channel_index(unit):
    """Get the index (0-31) of the max electrode within the unit's electrodes list."""
    max_electrode_idx = unit["max_electrode"].index[0]
    electrodes_indices = unit["electrodes"].index.tolist()
    if max_electrode_idx in electrodes_indices:
        return electrodes_indices.index(max_electrode_idx)
    waveform = unit["waveform_mean"]
    peak_to_peak = waveform.max(axis=0) - waveform.min(axis=0)
    return np.argmax(peak_to_peak)


def plot_max_channel_waveform(waveform_uV, ax, max_ch_idx=None, fs=30000.0):
    """Plot waveform on the max amplitude channel.

    Parameters
    ----------
    waveform_uV : array
        Waveform data in microvolts (num_samples, num_channels).
    ax : matplotlib axis
    max_ch_idx : int, optional
        Index of max channel in the waveform array. If None, computed from waveform.
    fs : float
        Sampling rate in Hz.
    """
    num_samples = waveform_uV.shape[0]
    center_sample = num_samples // 2
    time_ms = (np.arange(num_samples) - center_sample) / fs * 1000

    if max_ch_idx is None:
        peak_to_peak = waveform_uV.max(axis=0) - waveform_uV.min(axis=0)
        max_ch_idx = np.argmax(peak_to_peak)

    trace = waveform_uV[:, max_ch_idx]

    ax.plot(time_ms, trace, color="black", linewidth=1.0)
    ax.fill_between(time_ms, 0, trace, where=(trace > 0), color="orange", alpha=0.8, linewidth=0)
    ax.fill_between(time_ms, 0, trace, where=(trace < 0), color="slateblue", alpha=0.8, linewidth=0)
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Amplitude (uV)")


def plot_waveform_heatmap(waveform_uV, electrode_depths, ax, fs=30000.0, vmax=None, add_colorbar=False):
    """Plot waveform as a heatmap (time x channel).

    Parameters
    ----------
    waveform_uV : array
        Waveform data in microvolts (num_samples, num_channels).
    electrode_depths : array
        Depth of each electrode channel.
    ax : matplotlib axis
    fs : float
        Sampling rate in Hz.
    vmax : float, optional
        Max value for colormap.
    add_colorbar : bool
        Whether to add a colorbar.
    """
    num_samples, num_channels = waveform_uV.shape

    # Handle mismatch between waveform channels and electrode depths
    n_electrodes = len(electrode_depths)
    if num_channels != n_electrodes:
        num_channels = min(num_channels, n_electrodes)
        waveform_uV = waveform_uV[:, :num_channels]
        electrode_depths = electrode_depths[:num_channels]

    center_sample = num_samples // 2
    time_ms = (np.arange(num_samples) - center_sample) / fs * 1000

    sort_order = np.argsort(electrode_depths)
    wf_sorted = waveform_uV[:, sort_order]
    depths_sorted = electrode_depths[sort_order]

    if vmax is None:
        vmax = np.abs(wf_sorted).max()

    im = ax.imshow(
        wf_sorted.T,
        aspect="auto",
        origin="lower",
        extent=[time_ms[0], time_ms[-1], 0, num_channels],
        cmap="RdBu_r",
        vmin=-vmax,
        vmax=vmax,
    )
    ax.set_xlabel("Time (ms)")

    depth_ticks = np.linspace(depths_sorted.min(), depths_sorted.max(), 5)
    channel_positions = np.linspace(0, num_channels, 5)
    ax.set_yticks(channel_positions)
    ax.set_yticklabels([f"{d:.0f}" for d in depth_ticks])
    ax.set_ylabel("Distance from tip (um)")

    if add_colorbar:
        plt.colorbar(im, ax=ax, label="Amplitude (uV)")
    return im


def plot_waveform_visualization(nwbfile, probe_name: str | None = None) -> plt.Figure:
    """Create combined waveform visualization.

    Parameters
    ----------
    nwbfile : NWBFile
        The NWB file object (processed).
    probe_name : str, optional
        Name of the probe to plot. If None, uses the first probe with good units.

    Returns
    -------
    plt.Figure
        The matplotlib figure.
    """
    units_df = nwbfile.units.to_dataframe()

    # Get localization data for probe visualization
    localization = nwbfile.lab_meta_data.get("localization")
    anatomical_tables = localization.anatomical_coordinates_tables
    ibl_bregma_table_df = anatomical_tables["ElectrodesIBLBregma"].to_dataframe()

    # Extract electrode positions from localized_entity
    ibl_bregma_table_df["rel_x"] = [electrode["rel_x"].iloc[0] for electrode in ibl_bregma_table_df["localized_entity"]]
    ibl_bregma_table_df["rel_y"] = [electrode["rel_y"].iloc[0] for electrode in ibl_bregma_table_df["localized_entity"]]

    # Select good units from first probe
    if probe_name is None:
        for pname in sorted(units_df["probe_name"].unique()):
            good_units = units_df[(units_df["probe_name"] == pname) & (units_df["ibl_quality_score"] == 1.0)]
            if len(good_units) > 0:
                probe_name = pname
                break

    good_units = units_df[(units_df["probe_name"] == probe_name) & (units_df["ibl_quality_score"] == 1.0)].copy()
    good_units = good_units.sort_values("distance_from_probe_tip_um")
    probe_table = ibl_bregma_table_df[ibl_bregma_table_df["probe_name"] == probe_name].copy()

    # Filter out units with any NaN waveforms (some units have partial NaN data)
    valid_waveform_mask = [not np.isnan(unit["waveform_mean"]).any() for _, unit in good_units.iterrows()]
    good_units = good_units[valid_waveform_mask]

    print(f"Selected {len(good_units)} good units with valid waveforms from {probe_name}")

    # Select up to 3 units evenly spaced across depth
    depths = good_units["distance_from_probe_tip_um"].values
    n_units_to_select = min(3, len(good_units))

    if n_units_to_select == 0:
        raise ValueError(f"No good units found for {probe_name}")

    if n_units_to_select == 1:
        selected_indices = [0]
    else:
        target_depths = np.linspace(depths.min(), depths.max(), n_units_to_select)
        selected_indices = []
        available_mask = np.ones(len(good_units), dtype=bool)

        for target in target_depths:
            available_depths = depths.copy()
            available_depths[~available_mask] = np.inf
            closest_idx = np.argmin(np.abs(available_depths - target))
            selected_indices.append(closest_idx)
            available_mask[closest_idx] = False

        selected_indices = sorted(selected_indices, key=lambda i: depths[i])

    example_units = good_units.iloc[selected_indices]
    example_depths = example_units["distance_from_probe_tip_um"].values.tolist()
    example_unit_ids = example_units.index.tolist()

    # Convert waveforms from volts to microvolts for visualization
    # NWB schema has waveform_mean unit fixed to 'volts', so we always convert to uV for display
    # Note: The pynwb attribute may not be accessible, but the HDF5 attribute is always 'volts'
    conversion_factor = 1e6
    print("Converting waveforms from volts to microvolts for display (factor: 1e6)")

    # Compute shared vmax for heatmaps (in microvolts)
    shared_vmax = max(np.abs(unit["waveform_mean"] * conversion_factor).max() for _, unit in example_units.iterrows())
    if np.isnan(shared_vmax) or shared_vmax == 0:
        shared_vmax = 1.0  # Default if all values are NaN

    # Create combined figure: Probe | n waveforms | colorbar
    n_units = len(example_units)
    width_ratios = [1.0] + [1.2] * n_units + [0.08]
    fig = plt.figure(figsize=(4 + 4 * n_units, 12))
    gs = fig.add_gridspec(3, n_units + 2, width_ratios=width_ratios, wspace=0.35, hspace=0.4)

    # Probe visualization (spans all 3 rows)
    ax_probe = fig.add_subplot(gs[:, 0])
    _, legend_handles = plot_probe_regions(probe_table, ax_probe, unit_depths=example_depths, unit_ids=example_unit_ids)
    ax_probe.set_title(f"{probe_name}\nElectrode Contacts", fontsize=10)

    if legend_handles:
        ax_probe.legend(
            handles=legend_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.02),
            ncol=2,
            fontsize=9,
            frameon=False,
            title="COSMOS Regions",
            title_fontsize=10,
            handlelength=1.5,
            handleheight=1.5,
        )

    # Store last heatmap image for shared colorbar
    last_heatmap_im = None
    max_channel_axes = []

    # Compute shared y-limits for max channel waveforms
    all_max_channel_waveforms = []
    for _, unit in example_units.iterrows():
        waveform_uV = unit["waveform_mean"] * conversion_factor
        max_ch_idx = get_max_channel_index(unit)
        all_max_channel_waveforms.append(waveform_uV[:, max_ch_idx])
    shared_ymin = min(wf.min() for wf in all_max_channel_waveforms)
    shared_ymax = max(wf.max() for wf in all_max_channel_waveforms)
    # Add some padding
    y_padding = (shared_ymax - shared_ymin) * 0.1
    shared_ymin -= y_padding
    shared_ymax += y_padding

    # Plot waveforms for each unit (columns 1-3)
    for col_idx, (unit_id, unit) in enumerate(example_units.iterrows()):
        # Convert waveform to microvolts for visualization
        waveform_uV = unit["waveform_mean"] * conversion_factor
        depth = unit["distance_from_probe_tip_um"]
        region = unit["max_electrode"]["location"].values[0]
        electrode_depths = unit["electrodes"]["rel_y"].values

        # Get max channel index from the unit's electrode mapping
        max_ch_idx = get_max_channel_index(unit)
        max_electrode_depth = unit["max_electrode"]["rel_y"].values[0]

        # Row 0: Wiggle plot
        ax_wiggle = fig.add_subplot(gs[0, col_idx + 1])
        plot_waveform_wiggle(waveform_uV, electrode_depths, ax_wiggle, gain=0.4, channel_spacing=0.8)
        ax_wiggle.set_title(f"Unit {unit_id}\n{region}", fontsize=8)

        # Row 1: Max channel waveform (use max_electrode depth in title)
        ax_max = fig.add_subplot(gs[1, col_idx + 1])
        plot_max_channel_waveform(waveform_uV, ax_max, max_ch_idx=max_ch_idx)
        ax_max.set_title(f"Depth of max electrode: {max_electrode_depth:.0f} um", fontsize=8)
        ax_max.set_ylim(shared_ymin, shared_ymax)
        max_channel_axes.append(ax_max)

        # Row 2: Heatmap
        ax_heatmap = fig.add_subplot(gs[2, col_idx + 1])
        last_heatmap_im = plot_waveform_heatmap(waveform_uV, electrode_depths, ax_heatmap, vmax=shared_vmax)

    # Add shared colorbar for heatmaps
    cbar_ax = fig.add_subplot(gs[2, n_units + 1])
    cbar = fig.colorbar(last_heatmap_im, cax=cbar_ax)
    cbar.set_label("Amplitude (uV)", fontsize=9)

    fig.suptitle(
        f"Waveform Visualization - {probe_name}\nSession: {nwbfile.session_id}",
        fontsize=12,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()

    return fig


if __name__ == "__main__":
    parser = create_argument_parser(
        "Plot waveform visualization",
        file_type="processed",
    )
    args = parser.parse_args()

    print(f"Loading NWB file: {args.nwbfile_path}")
    nwbfile = read_nwb(args.nwbfile_path)

    # Print waveform metadata for verification
    print("\n=== Waveform Metadata ===")
    waveform_mean = nwbfile.units["waveform_mean"]
    print(f"Unit attribute: {waveform_mean.unit if hasattr(waveform_mean, 'unit') else 'not set'}")

    # Check sampling_rate attribute via HDF5
    import h5py

    with h5py.File(args.nwbfile_path, "r") as hf:
        if "units/waveform_mean" in hf:
            attrs = dict(hf["units/waveform_mean"].attrs)
            print(f"HDF5 sampling_rate attr: {attrs.get('sampling_rate', 'NOT SET')}")
            print(f"HDF5 unit attr: {attrs.get('unit', 'NOT SET')}")

    # Check data range
    sample_waveform = nwbfile.units["waveform_mean"][0]
    print(f"Sample waveform range (raw): {sample_waveform.min():.2e} to {sample_waveform.max():.2e}")
    print("(Values ~1e-4 to 1e-5 indicate VOLTS, ~1e1 to 1e2 would indicate microvolts)")
    print("=" * 30 + "\n")

    print("Generating waveform visualization...")
    fig = plot_waveform_visualization(nwbfile)

    output_path = save_figure(fig, "plot_waveform_visualization")
    print(f"Figure saved to: {output_path}")

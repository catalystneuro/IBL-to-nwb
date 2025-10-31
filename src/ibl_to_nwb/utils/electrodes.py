from __future__ import annotations

import warnings
import os
from pathlib import Path
from typing import Iterable, List, Literal, Optional

import numpy as np
from brainbox.io.one import SpikeSortingLoader
from iblatlas.atlas import AllenAtlas
from iblatlas.regions import BrainRegions
from one.api import ONE
from pynwb import NWBFile
from probeinterface import Probe
from probeinterface.neuropixels_tools import read_spikeglx


DEFAULT_FALLBACK_PROBE_MANUFACTURER = "imec"
DEFAULT_FALLBACK_PROBE_MODEL = "PRB_1_4_0480_1"


def _load_fallback_probe(model_name: str = DEFAULT_FALLBACK_PROBE_MODEL) -> Probe:
    """
    Generate the Neuropixels 1.0 probe geometry programmatically to avoid external files.
    """
    if model_name != DEFAULT_FALLBACK_PROBE_MODEL:
        raise ValueError(f"Unsupported fallback probe model: {model_name}")

    probe = Probe(
        ndim=2,
        si_units="um",
        model_name=DEFAULT_FALLBACK_PROBE_MODEL,
        manufacturer=DEFAULT_FALLBACK_PROBE_MANUFACTURER.upper(),
    )

    probe.annotations.update(
        {
            "model_name": DEFAULT_FALLBACK_PROBE_MODEL,
            "manufacturer": DEFAULT_FALLBACK_PROBE_MANUFACTURER,
            "description": "Neuropixels 1.0 probe",
            "shank_tips": [(24.0, -220.0)],
        }
    )

    num_rows = 240
    positions: list[tuple[float, float]] = []
    for row in range(num_rows):
        base_y = float(row * 40)
        positions.extend(
            [
                (16.0, base_y),
                (48.0, base_y),
                (0.0, base_y + 20.0),
                (32.0, base_y + 20.0),
            ]
        )

    contact_positions = np.asarray(positions, dtype=np.float64)
    plane_axes = np.broadcast_to(np.eye(2, dtype=np.float64), (contact_positions.shape[0], 2, 2)).copy()
    contact_ids = [f"e{index}" for index in range(contact_positions.shape[0])]
    shank_ids = ["0"] * contact_positions.shape[0]

    probe.set_contacts(
        positions=contact_positions,
        shapes="square",
        shape_params={"width": 12.0},
        plane_axes=plane_axes,
        contact_ids=contact_ids,
        shank_ids=shank_ids,
    )
    probe.set_device_channel_indices(np.arange(contact_positions.shape[0], dtype=np.int64))
    probe.set_planar_contour([[-11.0, 9989.0], [-11.0, -11.0], [24.0, -220.0], [59.0, -11.0], [59.0, 9989.0]])

    return probe


def _ensure_ibl_coordinates_um(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return IBL coordinates in micrometres along with their metre representation."""
    coords_m = np.column_stack([x, y, z]).astype(np.float64)
    if np.nanmax(np.abs(coords_m)) > 0.1:  # heuristically treat values as micrometres
        coords_m *= 1e-6
    coords_um = coords_m * 1e6
    return coords_um, coords_m


def convert_ibl_to_ccf3_coordinates(
    *,
    atlas: AllenAtlas,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    acronyms: np.ndarray,
    probe_name: str | None = None,
    eid: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert IBL (bregma-centered) coordinates into the Allen CCFv3 frame.

    The spike-sorting loaders often provide histology coordinates in micrometers. This helper
    normalizes inputs to meters when necessary, performs the atlas transformation, and labels
    out-of-volume points as ``"out-of-atlas"`` while returning CCF coordinates in micrometers.

    Parameters
    ----------
    atlas : AllenAtlas
        Atlas instance used for the coordinate transformation.
    x, y, z : np.ndarray
        Coordinates in meters in the IBL frame. If the magnitudes indicate micrometers, the values
        are rescaled automatically.
    acronyms : np.ndarray
        Brain region acronyms associated with each coordinate.
    probe_name : str, optional
        Probe identifier included in warning messages.
    eid : str, optional
        Session identifier included in warning messages.

   -------
    ccf_coords_um : np.ndarray
        Allen CCF coordinates in micrometers (NaN for entries outside the atlas volume).
    ccf_regions : np.ndarray
        Region labels for the CCF coordinates, with ``"out-of-atlas"`` marking out-of-bounds
        points.
    outside_mask : np.ndarray
        Boolean mask indicating which coordinates fell outside the atlas bounds.
    """

    _, coords_m = _ensure_ibl_coordinates_um(x, y, z)
    lims = np.array([np.sort(atlas.bc.lim(axis)) for axis in range(3)], dtype=np.float64)
    outside_mask = (
        (coords_m[:, 0] < lims[0][0]) | (coords_m[:, 0] > lims[0][1])
        | (coords_m[:, 1] < lims[1][0]) | (coords_m[:, 1] > lims[1][1])
        | (coords_m[:, 2] < lims[2][0]) | (coords_m[:, 2] > lims[2][1])
    )

    ccf_coords_um = np.full_like(coords_m, fill_value=np.nan, dtype=np.float64)
    valid_indices = ~outside_mask

    if valid_indices.any():
        try:
            converted = atlas.xyz2ccf(coords_m[valid_indices]).astype(np.float64)
            ccf_coords_um[valid_indices] = converted
        except ValueError as exc:
            warnings.warn(
                (
                    "Unable to convert some IBL coordinates to CCF for probe "
                    f"'{probe_name}' (session {eid}): {exc}. Filling invalid entries with NaN."
                ),
                RuntimeWarning,
                stacklevel=2,
            )

    if outside_mask.any():
        out_indices = np.where(outside_mask)[0].tolist()
        warnings.warn(
            "Probe '%s' (session %s) has %d electrode(s) outside the Allen atlas volume: indices %s."
            % (probe_name, eid, len(out_indices), out_indices),
            RuntimeWarning,
            stacklevel=2,
        )

    ccf_regions = np.array(acronyms, dtype=str)
    ccf_regions[outside_mask] = "out-of-atlas"

    return ccf_coords_um, ccf_regions, outside_mask


def _resolve_meta_path(
    one: ONE,
    eid: str,
    probe_name: str,
    meta_path: Optional[Path],
) -> Optional[Path]:
    """
    Resolve the local path to the SpikeGLX `.meta` file for a given probe.

    Note: Raw ephys data is NOT revision-dependent (raw recordings never change).
    """
    if meta_path is not None:
        return Path(meta_path)

    collection = f"raw_ephys_data/{probe_name}"
    datasets = one.list_datasets(eid=eid, collection=collection)
    meta_datasets = [dataset for dataset in datasets if dataset.endswith(".ap.meta")]
    if not meta_datasets:
        return None

    local_path = one.load_dataset(eid, dataset=meta_datasets[0])
    return Path(local_path)


def add_probe_definition_to_nwbfile(
    probe: Probe,
    nwbfile: NWBFile,
    *,
    group_mode: Literal["by_probe", "by_shank"] = "by_probe",
    metadata: Optional[dict] = None,
    source_description: str,
) -> None:
    """
    Minimal helper to populate the electrodes table using a `probeinterface.Probe` object.
    """
    if group_mode != "by_probe":
        raise ValueError("Only group_mode='by_probe' is supported in this lightweight implementation.")

    contacts = probe.to_numpy(complete=True)
    if contacts.size == 0:
        raise ValueError(f"No contacts found in probe definition: {source_description}")

    # Get contact positions for rel_x, rel_y (probe-relative coordinates)
    contact_positions = probe.contact_positions

    metadata_copy = metadata.copy() if metadata is not None else {}
    ecephys_metadata = metadata_copy.setdefault("Ecephys", {})

    device_entry = ecephys_metadata.setdefault(
        "Device",
        [dict(name="NeuropixelsProbe", description="Neuropixels probe", manufacturer="IMEC")],
    )[0]
    device_name = device_entry["name"]
    if device_name in nwbfile.devices:
        device = nwbfile.devices[device_name]
    else:
        device = nwbfile.create_device(
            name=device_name,
            description=device_entry.get("description", ""),
        )

    group_entry = ecephys_metadata.setdefault(
        "ElectrodeGroup",
        [
            dict(
                name=device_name,
                description="Electrode group for Neuropixels probe",
                location="Unknown",
                device=device_name,
            )
        ],
    )[0]
    group_name = group_entry["name"]
    if group_name in nwbfile.electrode_groups:
        electrode_group = nwbfile.electrode_groups[group_name]
    else:
        electrode_group = nwbfile.create_electrode_group(
            name=group_name,
            description=group_entry.get("description", ""),
            location=group_entry.get("location", "Unknown"),
            device=device,
        )

    default_columns = {"x", "y", "z", "imp", "location", "filtering", "group", "group_name"}
    existing_columns = set(nwbfile.electrodes.colnames) if nwbfile.electrodes is not None else set()

    required_columns = [
        ("electrode_name", "Unique identifier derived from probe contact ids."),
        ("contact_shapes", "Contact shape per electrode as defined by the probe."),
        ("beryl_location", "Brain region in IBL Beryl atlas (coarse grouping)."),
        ("cosmos_location", "Brain region in IBL Cosmos atlas (very coarse grouping)."),
        ("channel_name", "The name of this channel, showing all recording streams for the electrode (e.g., 'AP379,LF379')."),
        ("rel_x", "Relative x coordinate on the probe (µm)."),
        ("rel_y", "Relative y coordinate on the probe (µm)."),
    ]
    # Note: contact_ids and shank_ids are added by NeuroConv's SpikeGLX interface automatically,
    # so we don't add them here to avoid duplication
    required_columns.extend(
        (column["name"], column.get("description", ""))
        for column in ecephys_metadata.get("Electrodes", [])
        if column["name"] not in {name for name, _ in required_columns}
    )

    for name, description in required_columns:
        if name in default_columns or name in existing_columns:
            continue
        nwbfile.add_electrode_column(name=name, description=description)
        existing_columns.add(name)

    dtype_names = contacts.dtype.names
    has_z = "z" in dtype_names
    has_contact_shapes = "contact_shapes" in dtype_names

    def _contact_id(index: int) -> str:
        # Use contact_ids from probe if available
        if "contact_ids" in dtype_names:
            raw_value = contacts["contact_ids"][index]
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode()
            if raw_value:
                return str(raw_value)
        return f"{group_name}_contact_{index}"

    for index in range(contacts.size):
        contact = contacts[index]
        contact_id = _contact_id(index)

        electrode_kwargs = dict(
            x=float(contact["x"]),
            y=float(contact["y"]),
            z=float(contact["z"]) if has_z else float("nan"),
            imp=float("nan"),
            location=group_entry.get("location", "Unknown"),
            filtering="",
            group=electrode_group,
            group_name=group_name,
            electrode_name=contact_id,
            beryl_location="",
            cosmos_location="",
            rel_x=float(contact_positions[index, 0]),
            rel_y=float(contact_positions[index, 1]),
        )

        if has_contact_shapes:
            shape_value = contact["contact_shapes"]
            electrode_kwargs["contact_shapes"] = shape_value.tolist() if hasattr(shape_value, "tolist") else shape_value

        # Add channel_name following SpikeGLX convention: "AP{index},LF{index}"
        # This matches the format used by NeuroConv's SpikeGLXRecordingInterface
        electrode_kwargs["channel_name"] = f"AP{index},LF{index}"

        nwbfile.add_electrode(**electrode_kwargs)


def add_spikeglx_probe_to_nwbfile(
    meta_file: str | Path,
    nwbfile: NWBFile,
    *,
    group_mode: Literal["by_probe", "by_shank"] = "by_probe",
    metadata: Optional[dict] = None,
) -> None:
    """
    Convenience wrapper that reads a SpikeGLX `.meta` file and delegates to
    :func:`add_probe_definition_to_nwbfile`.
    """
    meta_path = Path(meta_file)
    probe = read_spikeglx(meta_path)
    add_probe_definition_to_nwbfile(
        probe=probe,
        nwbfile=nwbfile,
        group_mode=group_mode,
        metadata=metadata,
        source_description=str(meta_path),
    )


def add_probe_electrodes_with_localization(
    *,
    nwbfile: NWBFile,
    one: ONE,
    eid: str,
    probe_name: str,
    pid: str,
    atlas: Optional[AllenAtlas] = None,
    brain_regions: Optional[BrainRegions] = None,
    meta_path: Optional[Path] = None,
) -> List[int]:
    """
    Add electrodes for a Neuropixels probe using the SpikeGLX `.meta` file and enrich with anatomical localization.

    Parameters
    ----------
    nwbfile : NWBFile
        NWB file receiving the electrodes.
    one : ONE
        ONE API client (used to fetch metadata files and histology channels).
    eid : str
        Session identifier.
    probe_name : str
        Probe name (e.g., 'probe00').
    pid : str
        Probe insertion UUID.
    atlas : AllenAtlas, optional
        Atlas instance used to convert IBL coordinates to CCF. Created if not provided.
    brain_regions : BrainRegions, optional
        BrainRegions helper to convert atlas IDs to acronyms. Created if not provided.
    meta_path : Path, optional
        Optional explicit path to the `.meta` file. When omitted the file is downloaded via ONE.

    Returns
    -------
    list[int]
        Electrode indices (in NWB electrode table order) corresponding to the probe channels.
    """

    suffix = probe_name[5:] if probe_name.lower().startswith("probe") else probe_name
    device_name = f"NeuropixelsProbe{suffix}"
    group_name = device_name

    atlas = atlas or AllenAtlas()
    brain_regions = brain_regions or BrainRegions()

    meta_path = _resolve_meta_path(one=one, eid=eid, probe_name=probe_name, meta_path=meta_path)

    if meta_path is None:
        # Fail loudly - missing .meta files indicate a data quality issue
        raise FileNotFoundError(
            f"No SpikeGLX metadata (.meta file) found for probe '{probe_name}' in session '{eid}'. "
            f"Cannot create accurate electrode geometry. "
            f"Ensure raw ephys data has been downloaded from ONE API. "
            f"Collection: raw_ephys_data/{probe_name}"
        )

    # Create metadata for probe from .meta file
    meta_metadata = {
        "Ecephys": {
            "Device": [
                dict(
                    name=device_name,
                    description="Neuropixels probe imported from SpikeGLX metadata.",
                    manufacturer="IMEC",
                )
            ],
            "ElectrodeGroup": [
                dict(
                    name=group_name,
                    description=f"Electrode group for {probe_name}",
                    location="Unresolved",
                    device=device_name,
                )
            ],
            "Electrodes": [
                dict(name="electrode_name", description="Electrode identifier derived from probe contact ids."),
                dict(name="location", description="Brain region acronym per electrode."),
                dict(name="x", description="CCF x coordinate (um)."),
                dict(name="y", description="CCF y coordinate (um)."),
                dict(name="z", description="CCF z coordinate (um)."),
                dict(name="beryl_location", description="Brain region in IBL Beryl atlas (coarse grouping)."),
                dict(name="cosmos_location", description="Brain region in IBL Cosmos atlas (very coarse grouping)."),
            ],
        }
    }

    add_spikeglx_probe_to_nwbfile(
        meta_file=meta_path,
        nwbfile=nwbfile,
        group_mode="by_probe",
        metadata=meta_metadata,
    )

    # Identify electrode indices for this probe.
    electrode_indices: List[int] = []
    for index in range(len(nwbfile.electrodes)):
        if nwbfile.electrodes["group_name"][index] == group_name:
            electrode_indices.append(index)

    if not electrode_indices:
        warnings.warn(
            f"Electrodes were not added for probe '{probe_name}'. Check the SpikeGLX metadata at '{meta_path}'.",
            RuntimeWarning,
            stacklevel=2,
        )
        return []

    # Fetch histology channel data.
    # Note: Histology data is ALF data (revision-dependent), always use BWM standard revision
    atlas = atlas or AllenAtlas()
    brain_regions = brain_regions or BrainRegions()

    BWM_REVISION = "2025-05-06"  # Must match IblAnatomicalLocalizationInterface.REVISION
    loader = SpikeSortingLoader(pid=pid, eid=eid, pname=probe_name, one=one, atlas=atlas, revision=BWM_REVISION)
    try:
        channels = loader.load_channels()
    except Exception as exc:
        warnings.warn(
            f"Unable to load histology channels for probe '{probe_name}': {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return electrode_indices
    if channels is None:
        warnings.warn(
            f"Histology channels unavailable for probe '{probe_name}'. "
            f"Electrode table will have probe geometry from .meta file but no anatomical localization.",
            RuntimeWarning,
            stacklevel=2,
        )
        return electrode_indices

    def _has_channel_field(field: str) -> bool:
        return field in channels

    if not all(_has_channel_field(field) for field in ("x", "y", "z", "atlas_id", "acronym")):
        warnings.warn(
            f"Histology channels missing required fields for probe '{probe_name}'. "
            f"Electrode table will have probe geometry from .meta file but no anatomical localization.",
            RuntimeWarning,
            stacklevel=2,
        )
        return electrode_indices

    n_channels = len(channels["x"])
    if n_channels == 0:
        warnings.warn(
            f"No histology channels available for probe '{probe_name}'.",
            RuntimeWarning,
            stacklevel=2,
        )
        return electrode_indices

    if len(electrode_indices) != n_channels:
        warnings.warn(
            f"Electrode count mismatch for probe '{probe_name}' "
            f"(electrodes={len(electrode_indices)}, histology channels={n_channels}).",
            RuntimeWarning,
            stacklevel=2,
        )

    columns_to_add = [
        ("x", "CCF x coordinate (um)."),
        ("y", "CCF y coordinate (um)."),
        ("z", "CCF z coordinate (um)."),
        ("location", "Brain region acronym per electrode."),
        ("beryl_location", "Brain region in IBL Beryl atlas (coarse grouping)."),
        ("cosmos_location", "Brain region in IBL Cosmos atlas (very coarse grouping)."),
    ]
    existing_columns = set(nwbfile.electrodes.colnames)
    for name, description in columns_to_add:
        if name not in existing_columns:
            nwbfile.add_electrode_column(name=name, description=description)
            existing_columns.add(name)

    channels_x = np.asarray(channels["x"], dtype=np.float64)
    channels_y = np.asarray(channels["y"], dtype=np.float64)
    channels_z = np.asarray(channels["z"], dtype=np.float64)

    atlas_ids = np.asarray(channels["atlas_id"])
    beryl_locations = brain_regions.id2acronym(atlas_id=atlas_ids, mapping="Beryl")
    cosmos_locations = brain_regions.id2acronym(atlas_id=atlas_ids, mapping="Cosmos")
    acronyms = np.asarray(channels["acronym"]).astype(str)

    ccf_coords_um, ccf_regions, _ = convert_ibl_to_ccf3_coordinates(
        atlas=atlas,
        x=channels_x,
        y=channels_y,
        z=channels_z,
        acronyms=acronyms,
        probe_name=probe_name,
        eid=eid,
    )

    electrode_indices_sorted = sorted(electrode_indices)
    for channel_index, electrode_index in enumerate(electrode_indices_sorted):
        index = min(channel_index, n_channels - 1)
        nwbfile.electrodes["x"].data[electrode_index] = float(ccf_coords_um[index, 0])
        nwbfile.electrodes["y"].data[electrode_index] = float(ccf_coords_um[index, 1])
        nwbfile.electrodes["z"].data[electrode_index] = float(ccf_coords_um[index, 2])
        nwbfile.electrodes["location"].data[electrode_index] = ccf_regions[index]
        nwbfile.electrodes["beryl_location"].data[electrode_index] = str(beryl_locations[index])
        nwbfile.electrodes["cosmos_location"].data[electrode_index] = str(cosmos_locations[index])

    return electrode_indices_sorted

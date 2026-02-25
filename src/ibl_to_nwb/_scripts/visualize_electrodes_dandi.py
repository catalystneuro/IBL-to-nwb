"""
Visualize electrode locations from a raw NWB file streamed from DANDI.

This script fetches a raw ecephys NWB file from DANDI archive (dandiset 000409)
and renders electrode positions in 3D using the Allen Mouse Brain Atlas.

See visualize_electrodes.py for coordinate system notes.
"""

import numpy as np

import h5py
import remfile
from brainrender import Scene
from brainrender.actors import Points
from dandi.dandiapi import DandiAPIClient
from pynwb import NWBHDF5IO


# =============================================================================
# Session EIDs for NEW format files (desc-raw / desc-processed)
# =============================================================================

# KS091 sessions (cortexlab)
KS091_SESSION_EID_1 = "78b4fff5-c5ec-44d9-b5f9-d59493063f00"  # 2022-07-04
KS091_SESSION_EID_2 = "196a2adf-ff83-49b2-823a-33f990049c2e"  # 2022-07-05


def fetch_raw_asset(session_eid: str):
    """Fetch the raw NWB asset from DANDI for a given session EID."""
    dandiset_id = "000409"
    client = DandiAPIClient()
    dandiset = client.get_dandiset(dandiset_id, "draft")

    session_assets = [asset for asset in dandiset.get_assets() if session_eid in asset.path]
    raw_asset = next((asset for asset in session_assets if "desc-raw" in asset.path), None)

    if raw_asset is None:
        available = [a.path for a in session_assets]
        raise ValueError(f"No raw asset found for EID {session_eid}. Available: {available}")

    print(f"Found raw file: {raw_asset.path}")
    return raw_asset


def stream_nwb_from_dandi(asset):
    """Open a DANDI asset as a streaming NWB file."""
    asset_url = asset.get_content_url(follow_redirects=1, strip_query=True)
    remote_file = remfile.File(asset_url)
    h5_file = h5py.File(remote_file, "r")
    io = NWBHDF5IO(file=h5_file, load_namespaces=True)
    return io, h5_file


def main():
    # Choose which session to use
    session_eid = KS091_SESSION_EID_2

    # Fetch and stream the raw NWB file
    raw_asset = fetch_raw_asset(session_eid)
    io, h5_file = stream_nwb_from_dandi(raw_asset)

    try:
        nwbfile = io.read()

        # Extract electrode coordinates from electrodes table
        print("Reading electrodes table...")
        x = nwbfile.electrodes["x"].data[:]
        y = nwbfile.electrodes["y"].data[:]
        z = nwbfile.electrodes["z"].data[:]
        group_name = nwbfile.electrodes["group_name"].data[:]

        print(f"Loaded {len(x)} electrode coordinates")
        unique_groups = np.unique(group_name)
        print(f"Probe groups: {unique_groups}")

        # Color electrodes by probe group
        colors = []
        color_map = {"NeuropixelsProbe00": "red", "NeuropixelsProbe01": "blue"}

        scene = Scene(atlas_name="allen_mouse_100um")

        for group in unique_groups:
            mask = group_name == group
            electrodes = np.c_[x[mask], y[mask], z[mask]]
            color = color_map.get(group, "green")
            pts = Points(electrodes, colors=color, radius=30, name=group)
            scene.add(pts)
            print(f"  {group}: {mask.sum()} electrodes ({color})")

        print("Rendering scene...")
        scene.render()

    finally:
        io.close()
        h5_file.close()


if __name__ == "__main__":
    main()

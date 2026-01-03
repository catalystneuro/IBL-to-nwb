"""
Visualize electrode locations from NWB file using brainrender.

This script loads electrode anatomical coordinates from an NWB file and
renders them in 3D using the Allen Mouse Brain Atlas (100um resolution).

COORDINATE SYSTEM NOTES:
-----------------------
The NWB file stores CCF coordinates in native Allen CCF ASL orientation:
    - ASL = (Anterior, Superior, Left)
    - ASL = (AP, DV, ML) in anatomical terms
    - x = AP (Antero-Posterior: front-back)
    - y = DV (Dorso-Ventral: top-bottom)
    - z = ML (Medio-Lateral: left-right)

Brainrender/BrainGlobe also expects coordinates in the same Allen CCF ASL format,
so no coordinate transformation is needed - we can use the coordinates directly.
"""

import numpy as np
from pathlib import Path

from brainrender import Scene
from brainrender.actors import Points
from pynwb import NWBHDF5IO


def main():
    # Load NWB file
    nwbfile_path = Path("/Users/heberto/ibl_data_local_mac/nwbfiles/full/sub-NYU-39/sub-NYU-39_ses-fa1f26a1-eb49-4b24-917e-19f02a18ac61_desc-processed_behavior+ecephys.nwb")

    assert nwbfile_path.exists(), f"NWB file not found at {nwbfile_path}"

    use_electrodes_table = True
    # Read NWB file
    with NWBHDF5IO(str(nwbfile_path), mode='r') as io:
        nwbfile = io.read()
        if use_electrodes_table:
            print("Using electrodes table for coordinates...")
            # Extract anatomical coordinates from electrodes table
            x = nwbfile.electrodes['x'].data[:] # Antero-Posterior (AP)
            y = nwbfile.electrodes['y'].data[:] # Dorso-Vertical (DV)
            z = nwbfile.electrodes['z'].data[:] # Medio-Lateral (ML)
            group_name = nwbfile.electrodes["group_name"].data[:]
            brain_area = nwbfile.electrodes["location"].data[:]

            group_mask = group_name == "NeuropixelsProbe00"

            x_probe = x[group_mask]
            y_probe = y[group_mask]
            z_probe = z[group_mask]
            brain_area_probe = brain_area[group_mask]

        else:
            # Extract anatomical coordinates from CCFv3
            coord_table = nwbfile.lab_meta_data['localization'].anatomical_coordinates_tables[
                'AnatomicalCoordinatesTableElectrodesCCFv3'
            ]

            # NWB stores in ASL orientation (native Allen CCF format)
            x = coord_table['x'][:]  # Antero-Posterior (AP)
            y = coord_table['y'][:]  # Dorso-Ventral (DV)
            z = coord_table['z'][:]  # Medio-Lateral (ML)

    print(f"Loaded {len(x)} electrode coordinates")

    # Coordinates are already in ASL format (AP, DV, ML) - no transformation needed
    electrodes = np.c_[x_probe, y_probe, z_probe]

    # Create scene with Allen Mouse Brain Atlas (100um resolution)
    print("Creating brainrender scene...")
    scene = Scene(atlas_name="allen_mouse_100um")

    # Add electrode points to scene
    pts = Points(electrodes, colors="red", radius=30, name="electrodes")
    scene.add(pts)

    print("Rendering scene...")
    scene.render()


if __name__ == "__main__":
    main()
    
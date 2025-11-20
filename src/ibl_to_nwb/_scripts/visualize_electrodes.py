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
    nwbfile_path = Path(
        "/media/heberto/Expansion/nwbfiles/full/sub-CSHL049/"
        "sub-CSHL049_ses-d839491f-55d8-4cbe-a298-7839208ba12b_desc-raw_ecephys.nwb"
    )
    assert nwbfile_path.exists(), f"NWB file not found at {nwbfile_path}"

    print(f"Loading NWB file from: {nwbfile_path}")

    # Read NWB file
    with NWBHDF5IO(str(nwbfile_path), mode='r') as io:
        nwbfile = io.read()

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
    electrodes = np.c_[x, y, z]

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
    
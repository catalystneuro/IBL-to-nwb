import os
from pathlib import Path

import h5py
import read_after_write as raw
from one.api import ONE
from pynwb import NWBHDF5IO

# the session
eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"  # dual probe session

# local setup
base_path = Path.home() / "ibl_scratch"
nwb_path = base_path / "nwbfiles" / f"{eid}" / f"{eid}.nwb"
cache_folder = base_path / "ibl_conversion" / eid / "cache"

# ONE instantiation
os.makedirs(cache_folder, exist_ok=True)

one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=False,
    cache_dir=cache_folder,
)

# one_revision = dict(revision='2024-05-06')

# NWB file
h5py_file = h5py.File(nwb_path, "r")
io = NWBHDF5IO(file=h5py_file, load_namespaces=True)
nwbfile = io.read()

raw.test_IblSortingInterface(nwbfile, one, eid)
raw.test_WheelInterface(nwbfile, one, eid)
raw.test_RoiMotionEnergyInterface(nwbfile, one, eid)
raw.test_BrainwideMapTrialsInterface(nwbfile, one, eid)
raw.test_IblPoseEstimationInterface(nwbfile, one, eid)
raw.test_LickInterface(nwbfile, one, eid)
raw.test_PupilTrackingInterface(nwbfile, one, eid)

print("all tests passed")  # replace with logger

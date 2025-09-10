# %%
from pathlib import Path
from pynwb import NWBHDF5IO
import numpy as np
from one.api import ONE


def eid2nwbfilename(eid, one, mode="processed"):
    ref = one.eid2ref(eid)
    base_path = Path("/mnt/home/graiser/quarantine/BWM_to_NWB/nwbfiles")
    if mode == "processed":
        suffix = "processed_behavior+ecephys"
    nwbfile_path = base_path / f"sub-{ref['subject']}" / f"sub-{ref['subject']}_ses-{eid}_desc-{suffix}.nwb"
    return nwbfile_path

eid = "4fa70097-8101-4f10-b585-db39429c5ed0" # no cam
eid = "56b57c38-2699-4091-90a8-aba35103155e"
one = ONE()
# nwbfile_path = Path("/mnt/sdceph/users/ibl/data/quarantine/BWM_to_NWB/nwbfiles/sub-NYU-12/sub-NYU-12_ses-a8a8af78-16de-4841-ab07-fde4b5281a03_desc-processed_behavior+ecephys.nwb")
nwbfile_path = eid2nwbfilename(eid, one)
nwbfile = NWBHDF5IO.read_nwb(nwbfile_path)

# %%

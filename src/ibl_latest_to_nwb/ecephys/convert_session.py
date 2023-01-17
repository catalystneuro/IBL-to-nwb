from ibl_to_nwb.tools.ecephys.spikeglx_to_nwb import write_recording
from ibl_to_nwb.tools.ecephys.spikeglx_to_nwb import IBL_CONFIG


cache_path = "/Volumes/t7-ssd/ibl_cache/"

# This is a unique identifier for an experimental session, required for streaming the data from Alyx database
session_id = "0f77ca5d-73c2-45bd-aa4c-4c5ed275dbde"

# Temporarily use session id in the name
nwbfile_path = f"/Volumes/t7-ssd/ibl_cache/{session_id}_ibl_ecephys_stub.nwb"

session_start_time = (
    "2020-09-21T18:58:14"  # TODO: access this from ONE api and other metadata
)
write_recording(
    nwbfile_path=nwbfile_path,
    session_id=session_id,
    metadata=dict(NWBFile=dict(session_start_time=session_start_time)),
)

from pynwb import NWBHDF5IO

io = NWBHDF5IO(nwbfile_path, "r")
nwbfile_in = io.read()

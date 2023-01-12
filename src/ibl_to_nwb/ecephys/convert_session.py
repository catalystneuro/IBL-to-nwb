from src.ibl_to_nwb.tools.ecephys.spikeglx_to_nwb import write_recording

# This is a unique identifier for an experimental session, required for streaming the data from Alyx database
pid = "da8dfec1-d265-44e8-84ce-6ae9c109b8bd"

nwbfile_path = f"/Volumes/t7-ssd/ibl_cache/{pid}_ibl_ecephys_stub.nwb"

session_start_time = (
    "2020-09-21T18:58:14"  # TODO: access this from ONE api and other metadata
)
write_recording(
    nwbfile_path=nwbfile_path,
    pid=pid,
    metadata=dict(NWBFile=dict(session_start_time=session_start_time)),
)

from pynwb import NWBHDF5IO

io = NWBHDF5IO(nwbfile_path, "r")
nwbfile_in = io.read()

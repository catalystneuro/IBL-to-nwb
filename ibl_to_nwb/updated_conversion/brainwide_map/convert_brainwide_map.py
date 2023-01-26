from pathlib import Path

from one.api import ONE
from pydantic import DirectoryPath

from ibl_to_nwb.updated_conversions import StreamingIblRecordingInterface, StreamingIblLfpInterface
from ibl_to_nwb.updated_conversions.brainwidemap import BrainwideMapConverter
from ibl_to_nwb.updated_conversions.data_interfaces import AlfDlcInterface

one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)

sessions = one.alyx.rest(url="sessions", action="list", tag="2022_Q2_IBL_et_al_RepeatedSite")


def convert_session(session: str, base_path: DirectoryPath):
    # Download behavior and spike sorted data for this session
    session_path = base_path / session
    cache_folder = base_path / session / "cache"

    # Get stream names from SI
    ap_stream_names = StreamingIblRecordingInterface.get_stream_names(session=session)
    lf_stream_names = StreamingIblLfpInterface.get_stream_names(session=session)

    # Initialize as many of each interface as we need across the streams
    data_interfaces = list()
    for stream_name in ap_stream_names:
        data_interfaces.append(StreamingIblRecordingInterface(session=session, stream_name=stream_name))
    for stream_name in lf_stream_names:
        data_interfaces.append(StreamingIblLfpInterface(session=session, stream_name=stream_name))
    # TODO: initialize behavior and spike sorting

    for camera_name in ["leftCamera", "rightCamera", "bodyCamera"]:
        camera_files = one.list_datasets(eid=session, filename=f"*{camera_name}.dlc*")
        if any("dlc" in x for x in camera_files):
            data_interfaces.append(AlfDlcInterface(session=session, cache_folder=cache_folder, camera_name=camera_name))

    # Run conversion
    nwbfile_path = session_path / f"{session}.nwb"
    session_converter = BrainwideMapConverter(session=session, data_interfaces=data_interfaces)
    session_converter.run_conversion(nwbfile_path=nwbfile_path, metadata=session_converter.get_metadata())


base_path = Path("/home/jovyan/ibl_conversion")  # prototype on DANDI Hub for now

for session in sessions:
    convert_session(session=session, base_path=base_path)

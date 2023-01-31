from pathlib import Path

from one.api import ONE

from ibl_to_nwb.updated_conversions import StreamingIblRecordingInterface, StreamingIblLfpInterface
from ibl_to_nwb.updated_conversions.brainwidemap import BrainwideMapConverter
from ibl_to_nwb.updated_conversions.datainterfaces import RoiMotionEnergyInterface

one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)

sessions = one.alyx.rest(url="sessions", action="list", tag="2022_Q2_IBL_et_al_RepeatedSite")


def convert_session(session: str, nwbfile_path: str):
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
    # TODO: initialize behavior and spike sorting interfaces

    roi_motion_energy_files = one.list_datasets(eid=session, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
        data_interfaces.append(
            RoiMotionEnergyInterface(session=session, cache_folder=cache_folder, camera_name=camera_name)
        )

    # Run conversion
    nwbfile_path = session_path / f"{session}.nwb"
    session_converter = BrainwideMapConverter(session=session, data_interfaces=data_interfaces)
    session_converter.run_conversion(nwbfile_path=nwbfile_path, metadata=session_converter.get_metadata())


base_path = Path("/home/jovyan/ibl_conversion")  # prototype on DANDI Hub for now

for session in sessions:
    convert_session(session=session, base_path=base_path)

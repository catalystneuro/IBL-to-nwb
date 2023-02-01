from pathlib import Path

from one.api import ONE
from ibl_to_nwb.updated_conversions import StreamingIblRecordingInterface, StreamingIblLfpInterface
from ibl_to_nwb.updated_conversions.brainwidemap import BrainwideMapConverter, BrainwideMapTrialsInterface
from ibl_to_nwb.updated_conversions.datainterfaces import (
    StreamingIblRecordingInterface,
    StreamingIblLfpInterface,
    IblLickInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface
)


def convert_session(base_path: Path, session: str, nwbfile_path: str):
    # Download behavior and spike sorted data for this session
    session_path = base_path / session
    cache_folder = base_path / session / "cache"
    session_one = ONE(cache_dic=cache_folder)

    # Get stream names from SI
    ap_stream_names = StreamingIblRecordingInterface.get_stream_names(session=session)
    lf_stream_names = StreamingIblLfpInterface.get_stream_names(session=session)

    # Initialize as many of each interface as we need across the streams
    data_interfaces = list()
    for stream_name in ap_stream_names:
        data_interfaces.append(
            StreamingIblRecordingInterface(session=session, stream_name=stream_name, cache_folder=cache_folder)
        )
    for stream_name in lf_stream_names:
        data_interfaces.append(
            StreamingIblLfpInterface(session=session, stream_name=stream_name, cache_folder=cache_folder)
        )

    data_interfaces.append(BrainwideMapTrialsInterface(one=session_one, session=session))

    roi_motion_energy_files = session_one.list_datasets(eid=session, filename="*features*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = roi_motion_energy_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
        data_interfaces.append(
            PupilTrackingInterface(one=session_one, session=session, cache_folder=cache_folder, camera_name=camera_name)
        )

    roi_motion_energy_files = one.list_datasets(eid=session, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
        data_interfaces.append(
            RoiMotionEnergyInterface(one=session_one, session=session, camera_name=camera_name)
        )

    if one.list_datasets(eid=session, collection="alf", filename="licks*"):
        data_interfaces.append(IblLickInterface(one=session_one, session=session))


    # Run conversion
    nwbfile_path = session_path / f"{session}.nwb"
    session_converter = BrainwideMapConverter(cache_folder=cache_folder, data_interfaces=data_interfaces)
    session_converter.run_conversion(nwbfile_path=nwbfile_path, metadata=session_converter.get_metadata())


base_path = Path("/home/jovyan/ibl_conversion")  # prototype on DANDI Hub for now

session_retrieval_one = ONE()
sessions = session_retrieval_one.alyx.rest(url="sessions", action="list", tag="2022_Q2_IBL_et_al_RepeatedSite")

for session in sessions:
    convert_session(base_path=base_path, session=session, base_path=base_path)

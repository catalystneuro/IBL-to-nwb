from pathlib import Path

from one.api import ONE

from ibl_to_nwb.updated_conversion.brainwide_map import BrainwideMapConverter
from ibl_to_nwb.updated_conversion.brainwide_map.datainterfaces import (
    BrainwideMapTrialsInterface,
)
from ibl_to_nwb.updated_conversion.datainterfaces import (
    AlfDlcInterface,
    IblSortingInterface,
    IblStreamingLfpInterface,
    IblStreamingRecordingInterface,
    LickInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)


def convert_session(base_path: Path, session: str, nwbfile_path: str, stub_test: bool = False):
    # Download behavior and spike sorted data for this session
    session_path = base_path / session
    cache_folder = base_path / session / "cache"
    session_one = ONE(
        base_url="https://openalyx.internationalbrainlab.org",
        password="international",
        silent=True,
        cache_dir=cache_folder,
    )

    # Get stream names from SI
    ap_stream_names = IblStreamingRecordingInterface.get_stream_names(session=session)
    lf_stream_names = IblStreamingLfpInterface.get_stream_names(session=session)

    # Initialize as many of each interface as we need across the streams
    data_interfaces = list()
    for stream_name in ap_stream_names:
        data_interfaces.append(
            IblStreamingRecordingInterface(
                session=session, stream_name=stream_name, cache_folder=cache_folder / "ap_recordings"
            )
        )
    for stream_name in lf_stream_names:
        data_interfaces.append(
            IblStreamingLfpInterface(
                session=session, stream_name=stream_name, cache_folder=cache_folder / "lf_recordings"
            )
        )

    # These interfaces should always be present in source data
    data_interfaces.append(IblSortingInterface(session=session, cache_folder=cache_folder / "sorting"))
    data_interfaces.append(BrainwideMapTrialsInterface(one=session_one, session=session))
    data_interfaces.append(WheelInterface(one=session_one, session=session))

    # These interfaces may not be present; check if they are before adding to list
    pose_estimation_files = session_one.list_datasets(eid=session, filename="*.dlc*")
    for pose_estimation_file in pose_estimation_files:
        camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
        data_interfaces.append(AlfDlcInterface(one=session_one, session=session, camera_name=camera_name))

    pupil_tracking_files = session_one.list_datasets(eid=session, filename="*features*")
    for pupil_tracking_file in pupil_tracking_files:
        camera_name = pupil_tracking_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
        data_interfaces.append(PupilTrackingInterface(one=session_one, session=session, camera_name=camera_name))

    roi_motion_energy_files = session_one.list_datasets(eid=session, filename="*ROIMotionEnergy.npy*")
    for roi_motion_energy_file in roi_motion_energy_files:
        camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
        data_interfaces.append(RoiMotionEnergyInterface(one=session_one, session=session, camera_name=camera_name))

    if session_one.list_datasets(eid=session, collection="alf", filename="licks*"):
        data_interfaces.append(LickInterface(one=session_one, session=session))

    # Run conversion
    nwbfile_path = session_path / f"{session}.nwb"
    session_converter = BrainwideMapConverter(one=session_one, data_interfaces=data_interfaces)

    conversion_options = dict()
    if stub_test:
        for data_interface_name in session_converter.data_interface_objects:
            if "Recording" in data_interface_name:
                conversion_options.update({data_interface_name: dict(stub_test=True)})

    session_converter.run_conversion(
        nwbfile_path=nwbfile_path, metadata=session_converter.get_metadata(), conversion_options=conversion_options
    )


base_path = Path("/home/jovyan/IBL/")  # prototype on DANDI Hub for now

session_retrieval_one = ONE()
sessions = session_retrieval_one.alyx.rest(url="sessions", action="list", tag="2022_Q4_IBL_et_al_BWM")

for session in sessions[:2]:
    print(f"Converting session '{session['id']}'")
    nwbfile_path = base_path / "nwbfiles" / f"{session}.nwb"
    convert_session(
        base_path=base_path / "ibl_conversion", session=session["id"], nwbfile_path=nwbfile_path, stub_test=True
    )

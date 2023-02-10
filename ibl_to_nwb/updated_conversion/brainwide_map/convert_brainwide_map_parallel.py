import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from shutil import rmtree

from neuroconv.tools.data_transfers import automatic_dandi_upload
from one.api import ONE
from tqdm import tqdm

from ibl_to_nwb.updated_conversion.brainwide_map import BrainwideMapConverter
from ibl_to_nwb.updated_conversion.brainwide_map.datainterfaces import (
    BrainwideMapTrialsInterface,
)
from ibl_to_nwb.updated_conversion.datainterfaces import (
    IblPoseEstimationInterface,
    IblSortingInterface,
    IblStreamingApInterface,
    IblStreamingLfInterface,
    LickInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)


def convert_session(
    base_path: Path, session: str, nwbfile_path: str, stub_test: bool = False, progress_position: int = 0
):
    try:
        if not stub_test:
            assert len(os.environ.get("DANDI_API_KEY", "")) > 0, "Run `export DANDI_API_KEY=...`!"

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
        ap_stream_names = IblStreamingApInterface.get_stream_names(session=session)
        lf_stream_names = IblStreamingLfInterface.get_stream_names(session=session)

        # Initialize as many of each interface as we need across the streams
        data_interfaces = list()
        for stream_name in ap_stream_names:
            data_interfaces.append(
                IblStreamingApInterface(
                    session=session, stream_name=stream_name, cache_folder=cache_folder / "ap_recordings"
                )
            )
        for stream_name in lf_stream_names:
            data_interfaces.append(
                IblStreamingLfInterface(
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
            data_interfaces.append(
                IblPoseEstimationInterface(one=session_one, session=session, camera_name=camera_name)
            )

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
        session_converter = BrainwideMapConverter(one=session_one, session=session, data_interfaces=data_interfaces)

        conversion_options = dict()
        if stub_test:
            for data_interface_name in session_converter.data_interface_objects:
                if "Ap" in data_interface_name or "Lf" in data_interface_name:
                    conversion_options.update({data_interface_name: dict(stub_test=True)})
        else:
            for data_interface_name in session_converter.data_interface_objects:
                if "Ap" in data_interface_name or "Lf" in data_interface_name:
                    conversion_options.update({data_interface_name: dict(progress_position=progress_position)})

        session_converter.run_conversion(
            nwbfile_path=nwbfile_path,
            metadata=session_converter.get_metadata(),
            conversion_options=conversion_options,
            overwrite=True,
        )
        if not stub_test:
            automatic_dandi_upload(dandiset_id="000409", nwb_folder_path=nwbfile_path.parent, cleanup=True)
        rmtree(cache_folder)

        return 1
    except Exception as exception:
        error_file_path = Path(__file__) / f"{session}_error.txt"
        with open(file=error_file_path, mode="w") as file:
            file.write(f"{type(exception)}: {str(exception)}\n{traceback.format_exc()}")
        return 0


number_of_parallel_jobs = 3
base_path = Path("/home/jovyan/IBL/")  # prototype on DANDI Hub for now

session_retrieval_one = ONE(
    base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True
)
brain_wide_sessions = session_retrieval_one.alyx.rest(url="sessions", action="list", tag="2022_Q4_IBL_et_al_BWM")[:5]

with ProcessPoolExecutor(max_workers=number_of_parallel_jobs) as executor:
    with tqdm(total=len(brain_wide_sessions), position=0, desc="Converting sessions...") as main_progress_bar:
        futures = []
        for progress_position, session_info in enumerate(brain_wide_sessions):
            session = session_info["id"]
            nwbfile_path = base_path / "nwbfiles" / session / f"{session}.nwb"
            nwbfile_path.parent.mkdir(exist_ok=True)
            futures.append(
                executor.submit(
                    convert_session,
                    base_path=base_path,
                    session=session,
                    nwbfile_path=nwbfile_path,
                    progress_position=1 + progress_position,
                )
            )
        for future in as_completed(futures):
            status = future.result()
            main_progress_bar.update(1)

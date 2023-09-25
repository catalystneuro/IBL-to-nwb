import os

os.environ["JUPYTER_PLATFORM_DIRS"] = "1"  # Annoying

import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from dandi.download import download as dandi_download
from dandi.organize import organize as dandi_organize
from dandi.upload import upload as dandi_upload
from neuroconv.tools.data_transfers import automatic_dandi_upload
from nwbinspector.tools import get_s3_urls_and_dandi_paths
from one.api import ONE
from pynwb import NWBHDF5IO
from pynwb.image import ImageSeries
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


def convert_and_upload_parallel_processed_only(
    base_path: Path,
    session: str,
    nwbfile_path: str,
    stub_test: bool = False,
    progress_position: int = 0,
    cleanup: bool = False,
    files_mode: str = "move",
):
    try:
        assert len(os.environ.get("DANDI_API_KEY", "")) > 0, "Run `export DANDI_API_KEY=...`!"

        nwbfile_path.parent.mkdir(exist_ok=True)

        # Download behavior and spike sorted data for this session
        session_path = base_path / "ibl_conversion" / session
        cache_folder = base_path / "ibl_conversion" / session / "cache"
        session_one = ONE(
            base_url="https://openalyx.internationalbrainlab.org",
            password="international",
            silent=True,
            cache_dir=cache_folder,
        )

        # Initialize as many of each interface as we need across the streams
        data_interfaces = list()

        # These interfaces should always be present in source data
        data_interfaces.append(IblSortingInterface(session=session, cache_folder=cache_folder / "sorting"))
        data_interfaces.append(BrainwideMapTrialsInterface(one=session_one, session=session))
        data_interfaces.append(WheelInterface(one=session_one, session=session))

        # These interfaces may not be present; check if they are before adding to list
        pose_estimation_files = session_one.list_datasets(eid=session, filename="*.dlc*")
        for pose_estimation_file in pose_estimation_files:
            camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
            data_interfaces.append(
                IblPoseEstimationInterface(
                    one=session_one, session=session, camera_name=camera_name, include_video=False
                )
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
        session_converter = BrainwideMapConverter(
            one=session_one, session=session, data_interfaces=data_interfaces, verbose=False
        )

        metadata = session_converter.get_metadata()
        metadata["NWBFile"]["session_id"] = metadata["NWBFile"]["session_id"] + "-processed-only"

        session_converter.run_conversion(
            nwbfile_path=nwbfile_path,
            metadata=metadata,
            overwrite=True,
        )
        automatic_dandi_upload(
            dandiset_id="000409",
            nwb_folder_path=nwbfile_path.parent,
            cleanup=cleanup,  # files_mode=files_mode
        )
        if cleanup:
            rmtree(cache_folder)
            rmtree(nwbfile_path.parent)

        return 1
    except Exception as exception:
        error_file_path = base_path / "errors" / "7-30-23" / f"{session}_error.txt"
        error_file_path.parent.mkdir(exist_ok=True)
        with open(file=error_file_path, mode="w") as file:
            file.write(f"{type(exception)}: {str(exception)}\n{traceback.format_exc()}")
        return 0


number_of_parallel_jobs = 8
base_path = Path("/home/jovyan/IBL")  # prototype on DANDI Hub for now

session_retrieval_one = ONE(
    base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True
)
brain_wide_sessions = [
    session_info["id"]
    for session_info in session_retrieval_one.alyx.rest(url="sessions", action="list", tag="2022_Q4_IBL_et_al_BWM")
]

# Already written sessions
dandi_file_paths = list(get_s3_urls_and_dandi_paths(dandiset_id="000409").values())
dandi_processed_file_paths = [dandi_file_path for dandi_file_path in dandi_file_paths if "processed" in dandi_file_path]
already_written_processed_sessions = [
    processed_dandi_file_path.split("ses-")[1].split("_")[0].strip("-processed-only")
    for processed_dandi_file_path in dandi_processed_file_paths
]
sessions_to_run = list(set(brain_wide_sessions) - set(already_written_processed_sessions))

with ProcessPoolExecutor(max_workers=number_of_parallel_jobs) as executor:
    with tqdm(total=len(sessions_to_run), position=0, desc="Converting sessions...") as main_progress_bar:
        futures = []
        for progress_position, session in enumerate(sessions_to_run):
            nwbfile_path = base_path / "nwbfiles" / session / f"{session}.nwb"
            nwbfile_path.parent.mkdir(exist_ok=True)
            futures.append(
                executor.submit(
                    convert_and_upload_parallel_processed_only,
                    base_path=base_path,
                    session=session,
                    nwbfile_path=nwbfile_path,
                    progress_position=1 + progress_position,
                    # stub_test=True,
                    # files_mode="copy",  # useful when debugging
                    # cleanup=True,  # causing shutil error ATM
                )
            )
        for future in as_completed(futures):
            status = future.result()
            main_progress_bar.update(1)

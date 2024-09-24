import os

os.environ["JUPYTER_PLATFORM_DIRS"] = "1"  # Annoying

import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from shutil import rmtree

from one.api import ONE
from tqdm import tqdm

from src.ibl_to_nwb.brainwide_map import BrainwideMapConverter
from src.ibl_to_nwb.brainwide_map.datainterfaces import (
    BrainwideMapTrialsInterface,
)
from src.ibl_to_nwb.datainterfaces import (
    IblPoseEstimationInterface,
    IblSortingInterface,
    IblStreamingApInterface,
    IblStreamingLfInterface,
    LickInterface,
    PupilTrackingInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)

# def automatic_dandi_upload(
#     dandiset_id: str,
#     nwb_folder_path: str,
#     dandiset_folder_path: str = None,
#     version: str = "draft",
#     files_mode: str = "move",
#     staging: bool = False,
#     cleanup: bool = False,
# ):
#     """
#     Fully automated upload of NWBFiles to a DANDISet.
#
#     Requires an API token set as an envrinment variable named DANDI_API_KEY.
#
#     To set this in your bash terminal in Linux or MacOS, run
#         export DANDI_API_KEY=...
#     or in Windows
#         set DANDI_API_KEY=...
#
#     DO NOT STORE THIS IN ANY PUBLICLY SHARED CODE.
#
#     Parameters
#     ----------
#     dandiset_id : str
#         Six-digit string identifier for the DANDISet the NWBFiles will be uploaded to.
#     nwb_folder_path : folder path
#         Folder containing the NWBFiles to be uploaded.
#     dandiset_folder_path : folder path, optional
#         A separate folder location within which to download the dandiset.
#         Used in cases where you do not have write permissions for the parent of the 'nwb_folder_path' directory.
#         Default behavior downloads the DANDISet to a folder adjacent to the 'nwb_folder_path'.
#     version : {None, "draft", "version"}
#         The default is "draft".
#     staging : bool, default: False
#         Is the DANDISet hosted on the staging server? This is mostly for testing purposes.
#         The default is False.
#     cleanup : bool, default: False
#         Whether to remove the dandiset folder path and nwb_folder_path.
#         Defaults to False.
#     """
#     nwb_folder_path = Path(nwb_folder_path)
#     dandiset_folder_path = (
#         Path(mkdtemp(dir=nwb_folder_path.parent)) if dandiset_folder_path is None else dandiset_folder_path
#     )
#     dandiset_path = dandiset_folder_path / dandiset_id
#     assert os.getenv("DANDI_API_KEY"), (
#         "Unable to find environment variable 'DANDI_API_KEY'. "
#         "Please retrieve your token from DANDI and set this environment variable."
#     )
#
#     url_base = "https://gui-staging.dandiarchive.org" if staging else "https://dandiarchive.org"
#     dandiset_url = f"{url_base}/dandiset/{dandiset_id}/{version}"
#     dandi_download(urls=dandiset_url, output_dir=str(dandiset_folder_path), get_metadata=True, get_assets=False)
#     assert dandiset_path.exists(), "DANDI download failed!"
#
#     dandi_organize(
#         paths=str(nwb_folder_path),
#         dandiset_path=str(dandiset_path),
#         update_external_file_paths=True,
#         files_mode=files_mode,
#         media_files_mode=files_mode,
#     )
#     organized_nwbfiles = dandiset_path.rglob("*.nwb")
#
#     # DANDI has yet to implement forcing of session_id inclusion in organize step
#     # This manually enforces it when only a single session per subject is organized
#     for organized_nwbfile in organized_nwbfiles:
#         if "ses" not in organized_nwbfile.stem:
#             with NWBHDF5IO(path=organized_nwbfile, mode="r", load_namespaces=True) as io:
#                 nwbfile = io.read()
#                 session_id = nwbfile.session_id
#             dandi_stem = organized_nwbfile.stem
#             dandi_stem_split = dandi_stem.split("_")
#             dandi_stem_split.insert(1, f"ses-{session_id}")
#             corrected_name = "_".join(dandi_stem_split) + ".nwb"
#             organized_nwbfile.rename(organized_nwbfile.parent / corrected_name)
#     organized_nwbfiles = list(dandiset_path.rglob("*.nwb"))
#     # The above block can be removed once they add the feature
#
#     # If any external images
#     image_folders = set(dandiset_path.rglob("*image*")) - set(organized_nwbfiles)
#     for image_folder in image_folders:
#         if "ses" not in image_folder.stem and len(organized_nwbfiles) == 1:  # Think about multiple file case
#             corrected_name = "_".join(dandi_stem_split)
#             image_folder = image_folder.rename(image_folder.parent / corrected_name)
#
#             # For image in folder, rename
#             with NWBHDF5IO(path=organized_nwbfiles[0], mode="r+", load_namespaces=True) as io:
#                 nwbfile = io.read()
#                 for _, object in nwbfile.objects.items():
#                     if isinstance(object, ImageSeries):
#                         this_external_file = image_folder / Path(str(object.external_file[0])).name
#                         corrected_name = "_".join(dandi_stem_split[:2]) + f"_{object.name}{this_external_file.suffix}"
#                         this_external_file = this_external_file.rename(this_external_file.parent / corrected_name)
#                         object.external_file[0] = "./" + str(this_external_file.relative_to(organized_nwbfile.parent))
#
#     assert len(list(dandiset_path.iterdir())) > 1, "DANDI organize failed!"
#
#     dandi_instance = "dandi-staging" if staging else "dandi"
#     dandi_upload(paths=[dandiset_folder_path / dandiset_id], dandi_instance=dandi_instance)
#
#     # Cleanup should be confirmed manually; Windows especially can complain
#     if cleanup:
#         try:
#             rmtree(path=dandiset_folder_path)
#         except PermissionError:  # pragma: no cover
#             warn("Unable to clean up source files and dandiset! Please manually delete them.", stacklevel=2)


def convert_and_upload_session(
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

        # Download behavior and spike sorted data for this session
        # session_path = base_path / "ibl_conversion" / session
        cache_folder = base_path / "ibl_conversion" / session / "cache"
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
        session_converter = BrainwideMapConverter(
            one=session_one, session=session, data_interfaces=data_interfaces, verbose=False
        )

        conversion_options = dict()
        if stub_test:
            for data_interface_name in session_converter.data_interface_objects:
                if "Ap" in data_interface_name or "Lf" in data_interface_name:
                    conversion_options.update(
                        {
                            data_interface_name: dict(
                                progress_position=progress_position,
                                stub_test=True,
                            )
                        }
                    )
        else:
            for data_interface_name in session_converter.data_interface_objects:
                if "Ap" in data_interface_name or "Lf" in data_interface_name:
                    conversion_options.update(
                        {
                            data_interface_name: dict(
                                progress_position=progress_position,
                            )
                        }
                    )

        metadata = session_converter.get_metadata()

        session_converter.run_conversion(
            nwbfile_path=nwbfile_path,
            metadata=metadata,
            conversion_options=conversion_options,
            overwrite=True,
        )
        # automatic_dandi_upload(
        #     dandiset_id="000409", nwb_folder_path=nwbfile_path.parent, cleanup=cleanup, files_mode=files_mode
        # )
        if cleanup:
            rmtree(cache_folder)
            rmtree(nwbfile_path.parent)

        return 1
    except Exception as exception:
        error_file_path = base_path / "errors" / "8-7-23" / f"{session}_error.txt"
        error_file_path.parent.mkdir(exist_ok=True)
        with open(file=error_file_path, mode="w") as file:
            file.write(f"{type(exception)}: {str(exception)}\n{traceback.format_exc()}")
        return 0


number_of_parallel_jobs = 8
base_path = Path("/home/jovyan/IBL")  # prototype on DANDI Hub for now

session_retrieval_one = ONE(
    base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True
)
brain_wide_sessions = session_retrieval_one.alyx.rest(url="sessions", action="list", tag="2022_Q4_IBL_et_al_BWM")

with ProcessPoolExecutor(max_workers=number_of_parallel_jobs) as executor:
    with tqdm(total=len(brain_wide_sessions), position=0, desc="Converting sessions...") as main_progress_bar:
        futures = []
        for progress_position, session_info in enumerate(brain_wide_sessions):
            session = session_info["id"]
            nwbfile_path = base_path / "nwbfiles" / session / f"{session}.nwb"
            nwbfile_path.parent.mkdir(exist_ok=True)
            futures.append(
                executor.submit(
                    convert_and_upload_session,
                    base_path=base_path,
                    session=session,
                    nwbfile_path=nwbfile_path,
                    progress_position=1 + progress_position,
                    # stub_test=True,
                    # files_mode="copy",  # useful when debugging
                    # cleanup=False,
                )
            )
        for future in as_completed(futures):
            status = future.result()
            main_progress_bar.update(1)

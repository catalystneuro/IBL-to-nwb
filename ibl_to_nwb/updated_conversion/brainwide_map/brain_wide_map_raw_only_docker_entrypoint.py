import os
import traceback
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from warnings import warn

from dandi.download import download as dandi_download
from dandi.organize import organize as dandi_organize
from dandi.upload import upload as dandi_upload
from one.api import ONE
from pynwb import NWBHDF5IO
from pynwb.image import ImageSeries

from ibl_to_nwb.updated_conversion.brainwide_map import BrainwideMapConverter
from ibl_to_nwb.updated_conversion.datainterfaces import (
    IblStreamingApInterface,
    IblStreamingLfInterface,
    IblPoseEstimationInterface,
)


def automatic_dandi_upload(
    dandiset_id: str,
    nwb_folder_path: str,
    dandiset_folder_path: str = None,
    version: str = "draft",
    files_mode: str = "move",
    staging: bool = False,
    cleanup: bool = False,
):
    """
    Fully automated upload of NWBFiles to a DANDISet.

    Requires an API token set as an envrinment variable named DANDI_API_KEY.

    To set this in your bash terminal in Linux or MacOS, run
        export DANDI_API_KEY=...
    or in Windows
        set DANDI_API_KEY=...

    DO NOT STORE THIS IN ANY PUBLICLY SHARED CODE.

    Parameters
    ----------
    dandiset_id : str
        Six-digit string identifier for the DANDISet the NWBFiles will be uploaded to.
    nwb_folder_path : folder path
        Folder containing the NWBFiles to be uploaded.
    dandiset_folder_path : folder path, optional
        A separate folder location within which to download the dandiset.
        Used in cases where you do not have write permissions for the parent of the 'nwb_folder_path' directory.
        Default behavior downloads the DANDISet to a folder adjacent to the 'nwb_folder_path'.
    version : {None, "draft", "version"}
        The default is "draft".
    staging : bool, default: False
        Is the DANDISet hosted on the staging server? This is mostly for testing purposes.
        The default is False.
    cleanup : bool, default: False
        Whether to remove the dandiset folder path and nwb_folder_path.
        Defaults to False.
    """
    nwb_folder_path = Path(nwb_folder_path)
    dandiset_folder_path = (
        Path(mkdtemp(dir=nwb_folder_path.parent)) if dandiset_folder_path is None else dandiset_folder_path
    )
    dandiset_path = dandiset_folder_path / dandiset_id
    assert os.getenv("DANDI_API_KEY"), (
        "Unable to find environment variable 'DANDI_API_KEY'. "
        "Please retrieve your token from DANDI and set this environment variable."
    )

    url_base = "https://gui-staging.dandiarchive.org" if staging else "https://dandiarchive.org"
    dandiset_url = f"{url_base}/dandiset/{dandiset_id}/{version}"
    dandi_download(urls=dandiset_url, output_dir=str(dandiset_folder_path), get_metadata=True, get_assets=False)
    assert dandiset_path.exists(), "DANDI download failed!"

    dandi_organize(
        paths=str(nwb_folder_path),
        dandiset_path=str(dandiset_path),
        update_external_file_paths=True,
        files_mode=files_mode,
        media_files_mode=files_mode,
    )
    organized_nwbfiles = dandiset_path.rglob("*.nwb")

    # DANDI has yet to implement forcing of session_id inclusion in organize step
    # This manually enforces it when only a single sesssion per subject is organized
    for organized_nwbfile in organized_nwbfiles:
        if "ses" not in organized_nwbfile.stem:
            with NWBHDF5IO(path=organized_nwbfile, mode="r", load_namespaces=True) as io:
                nwbfile = io.read()
                session_id = nwbfile.session_id
            dandi_stem = organized_nwbfile.stem
            dandi_stem_split = dandi_stem.split("_")
            dandi_stem_split.insert(1, f"ses-{session_id}")
            corrected_name = "_".join(dandi_stem_split) + ".nwb"
            organized_nwbfile.rename(organized_nwbfile.parent / corrected_name)
    organized_nwbfiles = list(dandiset_path.rglob("*.nwb"))
    # The above block can be removed once they add the feature

    # If any external images
    image_folders = set(dandiset_path.rglob("*image*")) - set(organized_nwbfiles)
    for image_folder in image_folders:
        if "ses" not in image_folder.stem and len(organized_nwbfiles) == 1:  # Think about multiple file case
            corrected_name = "_".join(dandi_stem_split)
            image_folder = image_folder.rename(image_folder.parent / corrected_name)

            # For image in folder, rename
            with NWBHDF5IO(path=organized_nwbfiles[0], mode="r+", load_namespaces=True) as io:
                nwbfile = io.read()
                for _, object in nwbfile.objects.items():
                    if isinstance(object, ImageSeries):
                        this_external_file = image_folder / Path(str(object.external_file[0])).name
                        corrected_name = "_".join(dandi_stem_split[:2]) + f"_{object.name}{this_external_file.suffix}"
                        this_external_file = this_external_file.rename(this_external_file.parent / corrected_name)
                        object.external_file[0] = "./" + str(this_external_file.relative_to(organized_nwbfile.parent))

    assert len(list(dandiset_path.iterdir())) > 1, "DANDI organize failed!"

    dandi_instance = "dandi-staging" if staging else "dandi"
    dandi_upload(paths=[dandiset_folder_path / dandiset_id], dandi_instance=dandi_instance)

    # Cleanup should be confirmed manually; Windows especially can complain
    if cleanup:
        try:
            rmtree(path=dandiset_folder_path)
        except PermissionError:  # pragma: no cover
            warn("Unable to clean up source files and dandiset! Please manually delete them.", stacklevel=2)


def convert_and_upload_session(
    base_path: Path,
    session: str,
    nwbfile_path: str,
    stub_test: bool = False,
    cleanup: bool = False,
    files_mode: str = "move",
):
    try:
        assert len(os.environ.get("DANDI_API_KEY", "")) > 0, "Run `export DANDI_API_KEY=...`!"

        # Download behavior and spike sorted data for this session
        session_path = base_path / "ibl_conversion" / session
        cache_folder = session_path / "cache"
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

        # These interfaces may not be present; check if they are before adding to list
        pose_estimation_files = session_one.list_datasets(eid=session, filename="*.dlc*")
        for pose_estimation_file in pose_estimation_files:
            camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
            data_interfaces.append(
                IblPoseEstimationInterface(one=session_one, session=session, camera_name=camera_name)
            )

        # Run conversion
        session_converter = BrainwideMapConverter(
            one=session_one, session=session, data_interfaces=data_interfaces, verbose=False
        )

        conversion_options = dict()
        if stub_test:
            for data_interface_name in session_converter.data_interface_objects:
                if "Ap" in data_interface_name or "Lf" in data_interface_name:
                    conversion_options.update({data_interface_name: dict(stub_test=True)})

        session_converter.run_conversion(
            nwbfile_path=nwbfile_path,
            metadata=session_converter.get_metadata(),
            conversion_options=conversion_options,
            overwrite=True,
        )
        automatic_dandi_upload(
            dandiset_id="000409", nwb_folder_path=nwbfile_path.parent, cleanup=cleanup, files_mode=files_mode
        )
        if cleanup:
            rmtree(cache_folder)
            rmtree(nwbfile_path.parent)

        return 1
    except Exception as exception:
        error_file_path = base_path / "errors" / f"{session}_error.txt"
        error_file_path.parent.mkdir(exist_ok=True)
        with open(file=error_file_path, mode="w") as file:
            file.write(f"{type(exception)}: {str(exception)}\n{traceback.format_exc()}")
        return 0


base_path = Path(".")
session = os.environ["SESSION_ID"]

nwbfile_path = base_path / "nwbfiles" / session / f"{session}.nwb"
nwbfile_path.parent.mkdir(exist_ok=True)

convert_and_upload_session(base_path=base_path, session=session, nwbfile_path=nwbfile_path)

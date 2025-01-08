import os
import sys
from datetime import datetime
from pathlib import Path

# if running on SDSC, use the OneSdsc, else normal
if "USE_SDSC_ONE" in os.environ:
    from deploy.iblsdsc import OneSdsc as ONE
else:
    from one.api import ONE

from ibl_to_nwb.converters import BrainwideMapConverter, IblSpikeGlxConverter
from ibl_to_nwb.datainterfaces import (
    BrainwideMapTrialsInterface,
    IblPoseEstimationInterface,
    IblSortingInterface,
    LickInterface,
    PupilTrackingInterface,
    RawVideoInterface,
    RoiMotionEnergyInterface,
    WheelInterface,
)


def get_last_before(eid: str, one: ONE, revision: str):
    revisions = one.list_revisions(eid, revision="*")
    revisions = [datetime.strptime(revision, "%Y-%m-%d") for revision in revisions]
    revision = datetime.strptime(revision, "%Y-%m-%d")
    revisions = sorted(revisions)
    ix = sum([not (rev > revision) for rev in revisions]) - 1
    return revisions[ix].strftime("%Y-%m-%d")


def convert(eid: str, one: ONE, data_interfaces: list, revision: str, mode: str):
    # Run conversion
    session_converter = BrainwideMapConverter(one=one, session=eid, data_interfaces=data_interfaces, verbose=True)
    metadata = session_converter.get_metadata()
    metadata["NWBFile"]["session_id"] = f"{eid}:{revision}"  # FIXME this hack has to go
    subject_id = metadata["Subject"]["subject_id"]

    subject_folder_path = output_folder / f"sub-{subject_id}"
    subject_folder_path.mkdir(exist_ok=True)
    if mode == "raw":
        fname = f"sub-{subject_id}_ses-{eid}_desc-raw_ecephys+image.nwb"
    if mode == "processed":
        fname = f"sub-{subject_id}_ses-{eid}_desc-processed_behavior+ecephys.nwb"

    nwbfile_path = subject_folder_path / fname
    session_converter.run_conversion(
        nwbfile_path=nwbfile_path,
        metadata=metadata,
        overwrite=True,
    )
    return nwbfile_path


if __name__ == "__main__":
    if len(sys.argv) == 1:
        eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"
        mode = "raw"
    else:
        eid = sys.argv[1]
        mode = sys.argv[2]  # raw or processed

    # path setup
    base_path = Path.home() / "ibl_scratch"
    output_folder = base_path / "nwbfiles"
    output_folder.mkdir(exist_ok=True, parents=True)

    one_kwargs = dict(
        base_url="https://openalyx.internationalbrainlab.org",
        password="international",
        mode="remote",
    )

    # if not running on SDSC adding the cache folder explicitly
    if "USE_SDSC_ONE" not in os.environ:
        # Initialize IBL (ONE) client to download processed data for this session
        one_cache_folder_path = base_path / "ibl_conversion" / eid / "cache"
        one_kwargs["cache_dir"] = one_cache_folder_path

    # instantiate one
    one = ONE(**one_kwargs)

    # correct revision
    revision = get_last_before(eid=eid, one=one, revision="2024-07-10")

    # Initialize as many of each interface as we need across the streams
    data_interfaces = []

    if mode == "raw":
        # ephys
        session_folder = one.eid2path(eid)
        spikeglx_source_folder_path = session_folder / "raw_ephys_data"

        # Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
        spikeglx_subconverter = IblSpikeGlxConverter(folder_path=spikeglx_source_folder_path, one=one, eid=eid)
        data_interfaces.append(spikeglx_subconverter)

        # video
        metadata_retrieval = BrainwideMapConverter(one=one, session=eid, data_interfaces=[], verbose=False)
        subject_id = metadata_retrieval.get_metadata()["Subject"]["subject_id"]

        pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
        for pose_estimation_file in pose_estimation_files:
            camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")

            video_interface = RawVideoInterface(
                nwbfiles_folder_path=output_folder,
                subject_id=subject_id,
                one=one,
                session=eid,
                camera_name=camera_name,
            )
            data_interfaces.append(video_interface)

    if mode == "processed":
        # These interfaces should always be present in source data
        data_interfaces.append(IblSortingInterface(one=one, session=eid, revision=revision))
        data_interfaces.append(BrainwideMapTrialsInterface(one=one, session=eid, revision=revision))
        data_interfaces.append(WheelInterface(one=one, session=eid, revision=revision))

        # # These interfaces may not be present; check if they are before adding to list
        pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
        for pose_estimation_file in pose_estimation_files:
            camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
            data_interfaces.append(
                IblPoseEstimationInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
            )

        pupil_tracking_files = one.list_datasets(eid=eid, filename="*features*")
        for pupil_tracking_file in pupil_tracking_files:
            camera_name = pupil_tracking_file.replace("alf/_ibl_", "").replace(".features.pqt", "")
            data_interfaces.append(
                PupilTrackingInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
            )

        roi_motion_energy_files = one.list_datasets(eid=eid, filename="*ROIMotionEnergy.npy*")
        for roi_motion_energy_file in roi_motion_energy_files:
            camera_name = roi_motion_energy_file.replace("alf/", "").replace(".ROIMotionEnergy.npy", "")
            data_interfaces.append(
                RoiMotionEnergyInterface(one=one, session=eid, camera_name=camera_name, revision=revision)
            )

        if one.list_datasets(eid=eid, collection="alf", filename="licks*"):
            data_interfaces.append(LickInterface(one=one, session=eid, revision=revision))

    # run the conversion
    nwbfile_path = convert(
        eid=eid,
        one=one,
        data_interfaces=data_interfaces,
        revision=revision,
        mode=mode,
    )

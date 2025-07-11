from shutil import copyfile
from typing import Literal

from neuroconv.basedatainterface import BaseDataInterface
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile
from pynwb.image import ImageSeries


class RawVideoInterface(BaseDataInterface):
    def __init__(
        self,
        nwbfiles_folder_path: DirectoryPath,
        subject_id: str,
        one: ONE,
        session: str,
        camera_name: Literal["left", "right", "body"],
    ) -> None:
        """
        Interface for the raw video data from the IBL Brainwide Map release.

        Parameters
        ----------
        nwbfiles_folder_path : DirectoryPath
            The folder path where the NWB file will be written in DANDI organization structure.
            This is an unusual value to pass to __init__, but in this case it is necessary to simplify the DANDI
            organization of the externally stored raw video data.
        subject_id : str
            The subject ID to use for the DANDI organization. This is also an unusual value to pass to __init__, but
            the custom handling of Subject extensions requires removing it from the main metadata at runtime.
        one : one.ONE
            The ONE API client.
        session : str
            The session ID (EID in ONE).
        camera_name : "left", "right", or "body"
            The name of the camera to load the raw video data for.
        revision : str, optional
            The revision of the pose estimation data to use. If not provided, the latest revision will be used.
        """
        self.nwbfiles_folder_path = nwbfiles_folder_path
        self.subject_id = subject_id
        self.one = one
        self.session = session
        self.camera_name = camera_name

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict) -> None:
        camera_data = self.one.load_object(id=self.session, obj=self.camera_name, collection="alf")
        timestamps = camera_data["times"]

        camera_view = self.camera_name.split("Camera")[0]  # left, right or body
        video_filename = f"raw_video_data/_iblrig_{self.camera_name}.raw.mp4"
        if self.one.list_datasets(eid=self.session, filename=video_filename):
            original_video_file_path = self.one.load_dataset(
                id=self.session, dataset=video_filename, download_only=True
            )

            # Rename to DANDI format and relative organization
            dandi_sub_stem = f"sub-{self.subject_id}"
            dandi_subject_folder = self.nwbfiles_folder_path / dandi_sub_stem

            dandi_sub_ses_stem = f"{dandi_sub_stem}_ses-{self.session}"
            dandi_video_folder_path = dandi_subject_folder / f"{dandi_sub_ses_stem}_ecephys+image"
            dandi_video_folder_path.mkdir(exist_ok=True, parents=True)

            nwb_video_name = f"OriginalVideo{camera_view.capitalize()}Camera"
            dandi_video_file_path = dandi_video_folder_path / f"{dandi_sub_ses_stem}_{nwb_video_name}.mp4"

            # A little bit of data duplication to copy, but easier for re-running since original file stays in cache
            copyfile(src=original_video_file_path, dst=dandi_video_file_path)

            image_series = ImageSeries(
                name=nwb_video_name,
                description="The original video each pose was estimated from.",
                unit="n.a.",
                external_file=["./" + str(dandi_video_file_path.relative_to(dandi_subject_folder))],
                format="external",
                timestamps=timestamps,
            )
            nwbfile.add_acquisition(image_series)

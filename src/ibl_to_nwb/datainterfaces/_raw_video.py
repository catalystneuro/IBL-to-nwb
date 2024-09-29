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

        left_right_or_body = self.camera_name[:5].removesuffix("C")
        if self.one.list_datasets(eid=self.session, filename=f"raw_video_data/*{self.camera_name}*"):
            original_video_file_path = self.one.load_dataset(
                id=self.session, dataset=f"raw_video_data/*{self.camera_name}*", download_only=True
            )

            nwb_video_name = f"OriginalVideo{left_right_or_body.capitalize()}Camera"

            # Rename to DANDI format and relative organization
            dandi_sub_stem = f"sub-{self.subject_id}"
            dandi_sub_ses_stem = f"{dandi_sub_stem}_ses-{self.session}"
            dandi_video_folder_path = self.nwbfiles_folder_path / dandi_sub_stem / f"{dandi_sub_ses_stem}_ecephys+image"
            dandi_video_folder_path.mkdir(exist_ok=True)
            dandi_video_file_path = dandi_video_folder_path / f"{dandi_sub_ses_stem}_{nwb_video_name}.mp4"

            # Move the file into the new DANDI folder and rename to the DANDI pattern
            original_video_file_path.rename(dandi_video_file_path)

            image_series = ImageSeries(
                name=nwb_video_name,
                description="The original video each pose was estimated from.",
                unit="n.a.",
                external_file=[str(original_video_file_path)],
                format="external",
                timestamps=timestamps,
            )
            nwbfile.add_acquisition(image_series)

from shutil import copyfile
from typing import Literal, Optional
import logging
import time

from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile
from pynwb.image import ImageSeries

from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures import load_fixtures


class RawVideoInterface(BaseIBLDataInterface):
    """Interface for raw video data and camera timestamps."""

    # Camera timestamps use BWM standard revision (timestamps were corrected/processed)
    # Raw video .mp4 files themselves are immutable, but timestamps are ALF data
    REVISION: str | None = "2025-05-06"

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
        """
        self.nwbfiles_folder_path = nwbfiles_folder_path
        self.subject_id = subject_id
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls, camera_name: Literal["left", "right", "body"]) -> dict:
        """
        Declare exact data files required for raw video.

        Parameters
        ----------
        camera_name : "left", "right", or "body"
            Camera view name

        Returns
        -------
        dict
            Data requirements with exact file paths
        """
        camera_object_name = f"{camera_name}Camera"
        return {
            "one_objects": [
                {
                    "object": camera_object_name,
                    "collection": "alf",
                    "attributes": ["times"],
                },
            ],
            "exact_files_options": {
                "standard": [
                    f"alf/{camera_object_name}.times.npy",
                    f"raw_video_data/_iblrig_{camera_object_name}.raw.mp4",
                ],
            },
        }

    @classmethod
    def check_availability(
        cls,
        one: ONE,
        eid: str,
        camera_name: Literal["left", "right", "body"],
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Check if raw video data is available for a session/camera, including QC filtering.

        This method checks BOTH file existence AND video quality control status.
        Sessions with CRITICAL or FAIL video QC are excluded to ensure high-quality video data.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        camera_name : "left", "right", or "body"
            Camera view name
        logger : logging.Logger, optional
            Logger for progress tracking

        Returns
        -------
        dict
            {"available": bool, "reason": str, "qc_status": str or None}
        """
        # STEP 1: Check video quality control from bwm_qc.json
        # Following revision_2 approach: exclude CRITICAL/FAIL videos
        # Fail-fast: if bwm_qc.json is missing/corrupted, let exception propagate
        bwm_qc = load_fixtures.load_bwm_qc()

        if eid not in bwm_qc:
            # Session not in QC database - allow it (might be new session)
            if logger:
                logger.warning(f"Session {eid} not in QC database - allowing raw video")
            video_qc_status = None
        else:
            video_qc_key = f"video{camera_name.capitalize()}"
            video_qc_status = bwm_qc[eid].get(video_qc_key, None)

            if video_qc_status in ['CRITICAL', 'FAIL']:
                if logger:
                    logger.info(f"Raw video for {camera_name} camera excluded: video QC is {video_qc_status}")
                return {
                    "available": False,
                    "reason": f"Video quality control failed: {video_qc_status}",
                    "qc_status": video_qc_status
                }

        # STEP 2: Check if raw video files exist (uses base class implementation)
        file_check_result = super(RawVideoInterface, cls).check_availability(
            one=one, eid=eid, camera_name=camera_name, logger=logger, **kwargs
        )

        # Add QC status to result
        file_check_result["qc_status"] = video_qc_status

        return file_check_result

    @classmethod
    def download_data(
        cls,
        one: ONE,
        eid: str,
        camera_name: Literal["left", "right", "body"],
        download_only: bool = True,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Download raw video data for a specific camera.

        NOTE: Uses class-level REVISION attribute for camera timestamps.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        camera_name : "left", "right", or "body"
            Camera view name (required)
        download_only : bool, default=True
            If True, download but don't load into memory
        logger : logging.Logger, optional
            Logger for progress tracking

        Returns
        -------
        dict
            Download status
        """
        requirements = cls.get_data_requirements(camera_name=camera_name)
        camera_object_name = f"{camera_name}Camera"

        # Use class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading raw video for {camera_name} camera (session {eid})")

        start_time = time.time()

        # Download timestamps - NO try-except, let failures propagate
        if logger:
            logger.info(f"  Loading {camera_object_name} timestamps")

        one.load_object(
            id=eid,
            obj=camera_object_name,
            collection="alf",
            revision=revision,
            download_only=download_only,
        )

        # Download video file - NO try-except, let failures propagate
        video_filename = f"raw_video_data/_iblrig_{camera_object_name}.raw.mp4"
        if logger:
            logger.info(f"  Loading video file: {video_filename}")

        one.load_dataset(
            eid,
            video_filename,
            download_only=download_only,
        )

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded video data in {download_time:.2f}s")

        return {
            "success": True,
            "downloaded_objects": [camera_object_name],
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict) -> None:
        # Convert camera_name ("left", "right", "body") to ONE object name ("leftCamera", etc.)
        camera_object_name = f"{self.camera_name}Camera"

        camera_data = self.one.load_object(
            id=self.session,
            obj=camera_object_name,
            collection="alf",
            revision=self.revision,
        )
        timestamps = camera_data["times"]

        video_filename = f"raw_video_data/_iblrig_{camera_object_name}.raw.mp4"
        # Note: Don't filter videos by revision - they may not have the same revision as other data
        if self.one.list_datasets(eid=self.session, filename=video_filename):
            original_video_file_path = self.one.load_dataset(
                id=self.session,
                dataset=video_filename,
                download_only=True,
            )

            # Rename to DANDI format and relative organization
            dandi_sub_stem = f"sub-{self.subject_id}"
            dandi_subject_folder = self.nwbfiles_folder_path / dandi_sub_stem

            dandi_sub_ses_stem = f"{dandi_sub_stem}_ses-{self.session}"
            dandi_video_folder_path = dandi_subject_folder / f"{dandi_sub_ses_stem}_ecephys+image"
            dandi_video_folder_path.mkdir(exist_ok=True, parents=True)

            nwb_video_name = f"Video{self.camera_name.capitalize()}Camera"
            dandi_video_file_path = dandi_video_folder_path / f"{dandi_sub_ses_stem}_{nwb_video_name}.mp4"

            # A little bit of data duplication to copy, but easier for re-running since original file stays in cache
            copyfile(src=original_video_file_path, dst=dandi_video_file_path)

            image_series = ImageSeries(
                name=nwb_video_name,
                description="Raw video from camera recording behavioral and task events.",
                unit="n.a.",
                external_file=["./" + str(dandi_video_file_path.relative_to(dandi_subject_folder))],
                format="external",
                timestamps=timestamps,
            )
            nwbfile.add_acquisition(image_series)

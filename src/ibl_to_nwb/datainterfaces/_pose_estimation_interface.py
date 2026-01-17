import logging
import re
import time
from typing import Optional

import numpy as np
from brainbox.io.one import SessionLoader
from ndx_pose import PoseEstimation, PoseEstimationSeries, Skeleton, Skeletons
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile

from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures import load_fixtures

# Mapping from IBL body part names (snake_case) to NWB names
# Following NWB best practices: PoseEstimationSeries{BodyPart}
IBL_TO_NWB_BODY_PART_NAMES = {
    # Nose
    "nose_tip": "PoseEstimationSeriesNoseTip",
    # Paws - IBL uses _l/_r suffix, we use Left/Right prefix for clarity
    "paw_l": "PoseEstimationSeriesLeftPaw",
    "paw_r": "PoseEstimationSeriesRightPaw",
    # Tongue
    "tongue_end_l": "PoseEstimationSeriesLeftTongueEnd",
    "tongue_end_r": "PoseEstimationSeriesRightTongueEnd",
    # Pupil markers (from left camera viewing right side of face)
    "pupil_top_r": "PoseEstimationSeriesRightPupilTop",
    "pupil_bottom_r": "PoseEstimationSeriesRightPupilBottom",
    "pupil_left_r": "PoseEstimationSeriesRightPupilLeft",
    "pupil_right_r": "PoseEstimationSeriesRightPupilRight",
    # Tube (lick spout)
    "tube_top": "PoseEstimationSeriesTubeTop",
    "tube_bottom": "PoseEstimationSeriesTubeBottom",
    # Body camera specific
    "tail_start": "PoseEstimationSeriesTailStart",
}


class IblPoseEstimationInterface(BaseIBLDataInterface):
    """Interface for pose estimation data (revision-dependent processed data)."""

    # Pose estimation uses BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(
        self,
        one: ONE,
        session: str,
        camera_name: str,
        tracker: str = 'lightningPose',
    ) -> None:
        """
        Interface for Lightning Pose estimation data from the IBL Brainwide Map release.

        Parameters
        ----------
        one : one.ONE
            The ONE API client.
        session : str
            The session ID (EID in ONE).
        camera_name : "left", "right", or "body"
            The name of the camera to load pose estimation data for.
        tracker : str, optional
            The tracker to use. Default is 'lightningPose'.
        """
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.tracker = tracker
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls, camera_name: str) -> dict:
        """
        Declare exact data files required for pose estimation.

        Parameters
        ----------
        camera_name : str
            Camera name (e.g., "leftCamera", "rightCamera", "bodyCamera")

        Returns
        -------
        dict
            Data requirements
        """
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)
        return {
            "exact_files_options": {
                "standard": [f"alf/_ibl_{camera_view}Camera.lightningPose.pqt"],
            },
        }

    @classmethod
    def get_session_loader_kwargs(cls, camera_name: str, tracker: str = "lightningPose") -> dict:
        """
        Return kwargs for SessionLoader.load_pose() call.

        Parameters
        ----------
        camera_name : str
            Camera name (e.g., "leftCamera", "rightCamera", "bodyCamera")
        tracker : str
            Tracker name. Default is "lightningPose".

        Returns
        -------
        dict
            Kwargs for SessionLoader.load_pose()
        """
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)
        return {"tracker": tracker, "views": [camera_view]}

    @classmethod
    def check_availability(
        cls,
        one: ONE,
        eid: str,
        camera_name: str,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Check if pose estimation data is available for a session/camera, including QC filtering.

        This method checks BOTH file existence AND video quality control status.
        Sessions with CRITICAL or FAIL video QC are excluded to ensure high-quality pose tracking.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        camera_name : str
            Camera name (e.g., "leftCamera", "rightCamera", "bodyCamera")
        logger : logging.Logger, optional
            Logger for progress tracking

        Returns
        -------
        dict
            {"available": bool, "reason": str, "qc_status": str or None}
        """
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)

        # STEP 1: Check video quality control from bwm_qc.json
        # Following revision_2 approach: exclude CRITICAL/FAIL videos
        # Fail-fast: if bwm_qc.json is missing/corrupted, let exception propagate
        bwm_qc = load_fixtures.load_bwm_qc()

        if eid not in bwm_qc:
            # Session not in QC database - allow it (might be new session)
            if logger:
                logger.warning(f"Session {eid} not in QC database - allowing pose estimation")
            video_qc_status = None
        else:
            video_qc_key = f"video{camera_view.capitalize()}"
            video_qc_status = bwm_qc[eid].get(video_qc_key, None)

            if video_qc_status in ['CRITICAL', 'FAIL']:
                if logger:
                    logger.info(f"Pose estimation for {camera_name} excluded: video QC is {video_qc_status}")
                return {
                    "available": False,
                    "reason": f"Video quality control failed: {video_qc_status}",
                    "qc_status": video_qc_status
                }

        # STEP 2: Check if pose estimation files exist (uses base class implementation)
        file_check_result = super(IblPoseEstimationInterface, cls).check_availability(
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
        camera_name: str,
        download_only: bool = True,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Download Lightning Pose estimation data.

        NOTE: Uses class-level REVISION attribute automatically.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        camera_name : str
            Camera name (required)
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
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)

        # Use class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading pose estimation for {camera_view} camera (session {eid})")

        start_time = time.time()

        # No try-except - check availability first, then download
        for option_name, option_files in requirements["exact_files_options"].items():
            filename_pattern = option_files[0].split("/")[-1]  # e.g., "_ibl_leftCamera.lightningPose.pqt"

            if logger:
                logger.info(f"  Checking {option_name}: {filename_pattern}")

            # Find matching datasets
            candidates = []
            candidates.extend(one.list_datasets(eid, filename=filename_pattern))
            if revision:
                candidates.extend(one.list_datasets(eid, filename=filename_pattern, revision=revision))

            candidates = sorted(set(candidates))

            if not candidates:
                if logger:
                    logger.info(f"    No {option_name} files found, trying next option...")
                continue

            # Files exist - download them (let it fail if download fails)
            if logger:
                logger.info(f"  Downloading {option_name}...")

            dataset_path = candidates[0]
            one.load_dataset(eid, dataset=dataset_path, download_only=download_only)

            download_time = time.time() - start_time

            if logger:
                logger.info(f"  Downloaded {option_name} in {download_time:.2f}s")

            return {
                "success": True,
                "downloaded_objects": [],
                "downloaded_files": option_files,
                "already_cached": [],
                "alternative_used": option_name,
                "data": None,
            }

        # If we get here, NONE of the options were found - FAIL LOUDLY
        raise FileNotFoundError(
            f"No pose estimation data found for {camera_view} camera (session {eid}). "
            f"Tried: {list(requirements['exact_files_options'].keys())}"
        )

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict) -> None:
        """
        Add Lightning Pose estimation data to NWB file.

        Data should already be downloaded via download_data().
        """
        session_loader = SessionLoader(one=self.one, eid=self.session, revision=self.revision)
        camera_view = re.search(r"(left|right|body)Camera*", self.camera_name).group(1)

        # Load pose data using kwargs from get_session_loader_kwargs
        session_loader_kwargs = self.get_session_loader_kwargs(camera_name=self.camera_name, tracker=self.tracker)
        session_loader.load_pose(**session_loader_kwargs)

        if self.camera_name not in session_loader.pose:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' not found in session '{self.session}'"
            )

        pose_data = session_loader.pose[self.camera_name]

        if "times" not in pose_data or pose_data["times"].empty:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' in session '{self.session}' contains no timestamps"
            )

        timestamps = pose_data["times"].values
        pose_data = pose_data.drop("times", axis=1)
        number_of_frames = len(timestamps)

        if number_of_frames == 0:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' in session '{self.session}' contains no frames"
            )


        body_parts = []
        for column in pose_data.columns:
            if not column.endswith('_x'):
                continue
            base_name = column[:-2]
            if (f'{base_name}_y' in pose_data.columns) and (f'{base_name}_likelihood' in pose_data.columns):
                body_parts.append(base_name)
        body_parts = sorted(set(body_parts))

        if not body_parts:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' in session '{self.session}' has no labeled body parts with x/y/likelihood columns"
            )
        # TODO: Discuss with team how to handle Lightning Pose ensemble/uncertainty data
        # Lightning Pose provides additional data beyond basic x,y,likelihood:
        # - ensemble_median: more robust predictions from multiple models
        # - ensemble_variance: disagreement between models (quality measure)
        # - posterior_variance: Bayesian uncertainty estimates
        # Currently filtering these out to maintain compatibility with existing NWB structure.
        # Consider: separate data objects, metadata fields, or extended pose schema.

        # Filter out ensemble and posterior columns, extract body parts
        # body_parts = set()
        # for field in pose_data.keys():
        #     # Skip ensemble and posterior variance columns
        #     if any(suffix in field for suffix in ['_ens_', '_posterior_']):
        #         continue
        #     # Extract body part name from basic x, y, likelihood columns
        #     if field.endswith('_x') or field.endswith('_y') or field.endswith('_likelihood'):
        #         body_part = field.replace('_x', '').replace('_y', '').replace('_likelihood', '')
        #         body_parts.add(body_part)

        body_parts = list(body_parts)
        skeleton_name = f"{camera_view.capitalize()}Camera"
        skeletons_container_name = "Skeletons"

        reused_timestamps = None
        all_pose_estimation_series = list()

        # Convert body part names to CamelCase for NWB
        nwb_body_part_names = [IBL_TO_NWB_BODY_PART_NAMES.get(bp, bp) for bp in body_parts]

        for body_part, nwb_name in zip(body_parts, nwb_body_part_names):
            required_columns = [f"{body_part}_x", f"{body_part}_y", f"{body_part}_likelihood"]
            for column in required_columns:
                if column not in pose_data:
                    raise RuntimeError(
                        f"Pose data for camera '{self.camera_name}' in session '{self.session}' is missing column '{column}'"
                    )

            body_part_data = np.empty(shape=(number_of_frames, 2))
            body_part_data[:, 0] = pose_data[f"{body_part}_x"]
            body_part_data[:, 1] = pose_data[f"{body_part}_y"]

            pose_estimation_series = PoseEstimationSeries(
                name=nwb_name,
                description=f"Marker placed on or around, labeled '{nwb_name}'.",
                data=body_part_data,
                unit="px",
                reference_frame="(0,0) corresponds to the upper left corner when using width by height convention.",
                timestamps=reused_timestamps or timestamps,
                confidence=np.array(pose_data[f"{body_part}_likelihood"]),

            )
            all_pose_estimation_series.append(pose_estimation_series)

            reused_timestamps = all_pose_estimation_series[0]  # A trick for linking timestamps across series

        skeleton_kwargs = dict(
            name=skeleton_name,
            nodes=nwb_body_part_names,
            edges=np.empty(shape=(0, 2), dtype="uint8"),
        )
        if nwbfile.subject is not None:
            skeleton_kwargs["subject"] = nwbfile.subject
        skeleton = Skeleton(**skeleton_kwargs)

        camera_module = get_module(nwbfile=nwbfile, name="pose_estimation", description="Pose estimation from video using Lightning Pose.")
        if skeletons_container_name in camera_module.data_interfaces:
            skeletons_container = camera_module.data_interfaces[skeletons_container_name]
            if skeleton_name in skeletons_container.skeletons:
                skeleton = skeletons_container.skeletons[skeleton_name]
            else:
                skeletons_container.add_skeletons(skeleton)
                skeleton = skeletons_container.skeletons[skeleton_name]
        else:
            skeletons_container = Skeletons(name=skeletons_container_name, skeletons=[skeleton])
            camera_module.add(skeletons_container)

        pose_estimation_kwargs = dict(
            name=f"{camera_view.capitalize()}Camera",
            pose_estimation_series=all_pose_estimation_series,
            description="Estimated positions of body parts using Lightning Pose.",
            source_software="Lightning Pose",
            skeleton=skeleton,
        )
        pose_estimation_container = PoseEstimation(**pose_estimation_kwargs)

        camera_module.add(pose_estimation_container)

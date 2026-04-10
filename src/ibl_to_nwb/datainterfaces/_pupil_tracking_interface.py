"""Data Interface for the pupil tracking."""

import logging
import re
from typing import Optional

import numpy as np
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import TimeSeries

from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures import load_fixtures


class PupilTrackingInterface(BaseIBLDataInterface):
    """Interface for pupil tracking data (revision-dependent processed data)."""

    # Pupil tracking uses BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(self, one: ONE, session: str, camera_name: str):
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls, camera_name: str) -> dict:
        """
        Declare exact data files required for pupil tracking.

        Parameters
        ----------
        camera_name : str
            Camera name (e.g., "leftCamera", "rightCamera")

        Returns
        -------
        dict
            Data requirements with ONE objects and exact file paths
        """
        return {
            "exact_files_options": {
                "standard": [
                    f"alf/_ibl_{camera_name}.features.pqt",
                    f"alf/_ibl_{camera_name}.times.npy",
                ],
            },
        }

    @classmethod
    def check_quality(cls, one: ONE, eid: str, logger: Optional[logging.Logger] = None, **kwargs) -> Optional[dict]:
        """
        Check video QC status from bwm_qc.json.

        Sessions with CRITICAL or FAIL video QC are excluded to ensure high-quality pupil data.
        """
        camera_name = kwargs.get("camera_name")
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)

        bwm_qc = load_fixtures.load_bwm_qc()

        if eid not in bwm_qc:
            if logger:
                logger.warning(f"Session {eid} not in QC database - allowing pupil tracking")
            return {"qc_status": None}

        video_qc_key = f"video{camera_view.capitalize()}"
        video_qc_status = bwm_qc[eid].get(video_qc_key, None)

        if video_qc_status in ["CRITICAL", "FAIL"]:
            if logger:
                logger.info(f"Pupil tracking for {camera_name} excluded: video QC is {video_qc_status}")
            return {
                "available": False,
                "reason": f"Video quality control failed: {video_qc_status}",
                "qc_status": video_qc_status,
            }

        return {"qc_status": video_qc_status}

    @classmethod
    def get_load_object_kwargs(cls, camera_name: str) -> dict:
        """Return kwargs for one.load_object() call."""
        return {"obj": camera_name, "collection": "alf"}

    def add_to_nwbfile(self, nwbfile, metadata: dict):
        camera_view = re.search(r"(left|right|body)Camera*", self.camera_name).group(1)
        camera_data = self.one.load_object(
            id=self.session, revision=self.revision, **self.get_load_object_kwargs(self.camera_name)
        )

        if "features" not in camera_data:
            raise RuntimeError(
                f"Pupil tracking data for camera '{self.camera_name}' in session '{self.session}' has no features table"
            )

        if "times" not in camera_data or camera_data["times"].size == 0:
            raise RuntimeError(
                f"Pupil tracking data for camera '{self.camera_name}' in session '{self.session}' contains no timestamps"
            )

        # Check for dimension mismatch between features and times
        features_len = len(camera_data["features"])
        times_len = len(camera_data["times"])

        if features_len != times_len:
            import warnings

            if features_len > times_len:
                # Data is longer than timestamps - this is an error!
                # We have data samples without corresponding time information
                error_msg = (
                    f"Pupil tracking data for {self.camera_name} in session {self.session} has "
                    f"more data samples ({features_len}) than timestamps ({times_len}). "
                    f"Cannot proceed without time information for all samples."
                )
                warnings.warn(error_msg, RuntimeWarning, stacklevel=2)
                raise RuntimeError(error_msg)
            else:
                # Timestamps are longer than data - we can truncate timestamps
                # This means we have extra timestamps at the end without corresponding data
                missing_samples = times_len - features_len
                warnings.warn(
                    f"Truncating timestamps for {self.camera_name} in session {self.session}: "
                    f"timestamps length ({times_len}) exceeds features length ({features_len}) by {missing_samples} samples. "
                    f"Using first {features_len} timestamps.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                camera_data["times"] = camera_data["times"][:features_len]

        # Add pupil data to dedicated pupil module
        pupil_module = get_module(
            nwbfile=nwbfile,
            name="pupil",
            description=(
                "Pupil diameter measurements from video-based eye tracking. "
                "Pupil diameter is estimated using pose estimation (DLC/Lightning Pose) to track keypoints "
                "around the pupil boundary. Diameter is computed as the median of multiple estimates "
                "(vertical, horizontal, and circular fits) for robustness. "
                "Pupil diameter correlates with arousal, attention, and cognitive state."
            ),
        )

        # Check required columns exist
        for ibl_key in ["pupilDiameter_raw", "pupilDiameter_smooth"]:
            if ibl_key not in camera_data["features"]:
                raise RuntimeError(
                    f"Pupil tracking data for camera '{self.camera_name}' in session '{self.session}' is missing column '{ibl_key}'"
                )

        # Pupil diameter (unsmoothed)
        raw_pupil_series = TimeSeries(
            name=f"{camera_view.capitalize()}PupilDiameter",
            description=(
                "Raw pupil diameter estimated from pose tracking keypoints around the pupil boundary. "
                "Multiple diameter estimates are computed: vertical (top-bottom distance), horizontal "
                "(left-right distance), and circular fits from other keypoint pairs. The final value "
                "is the median of these estimates, providing robustness against individual tracking errors."
            ),
            data=np.array(camera_data["features"]["pupilDiameter_raw"]),
            timestamps=camera_data["times"],
            unit="px",
        )
        pupil_module.add(raw_pupil_series)

        # Smoothed pupil diameter
        smoothed_pupil_series = TimeSeries(
            name=f"{camera_view.capitalize()}PupilDiameterSmoothed",
            description=(
                "Smoothed pupil diameter. This version has been temporally smoothed and interpolated "
                "over frames with missing or low-confidence keypoint detections. Useful for analyses "
                "where smooth trajectories are preferred over frame-by-frame accuracy."
            ),
            data=np.array(camera_data["features"]["pupilDiameter_smooth"]),
            timestamps=camera_data["times"],
            unit="px",
        )
        pupil_module.add(smoothed_pupil_series)

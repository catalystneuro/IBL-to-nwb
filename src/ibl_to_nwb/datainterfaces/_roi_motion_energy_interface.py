"""Data Interface for the special data type of ROI Motion Energy."""

import logging
import re
from typing import Optional

from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import TimeSeries

from ._base_ibl_interface import BaseIBLDataInterface
from ..fixtures import load_fixtures


class RoiMotionEnergyInterface(BaseIBLDataInterface):
    """Interface for ROI motion energy data (revision-dependent processed data)."""

    # ROI motion energy uses BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(self, one: ONE, session: str, camera_name: str):
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls, camera_name: str) -> dict:
        """
        Declare exact data files required for ROI motion energy.

        Parameters
        ----------
        camera_name : str
            Camera name (e.g., "leftCamera", "rightCamera", "bodyCamera")

        Returns
        -------
        dict
            Data requirements with ONE objects and exact file paths
        """
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)
        return {
            "exact_files_options": {
                "standard": [
                    f"alf/{camera_name}.ROIMotionEnergy.npy",
                    f"alf/_ibl_{camera_name}.times.npy",
                    f"alf/{camera_view}ROIMotionEnergy.position.npy",
                ],
            },
        }

    @classmethod
    def check_quality(
        cls,
        one: ONE,
        eid: str,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> Optional[dict]:
        """
        Check video QC status from bwm_qc.json.

        Sessions with CRITICAL or FAIL video QC are excluded to ensure high-quality motion energy data.
        """
        camera_name = kwargs.get("camera_name")
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)

        bwm_qc = load_fixtures.load_bwm_qc()

        if eid not in bwm_qc:
            if logger:
                logger.warning(f"Session {eid} not in QC database - allowing ROI motion energy")
            return {"qc_status": None}

        video_qc_key = f"video{camera_view.capitalize()}"
        video_qc_status = bwm_qc[eid].get(video_qc_key, None)

        if video_qc_status in ['CRITICAL', 'FAIL']:
            if logger:
                logger.info(f"ROI motion energy for {camera_name} excluded: video QC is {video_qc_status}")
            return {
                "available": False,
                "reason": f"Video quality control failed: {video_qc_status}",
                "qc_status": video_qc_status
            }

        return {"qc_status": video_qc_status}

    @classmethod
    def get_load_object_kwargs(cls, camera_name: str) -> list[dict]:
        """
        Return kwargs for one.load_object() calls.

        Returns a list because this interface loads two objects:
        1. Camera data (ROIMotionEnergy, times)
        2. ROI position data
        """
        camera_view = re.search(r"(left|right|body)", camera_name).group(1)
        return [
            {"obj": camera_name, "collection": "alf"},
            {"obj": f"{camera_view}ROIMotionEnergy", "collection": "alf"},
        ]

    def add_to_nwbfile(self, nwbfile, metadata: dict):
        camera_view = re.search(r"(left|right|body)Camera*", self.camera_name).group(1)
        load_kwargs_list = self.get_load_object_kwargs(self.camera_name)

        camera_data = self.one.load_object(id=self.session, revision=self.revision, **load_kwargs_list[0])

        if "ROIMotionEnergy" not in camera_data or "times" not in camera_data:
            raise RuntimeError(
                f"ROI motion energy data for camera '{self.camera_name}' in session '{self.session}' is incomplete"
            )

        if camera_data["times"].size == 0:
            raise RuntimeError(
                f"ROI motion energy timestamps for camera '{self.camera_name}' in session '{self.session}' are empty"
            )

        motion_energy_video_region = self.one.load_object(id=self.session, revision=self.revision, **load_kwargs_list[1])

        # extra dirty hack to be removed
        # if self.session == "dc21e80d-97d7-44ca-a729-a8e3f9b14305" and camera_view == 'right': # the broken session
        #     camera_data["features"] = pd.read_parquet(Path("/mnt/sdceph/users/ibl/data/wittenlab/Subjects/ibl_witten_26/2021-01-31/001/alf/#2025-06-04#/_ibl_rightCamera.features.c9658c1b-1d93-469c-9faf-76d535205485.pqt"))

        if "position" not in motion_energy_video_region:
            raise RuntimeError(
                f"ROI motion energy metadata missing position for camera '{self.camera_name}' in session '{self.session}'"
            )

        width, height, x, y = motion_energy_video_region["position"]

        description = (
            f"Motion energy calculated for a region of the {camera_view} camera video that is {width} pixels "
            f"wide, {height} pixels tall, and the top-left corner of the region is the pixel ({x}, {y}).\n\n"
            "CAUTION: As each software will load the video in a different orientation, the ROI might need to be "
            "adapted. For example, when loading the video with cv2 in Python, x and y axes are flipped from the "
            f"convention used above. The region then becomes [{y}:{y + height}, {x}:{x + width}]."
        )

        motion_energy_series = TimeSeries(
            name=f"TimeSeries{camera_view.capitalize()}MotionEnergy",
            description=description,
            data=camera_data["ROIMotionEnergy"],
            timestamps=camera_data["times"],
            unit="a.u.",
        )

        video_module = get_module(nwbfile=nwbfile, name="video", description="Scalar signals derived from video.")
        video_module.add(motion_energy_series)

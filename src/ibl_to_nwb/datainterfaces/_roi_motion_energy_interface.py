"""Data Interface for the special data type of ROI Motion Energy."""

import re
from typing import Optional

from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import TimeSeries
import pandas as pd
from pathlib import Path

class RoiMotionEnergyInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, camera_name: str, revision: Optional[str] = None):
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.revision = one.list_revisions(session)[-1] if revision is None else revision

    def add_to_nwbfile(self, nwbfile, metadata: dict):
        # left_right_or_body = self.camera_name[:5].rstrip("C")
        camera_view = re.search(r"(left|right|body)Camera*", self.camera_name).group(1)
        camera_data = self.one.load_object(
            id=self.session, obj=self.camera_name, collection="alf", revision=self.revision
        )

        if "ROIMotionEnergy" not in camera_data or "times" not in camera_data:
            raise RuntimeError(
                f"ROI motion energy data for camera '{self.camera_name}' in session '{self.session}' is incomplete"
            )

        if camera_data["times"].size == 0:
            raise RuntimeError(
                f"ROI motion energy timestamps for camera '{self.camera_name}' in session '{self.session}' are empty"
            )

        motion_energy_video_region = self.one.load_object(
            id=self.session, obj=f"{camera_view}ROIMotionEnergy", collection="alf"
        )

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
            name=f"{camera_view.capitalize()}CameraMotionEnergy",
            description=description,
            data=camera_data["ROIMotionEnergy"],
            timestamps=camera_data["times"],
            unit="a.u.",
        )

        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        camera_module.add(motion_energy_series)

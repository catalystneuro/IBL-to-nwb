"""Data Interface for the special data type of ROI Motion Energy."""
from typing import Optional

from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import TimeSeries


class RoiMotionEnergyInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, camera_name: str, revision: Optional[str] = None):
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.revision = one.list_revisions(session)[-1] if revision is None else revision

    def add_to_nwbfile(self, nwbfile, metadata: dict):
        left_right_or_body = self.camera_name[:5].rstrip("C")

        camera_data = self.one.load_object(id=self.session, obj=self.camera_name, collection="alf")
        motion_energy_video_region = self.one.load_object(
            id=self.session, obj=f"{left_right_or_body}ROIMotionEnergy", collection="alf", revision=self.revision
        )

        width, height, x, y = motion_energy_video_region["position"]

        description = (
            f"Motion energy calculated for a region of the {left_right_or_body} camera video that is {width} pixels "
            f"wide, {height} pixels tall, and the top-left corner of the region is the pixel ({x}, {y}).\n\n"
            "CAUTION: As each software will load the video in a different orientation, the ROI might need to be "
            "adapted. For example, when loading the video with cv2 in Python, x and y axes are flipped from the "
            f"convention used above. The region then becomes [{y}:{y+height}, {x}:{x+width}]."
        )

        motion_energy_series = TimeSeries(
            name=f"{left_right_or_body.capitalize()}CameraMotionEnergy",
            description=description,
            data=camera_data["ROIMotionEnergy"],
            timestamps=camera_data["times"],
            unit="a.u.",
        )

        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        camera_module.add(motion_energy_series)

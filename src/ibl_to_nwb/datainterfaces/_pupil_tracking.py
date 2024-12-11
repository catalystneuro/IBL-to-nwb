"""Data Interface for the pupil tracking."""

from pathlib import Path

import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import TimeSeries
from pynwb.behavior import PupilTracking


class PupilTrackingInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, camera_name: str, revision: str | None = None):
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.revision = one.list_revisions(session)[-1] if revision is None else revision

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        pupils_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "pupils.yml")
        metadata.update(pupils_metadata)

        return metadata

    def add_to_nwbfile(self, nwbfile, metadata: dict):
        left_or_right = self.camera_name[:5].rstrip("C")

        camera_data = self.one.load_object(id=self.session, obj=self.camera_name, collection="alf", revision=self.revision)

        pupil_time_series = list()
        for ibl_key in ["pupilDiameter_raw", "pupilDiameter_smooth"]:
            pupil_time_series.append(
                TimeSeries(
                    name=left_or_right.capitalize() + metadata["Pupils"][ibl_key]["name"],
                    description=metadata["Pupils"][ibl_key]["description"],
                    data=np.array(camera_data["features"][ibl_key]),
                    timestamps=camera_data["times"],
                    unit="px",
                )
            )
        # Normally best practice convention would be PupilTrackingLeft or PupilTrackingRight but
        # in this case I'd say LeftPupilTracking and RightPupilTracking reads better
        pupil_tracking = PupilTracking(name=f"{left_or_right.capitalize()}PupilTracking", time_series=pupil_time_series)

        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        camera_module.add(pupil_tracking)

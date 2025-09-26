"""Data Interface for the pupil tracking."""

import re
from pathlib import Path
from typing import Optional

import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import TimeSeries
from pynwb.behavior import PupilTracking
import pandas as pd


class PupilTrackingInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, camera_name: str, revision: Optional[str] = None):
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
        camera_view = re.search(r"(left|right|body)Camera*", self.camera_name).group(1)
        camera_data = self.one.load_object(
            id=self.session, obj=self.camera_name, collection="alf", revision=self.revision
        )

        # extra dirty hack to be removed
        # if self.session == "dc21e80d-97d7-44ca-a729-a8e3f9b14305" and camera_view == 'right': # the broken session
        #     camera_data["features"] = pd.read_parquet(Path("/mnt/sdceph/users/ibl/data/wittenlab/Subjects/ibl_witten_26/2021-01-31/001/alf/#2025-06-04#/_ibl_rightCamera.features.c9658c1b-1d93-469c-9faf-76d535205485.pqt"))

        pupil_time_series = list()
        for ibl_key in ["pupilDiameter_raw", "pupilDiameter_smooth"]:
            pupil_time_series.append(
                TimeSeries(
                    name=camera_view.capitalize() + metadata["Pupils"][ibl_key]["name"],
                    description=metadata["Pupils"][ibl_key]["description"],
                    data=np.array(camera_data["features"][ibl_key]),
                    timestamps=camera_data["times"],
                    unit="px",
                )
            )
        # Normally best practice convention would be PupilTrackingLeft or PupilTrackingRight but
        # in this case I'd say LeftPupilTracking and RightPupilTracking reads better
        pupil_tracking = PupilTracking(name=f"{camera_view.capitalize()}PupilTracking", time_series=pupil_time_series)

        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        camera_module.add(pupil_tracking)

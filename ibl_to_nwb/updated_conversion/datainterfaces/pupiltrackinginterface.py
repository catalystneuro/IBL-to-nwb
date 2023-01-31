"""Data Interface for the pupil tracking."""
from pathlib import Path

import numpy as np
from one.api import ONE
from pynwb import TimeSeries, H5DataIO
from pynwb.behavior import PupilTracking
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file


class PupilTrackingInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, camera_name: str):
        self.one = one
        self.session = session
        self.camera_name = camera_name

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        pupils_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "pupils.yml")
        metadata.update(pupils_metadata)
        return metadata

    def run_conversion(self, nwbfile, metadata: dict):
        one = ONE(
            base_url='https://openalyx.internationalbrainlab.org',
            password='international',
            silent=True,
            cache_folder=self.cache_folder,
        )

        left_or_right = self.camera_name[:5].rstrip("C")

        camera_data = one.load_object(id=self.session, obj=self.camera_name, collection="alf")

        behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="processed behavioral data")
        pupil_time_series = list()
        for ibl_key in ["pupilDiameter_raw", "pupilDiameter_smooth"]:
            pupil_time_series.append(
                TimeSeries(
                    name=left_or_right + metadata["Pupils"][ibl_key]["name"],
                    description=metadata["Pupils"][ibl_key]["description"],
                    data=H5DataIO(np.array(camera_data["features"][ibl_key]), compression=True),
                    timestamps=camera_data["times"],
                    unit="px",
                )
            )
        pupil_tracking = PupilTracking(time_series=pupil_time_series)
        behavior_module.add(pupil_tracking)

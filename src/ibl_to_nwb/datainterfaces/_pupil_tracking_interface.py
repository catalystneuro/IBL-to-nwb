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
                    stacklevel=2
                )
                camera_data["times"] = camera_data["times"][:features_len]

        pupil_time_series = list()
        for ibl_key in ["pupilDiameter_raw", "pupilDiameter_smooth"]:
            if ibl_key not in camera_data["features"]:
                raise RuntimeError(
                    f"Pupil tracking data for camera '{self.camera_name}' in session '{self.session}' is missing column '{ibl_key}'"
                )
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

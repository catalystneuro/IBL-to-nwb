from datetime import datetime
from typing import Optional

import numpy as np
from ndx_pose import PoseEstimation, PoseEstimationSeries
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile


class IblPoseEstimationInterface(BaseDataInterface):
    def __init__(
        self,
        one: ONE,
        session: str,
        camera_name: str,
        revision: Optional[str] = None,
    ) -> None:
        """
        Interface for the pose estimation (DLC) data from the IBL Brainwide Map release.

        Parameters
        ----------
        one : one.ONE
            The ONE API client.
        session : str
            The session ID (EID in ONE).
        camera_name : "left", "right", or "body"
            The name of the camera to load the raw video data for.
        revision : str, optional
            The revision of the pose estimation data to use. If not provided, the latest revision will be used.
        """
        self.one = one
        self.session = session
        self.camera_name = camera_name

        self.revision = revision
        if self.revision is None:
            self.revision = one.list_revisions(session)[-1]
        #     session_files = self.one.list_datasets(eid=self.session, filename=f"*{self.camera_name}.dlc*")
        #     revision_datetime_format = "%Y-%m-%d"
        #     revisions = [
        #         datetime.strptime(session_file.split("#")[1], revision_datetime_format)
        #         for session_file in session_files
        #         if "#" in session_file
        #     ]

        #     if any(revisions):
        #         most_recent = max(revisions)
        #         self.revision = most_recent.strftime("%Y-%m-%d")

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict) -> None:
        camera_data = self.one.load_object(
            id=self.session, obj=self.camera_name, collection="alf", revision=self.revision
        )
        dlc_data = camera_data["dlc"]
        timestamps = camera_data["times"]
        number_of_frames = len(timestamps)
        body_parts = list(
            set(field.replace("_x", "").replace("_y", "").replace("_likelihood", "") for field in dlc_data.keys())
        )

        left_right_or_body = self.camera_name[:5].rstrip("C")
        reused_timestamps = None
        all_pose_estimation_series = list()

        for body_part in body_parts:
            body_part_data = np.empty(shape=(number_of_frames, 2))
            body_part_data[:, 0] = dlc_data[f"{body_part}_x"]
            body_part_data[:, 1] = dlc_data[f"{body_part}_y"]

            pose_estimation_series = PoseEstimationSeries(
                name=body_part,
                description=f"Marker placed on or around, labeled '{body_part}'.",
                data=body_part_data,
                unit="px",
                reference_frame="(0,0) corresponds to the upper left corner when using width by height convention.",
                timestamps=reused_timestamps or timestamps,
                confidence=np.array(dlc_data[f"{body_part}_likelihood"]),
            )
            all_pose_estimation_series.append(pose_estimation_series)

            reused_timestamps = all_pose_estimation_series[0]  # A trick for linking timestamps across series

        pose_estimation_kwargs = dict(
            name=f"PoseEstimation{left_right_or_body.capitalize()}Camera",
            pose_estimation_series=all_pose_estimation_series,
            description="Estimated positions of body parts using DeepLabCut.",
            source_software="DeepLabCut",
            nodes=body_parts,
        )
        pose_estimation_container = PoseEstimation(**pose_estimation_kwargs)

        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        camera_module.add(pose_estimation_container)

import re
from typing import Optional

import numpy as np
from ndx_pose import PoseEstimation, PoseEstimationSeries, Skeleton, Skeletons
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

        camera_view = re.search(r'(left|right|body)Camera*', self.camera_name).group(1)
        camera_view = camera_view.capitalize()  # To SnakeCase
        # left_right_or_body = self.camera_name[:5].rstrip("C")
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
                confidence_definition="Likelihood output from DeepLabCut neural network.",
            )
            all_pose_estimation_series.append(pose_estimation_series)

            reused_timestamps = all_pose_estimation_series[0]  # A trick for linking timestamps across series

        # Create skeleton that defines the body parts without edges
        skeleton_name = f"{camera_view}_camera_skeleton"

        skeleton = Skeleton(
            name=skeleton_name,
            nodes=body_parts,
        )

        # Store the skeleton in a Skeletons container
        skeletons = Skeletons(skeletons=[skeleton])

        # Create device for the camera
        camera_name_snake_case = f"{camera_view}_camera"
        camera_device = nwbfile.create_device(
            name=camera_name_snake_case,
            description=f"{camera_view} camera for recording behavior",
        )

        pose_estimation_kwargs = dict(
            name=f"PoseEstimation{camera_view.capitalize()}Camera",
            pose_estimation_series=all_pose_estimation_series,
            description="Estimated positions of body parts using DeepLabCut.",
            source_software="DeepLabCut",
            skeleton=skeleton,  # link to the skeleton object
            devices=[camera_device],
        )
        pose_estimation_container = PoseEstimation(**pose_estimation_kwargs)
        
        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        camera_module.add(skeletons)
        camera_module.add(pose_estimation_container)
from datetime import datetime
from typing import Optional

import numpy as np
from ndx_pose import PoseEstimation, PoseEstimationSeries
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile
from pynwb.image import ImageSeries


class IblPoseEstimationInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, camera_name: str, include_video: bool, include_pose: bool):
        self.one = one
        self.session = session
        self.camera_name = camera_name
        self.include_video = include_video
        self.include_pose = include_pose

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, revision: Optional[str] = None):
        if revision is None:
            session_files = self.one.list_datasets(eid=self.session, filename=f"*{self.camera_name}.dlc*")
            revision_datetime_format = "%Y-%m-%d"
            revisions = [
                datetime.strptime(session_file.split("#")[1], revision_datetime_format)
                for session_file in session_files
                if "#" in session_file
            ]

            if any(revisions):
                most_recent = max(revisions)
                revision = most_recent.strftime("%Y-%m-%d")

        camera_data = self.one.load_object(id=self.session, obj=self.camera_name, collection="alf", revision=revision)
        dlc_data = camera_data["dlc"]
        timestamps = camera_data["times"]
        number_of_frames = len(timestamps)
        body_parts = list(
            set(field.replace("_x", "").replace("_y", "").replace("_likelihood", "") for field in dlc_data.keys())
        )

        left_right_or_body = self.camera_name[:5].rstrip("C")
        reused_timestamps = None
        all_pose_estimation_series = list()
        if self.include_pose:
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
            behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="Processed behavioral data.")
            behavior_module.add(pose_estimation_container)

        if self.include_video and self.one.list_datasets(
            eid=self.session, filename=f"raw_video_data/*{self.camera_name}*"
        ):
            all_pose_estimation_series.append(pose_estimation_series)

            reused_timestamps = all_pose_estimation_series[0]  # A trick for linking timestamps across series

            original_video_file = self.one.load_dataset(
                id=self.session, dataset=f"raw_video_data/*{self.camera_name}*", download_only=True
            )
            image_series = ImageSeries(
                name=f"OriginalVideo{left_right_or_body.capitalize()}Camera",
                description="The original video each pose was estimated from.",
                unit="n.a.",
                external_file=[str(original_video_file)],
                format="external",
                timestamps=reused_timestamps or timestamps,
            )
            nwbfile.add_acquisition(image_series)

from datetime import datetime

import numpy as np
from ndx_pose import PoseEstimation, PoseEstimationSeries
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import H5DataIO


class AlfDlcInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, camera_name: str):
        self.one = one
        self.session = session
        self.camera_name = camera_name

    def run_conversion(self, nwbfile, metadata: dict):
        original_video_file = self.one.list_datasets(eid=self.session, filename=f"raw_video_data/*{self.camera_name}*")

        # Sometimes the DLC data has been revised, possibly multiple times
        # Always use the most recent revision available
        session_files = self.one.list_datasets(eid=self.session, filename=f"*{self.camera_name}.dlc*")
        revision_datetime_format = "%Y-%m-%d"
        revisions = [
            datetime.strptime(session_file.split("#")[1], revision_datetime_format)
            for session_file in session_files
            if "#" in session_file
        ]
        revision = None
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

        camera_name_snake_case = self.camera_name[:5].rstrip("C") + "_camera"
        reused_timestamps = None
        all_pose_estimation_series = list()
        for body_part in body_parts:
            body_part_name = f"{body_part}_{camera_name_snake_case}"

            body_part_data = np.empty(shape=(number_of_frames, 2))
            body_part_data[:, 0] = dlc_data[f"{body_part}_x"]
            body_part_data[:, 1] = dlc_data[f"{body_part}_y"]

            pose_estimation_series = PoseEstimationSeries(
                name=body_part_name,
                # description='Marker placed around fingers of front left paw.',  # TODO
                data=H5DataIO(body_part_data, compression=True),
                unit="px",
                reference_frame="(0,0) corresponds to the upper left corner when using width by height convention.",
                timestamps=reused_timestamps or H5DataIO(timestamps, compression=True),
                confidence=np.array(dlc_data[f"{body_part}_likelihood"]),
                # confidence_definition='Softmax output of the deep neural network.',  # TODO
            )
            all_pose_estimation_series.append(pose_estimation_series)

            reused_timestamps = all_pose_estimation_series[0]  # trick for linking timestamps across series

        pose_estimation_container = PoseEstimation(
            name=f"PoseEstimation{self.camera_name.capitalize()}",
            pose_estimation_series=all_pose_estimation_series,
            description="Estimated positions of body parts using DeepLabCut.",
            original_videos=original_video_file if any(original_video_file) else None,
            # dimensions=np.array([[640, 480], [1024, 768]], dtype='uint8'),  # TODO
            # scorer='DLC_resnet50_openfieldOct30shuffle1_1600',  # TODO
            source_software="DeepLabCut",
            # source_software_version='2.2b8',  # TODO?
            nodes=body_parts,
            # edges=np.array([[0, 1]], dtype='uint8'),  # TODO?
        )

        behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="Processed behavioral data.")
        behavior_module.add(pose_estimation_container)

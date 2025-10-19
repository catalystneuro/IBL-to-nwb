import logging
import re
from typing import Optional

import numpy as np
from brainbox.io.one import SessionLoader
from ndx_pose import PoseEstimation, PoseEstimationSeries, Skeleton, Skeletons
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile
from one.alf.exceptions import ALFObjectNotFound


class IblPoseEstimationInterface(BaseDataInterface):
    def __init__(
        self,
        one: ONE,
        session: str,
        camera_name: str,
        revision: Optional[str] = None,
        tracker: str = 'lightningPose',
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
        self.tracker = tracker

        self.revision = revision
        if self.revision is None:
            self.revision = one.list_revisions(session)[-1]

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict) -> None:
        session_loader = SessionLoader(one=self.one, eid=self.session, revision=self.revision)
        camera_view = re.search(r"(left|right|body)Camera*", self.camera_name).group(1)
        tracker_to_use = self.tracker

        try:
            session_loader.load_pose(tracker=tracker_to_use, views=[camera_view])
        except KeyError as exc:
            if tracker_to_use != "lightningPose":
                raise exc

            # Attempt to repair LightningPose cache first
            lightning_filename = f"_ibl_{camera_view}Camera.lightningPose.pqt"
            lightning_candidates = []
            try:
                lightning_candidates.extend(self.one.list_datasets(self.session, filename=lightning_filename))
                if self.revision:
                    lightning_candidates.extend(
                        self.one.list_datasets(self.session, filename=lightning_filename, revision=self.revision)
                    )
            except Exception:
                lightning_candidates = []

            lightning_candidates = sorted(set(lightning_candidates))
            lightning_success = False
            if lightning_candidates:
                dataset_path = lightning_candidates[0]
                try:
                    self.one.load_dataset(
                        self.session,
                        dataset=dataset_path,
                        download_only=True,
                    )
                    session_loader = SessionLoader(one=self.one, eid=self.session, revision=self.revision)
                    session_loader.load_pose(tracker=tracker_to_use, views=[camera_view])
                    lightning_success = True
                except ALFObjectNotFound:
                    lightning_success = False

            if not lightning_success:
                # Fall back to DLC if available
                dlc_filename = f"_ibl_{camera_view}Camera.dlc.pqt"
                dlc_candidates = []
                try:
                    dlc_candidates.extend(self.one.list_datasets(self.session, filename=dlc_filename))
                    if self.revision:
                        dlc_candidates.extend(
                            self.one.list_datasets(self.session, filename=dlc_filename, revision=self.revision)
                        )
                except Exception:
                    dlc_candidates = []

                dlc_candidates = sorted(set(dlc_candidates))
                if not dlc_candidates:
                    raise FileNotFoundError(
                        "Pose estimation datasets missing for camera '%s' (session %s) -- "
                        "neither LightningPose nor DLC available." % (self.camera_name, self.session)
                    )

                dataset_path = dlc_candidates[0]
                try:
                    self.one.load_dataset(
                        self.session,
                        dataset=dataset_path,
                        download_only=True,
                    )
                except ALFObjectNotFound:
                    raise FileNotFoundError(
                        "Pose estimation dataset '%s' (tracker=dlc, session=%s) is unavailable; aborting conversion." % (
                            dataset_path,
                            self.session,
                        )
                    )

                tracker_to_use = "dlc"
                session_loader = SessionLoader(one=self.one, eid=self.session, revision=self.revision)
                session_loader.load_pose(tracker=tracker_to_use, views=[camera_view])

                logging.warning(
                    "Falling back to DLC pose estimates for %s (session %s); LightningPose data not found.",
                    self.camera_name,
                    self.session,
                )

        if self.camera_name not in session_loader.pose:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' not found in session '{self.session}'"
            )

        pose_data = session_loader.pose[self.camera_name]

        if "times" not in pose_data or pose_data["times"].empty:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' in session '{self.session}' contains no timestamps"
            )

        timestamps = pose_data["times"].values
        pose_data = pose_data.drop("times", axis=1)
        number_of_frames = len(timestamps)

        if number_of_frames == 0:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' in session '{self.session}' contains no frames"
            )


        body_parts = []
        for column in pose_data.columns:
            if not column.endswith('_x'):
                continue
            base_name = column[:-2]
            if (f'{base_name}_y' in pose_data.columns) and (f'{base_name}_likelihood' in pose_data.columns):
                body_parts.append(base_name)
        body_parts = sorted(set(body_parts))

        if not body_parts:
            raise RuntimeError(
                f"Pose data for camera '{self.camera_name}' in session '{self.session}' has no labeled body parts with x/y/likelihood columns"
            )
        # TODO: Discuss with team how to handle Lightning Pose ensemble/uncertainty data
        # Lightning Pose provides additional data beyond basic x,y,likelihood:
        # - ensemble_median: more robust predictions from multiple models
        # - ensemble_variance: disagreement between models (quality measure)
        # - posterior_variance: Bayesian uncertainty estimates
        # Currently filtering these out to maintain compatibility with existing NWB structure.
        # Consider: separate data objects, metadata fields, or extended pose schema.

        # Filter out ensemble and posterior columns, extract body parts
        # body_parts = set()
        # for field in pose_data.keys():
        #     # Skip ensemble and posterior variance columns
        #     if any(suffix in field for suffix in ['_ens_', '_posterior_']):
        #         continue
        #     # Extract body part name from basic x, y, likelihood columns
        #     if field.endswith('_x') or field.endswith('_y') or field.endswith('_likelihood'):
        #         body_part = field.replace('_x', '').replace('_y', '').replace('_likelihood', '')
        #         body_parts.add(body_part)

        body_parts = list(body_parts)
        skeleton_name = f"Skeleton{camera_view.capitalize()}Camera"
        skeletons_container_name = f"Skeletons{camera_view.capitalize()}Camera"

        reused_timestamps = None
        all_pose_estimation_series = list()

        for body_part in body_parts:
            required_columns = [f"{body_part}_x", f"{body_part}_y", f"{body_part}_likelihood"]
            for column in required_columns:
                if column not in pose_data:
                    raise RuntimeError(
                        f"Pose data for camera '{self.camera_name}' in session '{self.session}' is missing column '{column}'"
                    )

            body_part_data = np.empty(shape=(number_of_frames, 2))
            body_part_data[:, 0] = pose_data[f"{body_part}_x"]
            body_part_data[:, 1] = pose_data[f"{body_part}_y"]

            pose_estimation_series = PoseEstimationSeries(
                name=body_part,
                description=f"Marker placed on or around, labeled '{body_part}'.",
                data=body_part_data,
                unit="px",
                reference_frame="(0,0) corresponds to the upper left corner when using width by height convention.",
                timestamps=reused_timestamps or timestamps,
                confidence=np.array(pose_data[f"{body_part}_likelihood"]),

            )
            all_pose_estimation_series.append(pose_estimation_series)

            reused_timestamps = all_pose_estimation_series[0]  # A trick for linking timestamps across series

        skeleton_kwargs = dict(
            name=skeleton_name,
            nodes=body_parts,
            edges=np.empty(shape=(0, 2), dtype="uint8"),
        )
        if nwbfile.subject is not None:
            skeleton_kwargs["subject"] = nwbfile.subject
        skeleton = Skeleton(**skeleton_kwargs)

        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        if skeletons_container_name in camera_module.data_interfaces:
            skeletons_container = camera_module.data_interfaces[skeletons_container_name]
            if skeleton_name in skeletons_container.skeletons:
                skeleton = skeletons_container.skeletons[skeleton_name]
            else:
                skeletons_container.add_skeletons(skeleton)
                skeleton = skeletons_container.skeletons[skeleton_name]
        else:
            skeletons_container = Skeletons(name=skeletons_container_name, skeletons=[skeleton])
            camera_module.add(skeletons_container)

        pose_estimation_kwargs = dict(
            name=f"PoseEstimation{camera_view.capitalize()}Camera",
            pose_estimation_series=all_pose_estimation_series,
            description="Estimated positions of body parts using DeepLabCut.",
            source_software="DeepLabCut",
            skeleton=skeleton,
        )
        pose_estimation_container = PoseEstimation(**pose_estimation_kwargs)

        camera_module.add(pose_estimation_container)

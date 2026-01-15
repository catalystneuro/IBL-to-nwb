"""NWB pose estimation video overlay widget."""

import pathlib
from typing import Optional

import anywidget
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import traitlets


class NWBPoseEstimationWidget(anywidget.AnyWidget):
    """Video player with pose estimation overlay and camera selector.

    Overlays DeepLabCut keypoints on streaming video with support for
    multiple cameras and keypoint visibility toggles.

    Parameters
    ----------
    nwbfile : pynwb.NWBFile
        NWB file containing pose estimation in processing['pose_estimation']
    video_urls : dict
        Mapping of video names to S3/HTTP URLs.
    camera_to_video_key : dict
        Mapping from pose estimation camera names (e.g., 'LeftCamera') to
        video_urls keys (e.g., 'VideoLeftCamera').
        Example: {"LeftCamera": "VideoLeftCamera", "BodyCamera": "VideoBodyCamera"}
    keypoint_colors : str or dict, default 'tab10'
        Either a matplotlib colormap name (e.g., 'tab10', 'Set1', 'Paired') for
        automatic color assignment, or a dict mapping keypoint names to hex colors
        (e.g., {'LeftPaw': '#FF0000', 'RightPaw': '#00FF00'}).
    default_camera : str, optional
        Camera to display initially. Falls back to first available if not found.

    Example
    -------
    >>> # Using a colormap (default)
    >>> widget = NWBPoseEstimationWidget(
    ...     nwbfile=nwbfile_processed,
    ...     video_urls=video_s3_urls,
    ...     camera_to_video_key={
    ...         "LeftCamera": "VideoLeftCamera",
    ...         "BodyCamera": "VideoBodyCamera",
    ...         "RightCamera": "VideoRightCamera",
    ...     },
    ... )

    >>> # Using custom colors for specific keypoints
    >>> widget = NWBPoseEstimationWidget(
    ...     nwbfile=nwbfile_processed,
    ...     video_urls=video_s3_urls,
    ...     camera_to_video_key={...},
    ...     keypoint_colors={'LeftPaw': '#FF0000', 'RightPaw': '#00FF00'},
    ... )
    """

    selected_camera = traitlets.Unicode("").tag(sync=True)
    available_cameras = traitlets.List([]).tag(sync=True)
    camera_to_video = traitlets.Dict({}).tag(sync=True)

    # Keypoint metadata (colors, labels)
    keypoint_metadata = traitlets.Dict({}).tag(sync=True)

    # Pose data as JSON - simple and reliable
    # TODO: For better performance with large datasets, consider binary transfer
    # using traitlets.Bytes and Float32Array views in JavaScript. See anywidget
    # patterns by Trevor Manz for reference implementation.
    pose_coordinates = traitlets.Dict({}).tag(sync=True)  # {keypoint_name: [[x, y], ...]}
    timestamps = traitlets.List([]).tag(sync=True)

    show_labels = traitlets.Bool(True).tag(sync=True)
    visible_keypoints = traitlets.Dict({}).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "nwb_pose_widget.js"

    def __init__(
        self,
        nwbfile,
        video_urls: dict[str, str],
        camera_to_video_key: dict[str, str],
        keypoint_colors: str | dict[str, str] = "tab10",
        default_camera: Optional[str] = None,
        **kwargs,
    ):
        # Parse keypoint_colors: either a colormap name (str) or explicit color dict
        if isinstance(keypoint_colors, str):
            # It's a colormap name - will assign colors automatically
            colormap_name = keypoint_colors
            custom_colors = {}
        else:
            # It's a dict of explicit colors - use tab10 for any missing keypoints
            colormap_name = "tab10"
            custom_colors = keypoint_colors

        # Get pose estimation container
        if "pose_estimation" not in nwbfile.processing:
            raise ValueError("NWB file does not contain pose_estimation processing module")
        pose_estimation = nwbfile.processing["pose_estimation"]

        # Find available cameras (those with both pose data AND video)
        # Preserve order from camera_to_video_key so first entry is default
        available_pose_cameras = set(pose_estimation.data_interfaces.keys())
        camera_to_video = {}
        available_cameras = []

        for camera_name in camera_to_video_key.keys():
            if camera_name not in available_pose_cameras:
                continue
            video_key = camera_to_video_key[camera_name]
            video_url = video_urls.get(video_key, "")
            if video_url:
                camera_to_video[camera_name] = video_url
                available_cameras.append(camera_name)

        if not available_cameras:
            raise ValueError(
                f"No cameras have both pose data and video URLs. "
                f"Pose cameras: {available_pose_cameras}, "
                f"Video keys: {list(video_urls.keys())}"
            )

        # Select default camera
        if default_camera and default_camera in available_cameras:
            selected_camera = default_camera
        else:
            selected_camera = available_cameras[0]

        # Get colormap for automatic color assignment
        cmap = plt.get_cmap(colormap_name)

        # Create pose loader closure
        def load_camera_pose_data(camera_name: str) -> dict:
            """Load pose data for a single camera.

            Returns a dict with:
            - keypoint_metadata: {name: {color, label}}
            - pose_coordinates: {name: [[x, y], ...]} as JSON-serializable lists
            - timestamps: [t0, t1, ...] as JSON-serializable list
            """
            camera_pose = pose_estimation[camera_name]

            keypoint_names = list(camera_pose.pose_estimation_series.keys())
            n_kp = len(keypoint_names)

            metadata = {}
            coordinates = {}
            timestamps = None

            for idx, (series_name, series) in enumerate(camera_pose.pose_estimation_series.items()):
                short_name = series_name.replace("PoseEstimationSeries", "")

                # Get coordinates - convert NaN to None for JSON compatibility
                data = series.data[:]  # shape: (n_frames, 2)
                # Convert to list, replacing NaN with None
                coords_list = []
                for x, y in data:
                    if np.isnan(x) or np.isnan(y):
                        coords_list.append(None)
                    else:
                        coords_list.append([float(x), float(y)])
                coordinates[short_name] = coords_list

                if timestamps is None:
                    timestamps = series.timestamps[:].tolist()

                # Assign color from custom dict or colormap
                if short_name in custom_colors:
                    color = custom_colors[short_name]
                else:
                    if hasattr(cmap, "N") and cmap.N < 256:
                        rgba = cmap(idx % cmap.N)
                    else:
                        rgba = cmap(idx / max(n_kp - 1, 1))
                    color = mcolors.to_hex(rgba)

                metadata[short_name] = {"color": color, "label": short_name}

            return {
                "keypoint_metadata": metadata,
                "pose_coordinates": coordinates,
                "timestamps": timestamps,
            }

        # Initialize parent with computed values
        super().__init__(
            selected_camera=selected_camera,
            available_cameras=available_cameras,
            camera_to_video=camera_to_video,
            **kwargs,
        )

        # Set up pose loading
        self._camera_data_cache = {}
        self._pose_loader = load_camera_pose_data

        # Load initial camera data
        self._load_camera(selected_camera)

        # Watch for camera changes
        self.observe(self._on_camera_change, names=["selected_camera"])

    def _load_camera(self, camera_name):
        """Load data for a camera (with caching)."""
        if camera_name not in self._camera_data_cache:
            print(f"Loading pose data for {camera_name}...")
            data = self._pose_loader(camera_name)
            self._camera_data_cache[camera_name] = data
            n_keypoints = len(data["keypoint_metadata"])
            n_frames = len(data["timestamps"])
            print(f"  Loaded {n_keypoints} keypoints, {n_frames} frames")
        else:
            data = self._camera_data_cache[camera_name]
            print(f"Using cached data for {camera_name}")

        # Update all traitlets with new data
        self.keypoint_metadata = data["keypoint_metadata"]
        self.pose_coordinates = data["pose_coordinates"]
        self.timestamps = data["timestamps"]

        # Initialize visibility for new keypoints
        new_visible = {**self.visible_keypoints}
        for name in data["keypoint_metadata"].keys():
            if name not in new_visible:
                new_visible[name] = True
        self.visible_keypoints = new_visible

    def _on_camera_change(self, change):
        """Called when selected_camera changes."""
        self._load_camera(change["new"])

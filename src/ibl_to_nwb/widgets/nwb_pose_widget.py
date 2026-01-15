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

    # Keypoint metadata (colors, labels) - small, JSON is fine
    keypoint_metadata = traitlets.Dict({}).tag(sync=True)

    # Binary coordinate data - using bytes for efficient transfer
    # Why binary instead of JSON? (Inspired by Trevor Manz's anywidget patterns)
    #
    # Pose data can have 100k+ frames × 11 keypoints × 2 coords = 2.2M floats
    # - JSON serialization: ~20 bytes/float = 44MB, plus slow Python list iteration
    # - Binary Float32: 4 bytes/float = 8.8MB, numpy handles conversion in C
    #
    # This 5x size reduction + faster serialization makes camera switching snappy.
    # JavaScript accesses the data via Float32Array view - zero parsing overhead.
    # NaN values are preserved in IEEE 754 float format and checked with isNaN() in JS.
    pose_coordinates = traitlets.Bytes(b"").tag(sync=True)
    timestamps_binary = traitlets.Bytes(b"").tag(sync=True)

    # Shape info needed to reconstruct arrays in JavaScript
    n_frames = traitlets.Int(0).tag(sync=True)
    n_keypoints = traitlets.Int(0).tag(sync=True)
    keypoint_order = traitlets.List([]).tag(sync=True)

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
            - keypoint_metadata: {name: {color, label}} for JSON transfer
            - pose_coordinates: bytes of Float32 array [n_keypoints, n_frames, 2]
            - timestamps_binary: bytes of Float64 array [n_frames]
            - n_frames, n_keypoints, keypoint_order: shape info for JS reconstruction
            """
            camera_pose = pose_estimation[camera_name]

            keypoint_names = list(camera_pose.pose_estimation_series.keys())
            n_kp = len(keypoint_names)

            # Build metadata (small, JSON is fine) and collect coordinate arrays
            metadata = {}
            coord_arrays = []
            timestamps = None

            for idx, (series_name, series) in enumerate(camera_pose.pose_estimation_series.items()):
                short_name = series_name.replace("PoseEstimationSeries", "")

                # Get coordinates as float32 - keeps NaN values intact
                # NaN is valid in IEEE 754 and will be checked with isNaN() in JavaScript
                data = series.data[:].astype(np.float32)  # shape: (n_frames, 2)
                coord_arrays.append(data)

                if timestamps is None:
                    # Float64 for timestamps to preserve precision
                    timestamps = series.timestamps[:].astype(np.float64)

                # Assign color from custom dict or colormap
                if short_name in custom_colors:
                    color = custom_colors[short_name]
                else:
                    # For listed colormaps (tab10, Set1, etc.), cycle through colors
                    # For continuous colormaps, sample evenly across the range
                    if hasattr(cmap, "N") and cmap.N < 256:
                        rgba = cmap(idx % cmap.N)
                    else:
                        rgba = cmap(idx / max(n_kp - 1, 1))
                    color = mcolors.to_hex(rgba)

                metadata[short_name] = {"color": color, "label": short_name}

            # Stack all coordinates into single array: shape (n_keypoints, n_frames, 2)
            # This layout allows efficient indexing by keypoint then frame in JavaScript
            all_coords = np.stack(coord_arrays, axis=0)
            n_frames = all_coords.shape[1]

            # Convert to bytes - numpy's tobytes() is fast (happens in C)
            # Using little-endian which matches most systems and JavaScript's DataView default
            coords_bytes = all_coords.astype("<f4").tobytes()  # <f4 = little-endian float32
            timestamps_bytes = timestamps.astype("<f8").tobytes()  # <f8 = little-endian float64

            # Short names in order (matches coord_arrays stacking order)
            keypoint_order = [
                name.replace("PoseEstimationSeries", "")
                for name in keypoint_names
            ]

            return {
                "keypoint_metadata": metadata,
                "pose_coordinates": coords_bytes,
                "timestamps_binary": timestamps_bytes,
                "n_frames": n_frames,
                "n_keypoints": n_kp,
                "keypoint_order": keypoint_order,
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
            print(f"  Loaded {data['n_keypoints']} keypoints, {data['n_frames']} frames")
            print(f"  Binary size: {len(data['pose_coordinates']) / 1024:.1f} KB coordinates")
        else:
            data = self._camera_data_cache[camera_name]
            print(f"Using cached data for {camera_name}")

        # Update all traitlets with new data
        self.keypoint_metadata = data["keypoint_metadata"]
        self.pose_coordinates = data["pose_coordinates"]
        self.timestamps_binary = data["timestamps_binary"]
        self.n_frames = data["n_frames"]
        self.n_keypoints = data["n_keypoints"]
        self.keypoint_order = data["keypoint_order"]

        # Initialize visibility for new keypoints
        new_visible = {**self.visible_keypoints}
        for name in data["keypoint_metadata"].keys():
            if name not in new_visible:
                new_visible[name] = True
        self.visible_keypoints = new_visible

    def _on_camera_change(self, change):
        """Called when selected_camera changes."""
        self._load_camera(change["new"])

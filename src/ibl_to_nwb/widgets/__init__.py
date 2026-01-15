"""
anywidget-based visualization widgets for IBL NWB data.

This module provides interactive Jupyter widgets for visualizing
video and pose estimation data from IBL experiments.
"""

from ibl_to_nwb.widgets.nwb_pose_widget import NWBPoseEstimationWidget
from ibl_to_nwb.widgets.nwb_video_widget import NWBFileVideoPlayer

__all__ = [
    "NWBFileVideoPlayer",
    "NWBPoseEstimationWidget",
]

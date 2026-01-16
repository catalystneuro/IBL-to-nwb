"""NWB video player widget with configurable grid layout."""

import pathlib
from typing import Optional

import anywidget
import traitlets

# Default grid layout: single row with Left, Body, Right cameras
DEFAULT_GRID_LAYOUT = [["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]


class NWBFileVideoPlayer(anywidget.AnyWidget):
    """Display videos in a configurable grid layout with synchronized playback.

    Parameters
    ----------
    nwbfile_raw : pynwb.NWBFile
        Raw NWB file containing video ImageSeries in acquisition
    dandi_asset : dandi.dandiapi.RemoteBlobAsset
        Asset object for the raw NWB file. The dandiset is derived from
        the asset's client and dandiset_id attributes.
    grid_layout : list of list of str, optional
        Grid layout specifying which videos to display and how to arrange them.
        Each inner list represents a row, and each string is a video series name.
        Videos not found in the NWB file are silently skipped.
        Default: [["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]

    Example
    -------
    Default layout (single row):

    >>> widget = NWBFileVideoPlayer(nwbfile_raw, dandi_asset)

    Custom 2x2 grid:

    >>> widget = NWBFileVideoPlayer(
    ...     nwbfile_raw, dandi_asset,
    ...     grid_layout=[
    ...         ["VideoLeftCamera", "VideoRightCamera"],
    ...         ["VideoBodyCamera"],
    ...     ]
    ... )

    Single video:

    >>> widget = NWBFileVideoPlayer(
    ...     nwbfile_raw, dandi_asset,
    ...     grid_layout=[["VideoLeftCamera"]]
    ... )
    """

    video_urls = traitlets.Dict({}).tag(sync=True)
    grid_layout = traitlets.List([]).tag(sync=True)
    # Timestamps for each video: {video_name: [t0, t1, ...]}
    # Used to display NWB session time instead of video-relative time
    video_timestamps = traitlets.Dict({}).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "nwb_video_widget.js"
    _css = pathlib.Path(__file__).parent / "nwb_video_widget.css"

    def __init__(
        self,
        nwbfile_raw,
        dandi_asset,
        grid_layout: Optional[list[list[str]]] = None,
        **kwargs,
    ):
        video_urls = self.get_video_urls_from_dandi(nwbfile_raw, dandi_asset)
        video_timestamps = self.get_video_timestamps(nwbfile_raw)
        layout = grid_layout if grid_layout is not None else DEFAULT_GRID_LAYOUT
        super().__init__(
            video_urls=video_urls,
            grid_layout=layout,
            video_timestamps=video_timestamps,
            **kwargs,
        )

    @staticmethod
    def get_video_urls_from_dandi(nwbfile_raw, dandi_asset) -> dict[str, str]:
        """Extract video S3 URLs from raw NWB file using DANDI API.

        Videos in NWB files are stored as ImageSeries with external_file paths.
        This function finds all ImageSeries with external files and resolves
        their relative paths to full S3 URLs using the DANDI API.

        Parameters
        ----------
        nwbfile_raw : pynwb.NWBFile
            Raw NWB file containing video ImageSeries in acquisition
        dandi_asset : dandi.dandiapi.RemoteBlobAsset
            Asset object for the raw NWB file. The dandiset is derived from
            the asset's client and dandiset_id attributes.

        Returns
        -------
        dict
            Mapping of video names to S3 URLs.
            Keys: 'VideoLeftCamera', 'VideoBodyCamera', 'VideoRightCamera'

        Example
        -------
        >>> from dandi.dandiapi import DandiAPIClient
        >>> client = DandiAPIClient()
        >>> dandiset = client.get_dandiset("000409")
        >>> dandi_asset = dandiset.get_asset_by_path("sub-.../sub-..._raw.nwb")
        >>> video_urls = NWBFileVideoPlayer.get_video_urls_from_dandi(
        ...     nwbfile_raw, dandi_asset
        ... )
        """
        from pathlib import Path

        from pynwb.image import ImageSeries

        # Derive dandiset from dandi_asset
        dandiset = dandi_asset.client.get_dandiset(dandi_asset.dandiset_id)

        nwb_parent = Path(dandi_asset.path).parent
        video_urls = {}

        for name, obj in nwbfile_raw.acquisition.items():
            # Videos are stored as ImageSeries with external_file attribute
            if isinstance(obj, ImageSeries) and obj.external_file is not None:
                relative_path = obj.external_file[0].lstrip("./")
                full_path = str(nwb_parent / relative_path)

                video_asset = dandiset.get_asset_by_path(full_path)
                if video_asset is not None:
                    video_urls[name] = video_asset.get_content_url(
                        follow_redirects=1, strip_query=True
                    )

        return video_urls

    @staticmethod
    def get_video_timestamps(nwbfile_raw) -> dict[str, list[float]]:
        """Extract video timestamps from NWB file ImageSeries.

        Parameters
        ----------
        nwbfile_raw : pynwb.NWBFile
            Raw NWB file containing video ImageSeries in acquisition

        Returns
        -------
        dict
            Mapping of video names to timestamp arrays.
            Each array contains the NWB session timestamps for each frame.
        """
        from pynwb.image import ImageSeries

        video_timestamps = {}

        for name, obj in nwbfile_raw.acquisition.items():
            if isinstance(obj, ImageSeries) and obj.external_file is not None:
                # Get timestamps - could be explicit or computed from starting_time + rate
                if obj.timestamps is not None:
                    timestamps = obj.timestamps[:]
                elif obj.starting_time is not None and obj.rate is not None:
                    # Compute timestamps from starting_time and rate
                    n_frames = len(obj.external_file) if hasattr(obj, 'dimension') else 1
                    # For external files, we may not know frame count upfront
                    # Use a reasonable estimate or just store start/rate info
                    timestamps = [obj.starting_time]
                else:
                    timestamps = [0.0]

                video_timestamps[name] = [float(t) for t in timestamps]

        return video_timestamps

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
    dandiset : dandi.dandiapi.RemoteDandiset
        DANDI dandiset object (from DandiAPIClient)
    raw_asset : dandi.dandiapi.RemoteAsset
        Asset object for the raw NWB file
    grid_layout : list of list of str, optional
        Grid layout specifying which videos to display and how to arrange them.
        Each inner list represents a row, and each string is a video series name.
        Videos not found in the NWB file are silently skipped.
        Default: [["VideoLeftCamera", "VideoBodyCamera", "VideoRightCamera"]]

    Example
    -------
    Default layout (single row):

    >>> widget = NWBFileVideoPlayer(nwbfile_raw, dandiset, raw_asset)

    Custom 2x2 grid:

    >>> widget = NWBFileVideoPlayer(
    ...     nwbfile_raw, dandiset, raw_asset,
    ...     grid_layout=[
    ...         ["VideoLeftCamera", "VideoRightCamera"],
    ...         ["VideoBodyCamera"],
    ...     ]
    ... )

    Single video:

    >>> widget = NWBFileVideoPlayer(
    ...     nwbfile_raw, dandiset, raw_asset,
    ...     grid_layout=[["VideoLeftCamera"]]
    ... )
    """

    video_urls = traitlets.Dict({}).tag(sync=True)
    grid_layout = traitlets.List([]).tag(sync=True)

    _esm = pathlib.Path(__file__).parent / "nwb_video_widget.js"

    def __init__(
        self,
        nwbfile_raw,
        dandiset,
        raw_asset,
        grid_layout: Optional[list[list[str]]] = None,
        **kwargs,
    ):
        video_urls = self.get_video_urls_from_dandi(nwbfile_raw, dandiset, raw_asset)
        layout = grid_layout if grid_layout is not None else DEFAULT_GRID_LAYOUT
        super().__init__(video_urls=video_urls, grid_layout=layout, **kwargs)

    @staticmethod
    def get_video_urls_from_dandi(nwbfile_raw, dandiset, raw_asset) -> dict[str, str]:
        """Extract video S3 URLs from raw NWB file using DANDI API.

        Videos in NWB files are stored as ImageSeries with external_file paths.
        This function finds all ImageSeries with external files and resolves
        their relative paths to full S3 URLs using the DANDI API.

        Parameters
        ----------
        nwbfile_raw : pynwb.NWBFile
            Raw NWB file containing video ImageSeries in acquisition
        dandiset : dandi.dandiapi.RemoteDandiset
            DANDI dandiset object (from DandiAPIClient)
        raw_asset : dandi.dandiapi.RemoteAsset
            Asset object for the raw NWB file

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
        >>> raw_asset = dandiset.get_asset_by_path("sub-.../sub-..._raw.nwb")
        >>> video_urls = NWBFileVideoPlayer.get_video_urls_from_dandi(
        ...     nwbfile_raw, dandiset, raw_asset
        ... )
        """
        from pathlib import Path

        from pynwb.image import ImageSeries

        nwb_parent = Path(raw_asset.path).parent
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

from typing import Optional, Tuple, Iterable

from brainbox.io.spikeglx import Streamer
from hdmf.data_utils import GenericDataChunkIterator


class SpikeGLXStreamerDataChunkIterator(GenericDataChunkIterator):
    """DataChunkIterator for use on IBL SpikeGLX data."""

    def __init__(
        self,
        file_streamer: Streamer,
        buffer_gb: Optional[float] = None,
        buffer_shape: Optional[tuple] = None,
        chunk_mb: Optional[float] = None,
        chunk_shape: Optional[tuple] = None,
        display_progress: bool = False,
        progress_bar_options: Optional[dict] = None,
    ):
        """

        Parameters
        ----------
        file_streamer
        buffer_gb
        buffer_shape
        chunk_mb
        chunk_shape
        display_progress
        progress_bar_options
        """

        self.file_streamer = file_streamer

        super().__init__(
            buffer_gb=buffer_gb,
            buffer_shape=buffer_shape,
            chunk_mb=chunk_mb,
            chunk_shape=chunk_shape,
            display_progress=display_progress,
            progress_bar_options=progress_bar_options,
        )

    def _get_data(self, selection: Tuple[slice]) -> Iterable:
        return self.file_streamer[selection]

    def _get_dtype(self):
        return self.file_streamer.dtype

    def _get_maxshape(self):
        # remove the synching channels from the raw data
        num_channels = self.file_streamer.nc - self.file_streamer.nsync
        return (self.file_streamer.shape[0], num_channels)

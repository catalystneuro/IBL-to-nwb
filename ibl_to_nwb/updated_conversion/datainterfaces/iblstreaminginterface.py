from typing import Optional

from neuroconv.datainterfaces.ecephys.baselfpextractorinterface import (
    BaseLFPExtractorInterface,
)
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import (
    BaseRecordingExtractorInterface,
)
from one.api import ONE
from pydantic import DirectoryPath


class IblStreamingApInterface(BaseRecordingExtractorInterface):
    ExtractorName = "IblStreamingRecordingExtractor"

    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "ap" in stream_name]

    def __init__(self, **kwargs):
        self.session = kwargs["session"]
        self.stream_name = kwargs["stream_name"]
        super().__init__(**kwargs)

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        metadata["Ecephys"].update(
            ElectricalSeriesAp=dict(
                name="ElectricalSeriesAp", description="Raw acquisition traces for the high-pass (ap) SpikeGLX data."
            )
        )

        return metadata

    def run_conversion(self, **kwargs):
        # The buffer and chunk shapes must be set explicitly for good performance with the streaming
        # Otherwise, the default buffer/chunk shapes might re-request the same data packet multiple times
        chunk_frames = 100 if kwargs.get("stub_test", False) else 30_000
        buffer_frames = 100 if kwargs.get("stub_test", False) else 5 * 30_000
        kwargs.update(
            iterator_opts=dict(
                display_progress=True,
                chunk_shape=(chunk_frames, 16),  # ~1 MB
                buffer_shape=(buffer_frames, 384),  # 100 MB
                progress_bar_options=dict(desc=f"Converting stream '{self.stream_name}' session '{self.session}'..."),
            )
        )
        kwargs.update(es_key="ElectricalSeriesAp")
        super().run_conversion(**kwargs)


class IblStreamingLfInterface(IblStreamingApInterface):
    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "lf" in stream_name]

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        metadata["Ecephys"].update(
            ElectricalSeriesLf=dict(
                name="ElectricalSeriesLf", description="Raw acquisition traces for the high-pass (lf) SpikeGLX data."
            )
        )

        return metadata

    def run_conversion(self, **kwargs):
        # The buffer and chunk shapes must be set explicitly for good performance with the streaming
        # Otherwise, the default buffer/chunk shapes might re-request the same data packet multiple times
        chunk_frames = 100 if kwargs.get("stub_test", False) else 30_000
        buffer_frames = 100 if kwargs.get("stub_test", False) else 5 * 30_000
        kwargs.update(
            iterator_opts=dict(
                display_progress=True,
                chunk_shape=(chunk_frames, 16),  # ~1 MB
                buffer_shape=(buffer_frames, 384),  # 100 MB
                progress_bar_options=dict(desc=f"Converting stream '{self.stream_name}' session '{self.session}'..."),
            )
        )
        kwargs.update(es_key="ElectricalSerieslf")
        super().run_conversion(**kwargs)

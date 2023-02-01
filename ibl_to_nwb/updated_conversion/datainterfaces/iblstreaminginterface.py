from neuroconv.datainterfaces.ecephys.baselfpextractorinterface import (
    BaseLFPExtractorInterface,
)
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import (
    BaseRecordingExtractorInterface,
)


class IblStreamingRecordingInterface(BaseRecordingExtractorInterface):
    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "ap" in stream_name]

    def get_metadata(self):
        pass  # TODO: add descriptions for all those custom properties


class IblStreamingLfpInterface(BaseLFPExtractorInterface):
    ExtractorName = "IblStreamingRecordingExtractor"

    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "lf" in stream_name]

    def get_metadata():
        pass  # TODO: add descriptions for all those custom properties

from neuroconv.datainterfaces.ecephys.baselfpextractorinterface import (
    BaseLFPExtractorInterface,
)
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import (
    BaseRecordingExtractorInterface,
)


class IblStreamingRecordingInterface(BaseRecordingExtractorInterface):

    @classmethod
    def get_stream_names(cls):
        pass  # TODO: constrain to ap streams

    def get_metadata(self):
        pass  # TODO: add descriptions for all those custom properties


class IblStreamingLfpInterface(BaseLFPExtractorInterface):
    ExtractorName = "IblStreamingRecordingExtractor"

    @classmethod
    def get_stream_names(cls):
        pass  # TODO: constrain to lf streams

    def get_metadata():
        pass  # TODO: add descriptions for all those custom properties

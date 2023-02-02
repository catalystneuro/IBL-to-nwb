"""The interface for loadding spike sorted data via ONE access."""
from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import (
    BaseSortingExtractorInterface,
)

from .iblsortingextractor import IblSortingExtractor


class IblSortingInterface(BaseSortingExtractorInterface):
    Extractor = IblSortingExtractor

    # def get_metadata(self):
    #    pass  # TODO: add descriptions for all those custom properties

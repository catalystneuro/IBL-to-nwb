"""The interface for loading spike sorted data via ONE access."""
from pathlib import Path

from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import (
    BaseSortingExtractorInterface,
)
from neuroconv.utils import load_dict_from_file

from .iblsortingextractor import IblSortingExtractor


class IblSortingInterface(BaseSortingExtractorInterface):
    Extractor = IblSortingExtractor

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        ecephys_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "ecephys.yml")
        metadata.update(ecephys_metadata)

        if "allen_location" in self.sorting_extractor.get_property_keys():
            for column_name in ["allen_location", "beryl_location", "cosmos_location"]:
                metadata["Ecephys"]["UnitProperties"].extend(ecephys_metadata["Ecephys"][column_name])

        return metadata

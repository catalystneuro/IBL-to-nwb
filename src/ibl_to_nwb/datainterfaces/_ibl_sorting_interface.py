"""The interface for loading spike sorted data via ONE access."""

from pathlib import Path
from typing import Optional

from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import (
    BaseSortingExtractorInterface,
)
from neuroconv.utils import load_dict_from_file
from one.api import ONE

from ._ibl_sorting_extractor import IblSortingExtractor


class IblSortingInterface(BaseSortingExtractorInterface):
    Extractor = IblSortingExtractor

    def __init__(
        self,
        session: str,
        one: ONE,
        revision: Optional[str] = None,
    ):
        super().__init__(session=session, one=one, revision=revision)

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        ecephys_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "ecephys.yml")

        metadata.update(Ecephys=dict())
        metadata["Ecephys"].update(UnitProperties=ecephys_metadata["Ecephys"]["UnitProperties"])
        if "allen_location" in self.sorting_extractor.get_property_keys():
            for column_name in ["beryl_location", "cosmos_location"]:
                metadata["Ecephys"]["UnitProperties"].extend(
                    [column for column in ecephys_metadata["Ecephys"]["Electrodes"] if column["name"] == column_name]
                )

        return metadata

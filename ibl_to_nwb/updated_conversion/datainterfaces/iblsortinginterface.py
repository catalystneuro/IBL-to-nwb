"""The interface for loading spike sorted data via ONE access."""
from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import (
    BaseSortingExtractorInterface,
)

from .iblsortingextractor import IblSortingExtractor


class IblSortingInterface(BaseSortingExtractorInterface):
    Extractor = IblSortingExtractor

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        if "Ecephys" not in metadata:
            metadata.update(Ecephys=dict())

        metadata["Ecephys"].update(
            UnitProperties=[
                dict(
                    name="maximum_amplitude_channel",
                    description="Channel which has the largest amplitude for this cluster.",
                )
            ]
        )

        if "allen_location" in self.sorting_extractor.get_property_keys():
            metadata["Ecephys"]["UnitProperties"].extend(
                [
                    dict(
                        name="allen_location",
                        description="Brain region reference in the Allen Mouse Brain Atlas.",
                    ),
                    dict(
                        name="beryl_location",
                        description="Brain region reference in the IBL Beryll Atlas, which is a reduced mapping of functionally related regions from the Allen Mouse Brain Atlas.",
                    ),
                    dict(
                        name="cosmos_location",
                        description="Brain region reference in the IBL Cosmos Atlas, which is a reduced mapping of functionally related regions from the Allen Mouse Brain Atlas.",
                    ),
                ]
            )

        return metadata

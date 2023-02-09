"""The interface for loading spike sorted data via ONE access."""
from neuroconv.datainterfaces.ecephys.basesortingextractorinterface import (
    BaseSortingExtractorInterface,
)
from one.api import ONE
from brainbox.io.one import SpikeSortingLoader
from ibllib.atlas import AllenAtlas
from ibllib.atlas.regions import BrainRegions

from .iblsortingextractor import IblSortingExtractor


class IblSortingInterface(BaseSortingExtractorInterface):
    Extractor = IblSortingExtractor

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)
        atlas = AllenAtlas()
        brain_regions = BrainRegions()
        spike_sorting_loader = SpikeSortingLoader(
            eid=self.session, one=one, pname=self.stream_name.split(".")[0], atlas=atlas
        )
        _, clusters, channels = spike_sorting_loader.load_spike_sorting()

        self.has_histology = False
        if spike_sorting_loader.histology not in ["alf", "resolved"]:
            return
        self.has_histology = True

        unit_id_to_channel_id = clusters["channels"]
        channel_id_to_allen_regions = channels["acronym"]
        channel_id_to_atlas_id = channels["atlas_id"]

        unit_id_to_allen_regions = channel_id_to_allen_regions[unit_id_to_channel_id]
        unit_id_to_beryl_regions = brain_regions.id2acronym(atlas_id=channel_id_to_atlas_id, mapping="beryl")
        unit_id_to_cosmos_regions = brain_regions.id2acronym(atlas_id=channel_id_to_atlas_id, mapping="cosmos")

        self.recording_extractor.set_property(
            key="allen_location", values=unit_id_to_allen_regions
        )  # Acronyms are symmetric, do not differentiate hemisphere to be consistent with their usage
        self.recording_extractor.set_property(key="beryl_location", values=unit_id_to_beryl_regions)
        self.recording_extractor.set_property(key="cosmos_location", values=unit_id_to_cosmos_regions)

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        if self.has_histology:
            metadata["Ecephys"].update(
                UnitProperties=[
                    dict(
                        name="allen_location",
                        description="Brain region reference in the Allen Mouse Brain Atlas.",
                    ),
                    dict(
                        name="beryl_location",
                        description="Brain region reference in the Allen Mouse Brain Atlas.",
                    ),
                    dict(
                        name="cosmos_location",
                        description="Brain region reference in the Allen Mouse Brain Atlas.",
                    ),
                ]
            )

        return metadata

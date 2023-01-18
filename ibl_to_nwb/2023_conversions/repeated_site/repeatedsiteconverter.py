from one.api import ONE
from neuroconv import ConverterPipe

from ..iblconverter import IblConverter

class RepeatedSiteConverter(IblConverter):
    def get_metadata(self):
        metadata = super().get_metadata()

        metadata["NWBFile"]["experiment_description"] = "..."  # Hardcode paper abstract
        metadata["NWBFile"]["related_publications"] = "..." # Hardcode paper DOI for these sessions

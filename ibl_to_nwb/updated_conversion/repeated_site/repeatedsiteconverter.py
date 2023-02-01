from pathlib import Path

from one.api import ONE
from neuroconv.utils import load_dict_from_file

from ..iblconverter import IblConverter


class RepeatedSiteConverter(IblConverter):

    def get_metadata(self):
        metadata = super().get_metadata()

        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)

        # TODO: fetch session and subject-level metadata, including comments/notes
        experiment_metadata = load_dict_from_file(file_path=Path(__file__) / "experiment_metadata.yml")

        metadata["NWBFile"]["experiment_description"] = experiment_metadata["experiment_description"]
        metadata["NWBFile"]["related_publications"] = experiment_metadata["related_publications"]

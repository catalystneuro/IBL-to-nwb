from pathlib import Path

from neuroconv.utils import load_dict_from_file
from one.api import ONE

from ..iblconverter import IblConverter


class BrainwideMapConverter(IblConverter):
    def get_metadata(self):
        metadata = super().get_metadata()

        # TODO: fetch session and subject-level metadata, including comments/notes
        experiment_metadata = load_dict_from_file(file_path=Path(__file__) / "experiment_metadata.yml")

        metadata["NWBFile"]["session_description"] = "A session from the Brain Wide Map data release from the IBL."
        metadata["NWBFile"]["experiment_description"] = experiment_metadata["experiment_description"]
        metadata["NWBFile"]["related_publications"] = experiment_metadata["related_publications"]

from pathlib import Path

from neuroconv.utils import dict_deep_update, load_dict_from_file
from one.api import ONE

from ..iblconverter import IblConverter


class BrainwideMapConverter(IblConverter):
    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        experiment_metadata = load_dict_from_file(file_path=Path(__file__).parent / "brainwide_map_metadata.yml")
        dict_deep_update(metadata, experiment_metadata)
        metadata["NWBFile"]["session_description"] = "A session from the Brain Wide Map data release from the IBL."

        return metadata

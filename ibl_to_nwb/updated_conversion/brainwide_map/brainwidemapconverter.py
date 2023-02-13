from pathlib import Path

from neuroconv.utils import dict_deep_update, load_dict_from_file
from one.api import ONE

from ..iblconverter import IblConverter


class BrainwideMapConverter(IblConverter):
    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        experiment_metadata = load_dict_from_file(file_path=Path(__file__).parent / "brainwide_map_metadata.yml")
        dict_deep_update(metadata, experiment_metadata)

        metadata["Subject"]["description"] = (
            "Mice were housed under a 12/12 h light/dark cycle (normal or inverted depending on the laboratory) "
            "with food and water 112 available ad libitum, except during behavioural training days."
        )

        return metadata

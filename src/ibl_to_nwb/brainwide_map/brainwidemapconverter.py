from pathlib import Path

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ..iblconverter import IblConverter


class BrainwideMapConverter(IblConverter):
    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        experiment_metadata = load_dict_from_file(file_path=Path(__file__).parent / "brainwide_map_metadata.yml")
        metadata = dict_deep_update(metadata, experiment_metadata)

        return metadata

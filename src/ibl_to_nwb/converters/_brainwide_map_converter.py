from pathlib import Path

from neuroconv.utils import dict_deep_update, load_dict_from_file

from src.ibl_to_nwb.converters._iblconverter import IblConverter


class BrainwideMapConverter(IblConverter):
    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        experiment_metadata = load_dict_from_file(file_path=Path(__file__).parent / "brainwide_map_general.yml")
        metadata = dict_deep_update(metadata, experiment_metadata)

        return metadata

from pathlib import Path

from neuroconv.utils import dict_deep_update, load_dict_from_file

from ibl_to_nwb.converters._iblconverter import IblConverter


class BrainwideMapConverter(IblConverter):
    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        brainwide_map_metadata_file_path = Path(__file__).parent.parent / "_metadata" / "brainwide_map_general.yml"
        experiment_metadata = load_dict_from_file(file_path=brainwide_map_metadata_file_path)
        metadata = dict_deep_update(metadata, experiment_metadata)

        return metadata

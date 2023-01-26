from pathlib import Path

from one.api import ONE
from pydantic import FilePath
from pynwb import NWBFile, H5DataIO
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import BaseDataInterface
from neuroconv.utils import load_dict_from_file


class BrainwideMapTrialsInterface(BaseDataInterface):
    def __init__(self, session: str, cache_folder: FilePath):
        self.cache_folder = cache_folder
        self.session = session

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        trial_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "trials.yml")
        metadata.update(trial_metadata)
        return metadata

    def run_conversion(self, nwbfile: NWBFile, metadata: dict):
        one = ONE(
            base_url="https://openalyx.internationalbrainlab.org",
            password="international",
            silent=True,
            cache_dir=self.cache_folder,
        )
        trials = one.load_object(id=self.session, obj="trials", collection="alf")

        column_ordering = [
            "choice",
            "feedbackType",
            "rewardVolume",
            "contrastLeft",
            "contrastRight",
            "probabilityLeft",
            "feedback_times",
            "response_times",
            "stimOff_times",
            "stimOn_times",
            "goCue_times",
            "goCueTrigger_times",
            "firstMovement_times",
        ]

        for start_time, stop_time in self.trials["intervals"]:
            nwbfile.add_trial(start_time=start_time, stop_time=stop_time)

        for ibl_key in column_ordering:
            nwbfile.add_trial_column(
                name=metadata["Trials"][ibl_key]["name"],
                description=metadata["Trials"][ibl_key]["description"],
                data=H5DataIO(trials[ibl_key], compression=True),
            )

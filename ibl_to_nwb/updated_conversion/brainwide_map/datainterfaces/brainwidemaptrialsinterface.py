from pathlib import Path

from hdmf.common import VectorData
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import H5DataIO, NWBFile
from pynwb.epoch import TimeIntervals


class BrainwideMapTrialsInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str):
        self.one = one
        self.session = session

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        trial_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "trials.yml")
        metadata.update(trial_metadata)
        return metadata

    def run_conversion(self, nwbfile: NWBFile, metadata: dict):
        trials = self.one.load_object(id=self.session, obj="trials", collection="alf")

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
            "firstMovement_times",
        ]
        columns = [
            VectorData(
                name="start_time",
                description="The beginning of the trial.",
                data=H5DataIO(trials["intervals"][:, 0], compression=True),
            ),
            VectorData(
                name="stop_time",
                description="The end of the trial.",
                data=H5DataIO(trials["intervals"][:, 1], compression=True),
            ),
        ]
        for ibl_key in column_ordering:
            columns.append(
                VectorData(
                    name=metadata["Trials"][ibl_key]["name"],
                    description=metadata["Trials"][ibl_key]["description"],
                    data=H5DataIO(trials[ibl_key], compression=True),
                )
            )
        nwbfile.add_time_intervals(
            TimeIntervals(
                name="trials",
                description="Trial intervals and conditions.",
                columns=columns,
            )
        )

        # for start_time, stop_time in trials["intervals"]:
        #    nwbfile.add_trial(start_time=start_time, stop_time=stop_time)

        # for ibl_key in column_ordering:
        #    nwbfile.add_trial_column(
        #        name=metadata["Trials"][ibl_key]["name"],
        #        description=metadata["Trials"][ibl_key]["description"],
        #        data=H5DataIO(trials[ibl_key], compression=True),
        #    )

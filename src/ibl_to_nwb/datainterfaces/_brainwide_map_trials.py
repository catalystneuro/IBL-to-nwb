from pathlib import Path
from typing import Optional

from hdmf.common import VectorData
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals
from brainbox.io.one import SessionLoader


class BrainwideMapTrialsInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, revision: Optional[str] = None):
        self.one = one
        self.session = session
        self.revision = one.list_revisions(session)[-1] if revision is None else revision
        self.session_loader = SessionLoader(one=self.one, eid=self.session, revision=self.revision)
        self.session_loader.load_trials()

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        trial_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "trials.yml")
        metadata.update(trial_metadata)
        return metadata

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict):
        # trials = self.one.load_object(id=self.session, obj="trials", collection="alf", revision=self.revision)
        trials = self.session_loader.trials

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
                data=trials["intervals_0"].values,
            ),
            VectorData(
                name="stop_time",
                description="The end of the trial.",
                data=trials["intervals_1"].values,
            ),
        ]
        for ibl_key in column_ordering:
            columns.append(
                VectorData(
                    name=metadata["Trials"][ibl_key]["name"],
                    description=metadata["Trials"][ibl_key]["description"],
                    data=trials[ibl_key].values,
                )
            )
        nwbfile.add_time_intervals(
            TimeIntervals(
                name="trials",
                description="Trial intervals and conditions.",
                columns=columns,
            )
        )

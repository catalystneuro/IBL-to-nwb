from pathlib import Path
from typing import Optional

from brainbox.io.one import SessionLoader
from hdmf.common import VectorData
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals


class BrainwideMapTrialsInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, revision: Optional[str] = None):
        self.one = one
        self.session = session
        self.revision = one.list_revisions(session)[-1] if revision is None else revision

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        trial_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "trials.yml")
        metadata.update(trial_metadata)
        return metadata

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, stub_test: bool = False, stub_trials: int = 10):
        """
        Add trial data to NWBFile.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWBFile to add data to.
        metadata : dict
            Metadata dictionary.
        stub_test : bool, default: False
            If True, only add the first stub_trials trials for testing.
        stub_trials : int, default: 10
            Number of trials to include when stub_test=True.
        """
        session_loader = SessionLoader(one=self.one, eid=self.session, revision=self.revision)
        session_loader.load_trials()
        trials = session_loader.trials

        # Subset trials if stub_test
        if stub_test:
            trials = trials.iloc[:stub_trials]

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

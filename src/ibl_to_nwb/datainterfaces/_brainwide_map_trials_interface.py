from pathlib import Path
from typing import Optional
import logging
import time

from brainbox.io.one import SessionLoader
from hdmf.common import VectorData
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals

from ._base_ibl_interface import BaseIBLDataInterface


class BrainwideMapTrialsInterface(BaseIBLDataInterface):
    """Interface for trial behavioral data (revision-dependent processed data)."""

    # Trials use BWM standard revision
    REVISION: str | None = "2024-05-06"

    def __init__(self, one: ONE, session: str):
        self.one = one
        self.session = session
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for trials data.

        BWM sessions use the consolidated parquet format (_ibl_trials.table.pqt).
        Older sessions use individual .npy files.

        Returns
        -------
        dict
            Data requirements with alternatives for BWM vs legacy formats
        """
        return {
            "one_objects": [],  # Uses SessionLoader abstraction
            "exact_files_options": {
                # BWM format: consolidated parquet table (preferred)
                "bwm_format": ["alf/trials.table.pqt"],
                # Legacy format: individual npy files
                "legacy_format": [
                    "alf/trials.intervals.npy",
                    "alf/trials.choice.npy",
                    "alf/trials.feedbackType.npy",
                    "alf/trials.rewardVolume.npy",
                    "alf/trials.contrastLeft.npy",
                    "alf/trials.contrastRight.npy",
                    "alf/trials.probabilityLeft.npy",
                    "alf/trials.feedback_times.npy",
                    "alf/trials.response_times.npy",
                    "alf/trials.stimOff_times.npy",
                    "alf/trials.stimOn_times.npy",
                    "alf/trials.goCue_times.npy",
                    "alf/trials.firstMovement_times.npy",
                ],
            },
        }

    @classmethod
    def download_data(
        cls,
        one: ONE,
        eid: str,
        download_only: bool = True,
        logger: Optional[logging.Logger] = None,
        **kwargs
    ) -> dict:
        """
        Download trials data using SessionLoader.

        NOTE: Uses class-level REVISION attribute automatically.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        download_only : bool, default=True
            If True, download but don't load into memory
        logger : logging.Logger, optional
            Logger for progress tracking

        Returns
        -------
        dict
            Download status
        """
        requirements = cls.get_data_requirements()

        # Use class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading trials data (session {eid}, revision {revision})")

        start_time = time.time()

        # SessionLoader.load_trials() downloads all trials files
        # NO try-except - let it fail if files missing
        session_loader = SessionLoader(one=one, eid=eid, revision=revision)
        session_loader.load_trials()

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded trials data in {download_time:.2f}s")

        # SessionLoader handles format detection internally, report BWM format as default
        # (it will fall back to legacy if needed)
        return {
            "success": True,
            "downloaded_objects": ["trials"],
            "downloaded_files": requirements["exact_files_options"]["bwm_format"],
            "already_cached": [],
            "alternative_used": "bwm_format",
            "data": None,
        }

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

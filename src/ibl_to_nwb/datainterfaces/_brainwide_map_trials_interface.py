from typing import Optional
import logging
import time

import numpy as np
import pandas as pd
from brainbox.io.one import SessionLoader
from hdmf.common import VectorData
from one.api import ONE
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals

from ._base_ibl_interface import BaseIBLDataInterface


# Trial column descriptions for NWB metadata
# Order: Temporal (chronological) -> Stimulus -> Response/Outcome
TRIAL_COLUMN_DESCRIPTIONS = {
    # Temporal columns (chronological order within a trial)
    "start_time": "The beginning of the trial.",
    "stop_time": "The end of the trial.",
    "go_cue_time": "Start time of the go cue tone (100ms 5kHz sine wave), recorded via soundcard sync fed back into Bpod.",
    "stim_on_time": "Time when the visual stimulus appears on screen, detected by photodiode over the sync square.",
    "first_movement_time": "Time of first wheel movement >= 0.1 radians, occurring between go cue and feedback.",
    "response_time": "Time when response was recorded (wheel reached threshold or 60s timeout).",
    "feedback_time": "Time of feedback delivery (valve TTL for correct, white noise trigger for incorrect).",
    "stim_off_time": "Time of stimulus offset, recorded by external photodiode.",
    # Stimulus columns
    "contrast_proportion": "Contrast of the visual stimulus as a proportion (0 to 1, where 1 is 100% contrast). NaN for catch trials.",
    "stimulus_side": "Side where stimulus appeared: 'left' (-35 deg), 'right' (+35 deg), or 'none' (catch trial).",
    "probability_left": "Prior probability of left stimulus (0.2, 0.5, or 0.8 in biasedChoiceWorld).",
    # Response and outcome columns
    "choice": "Mouse response: 'left' (CCW wheel), 'right' (CW wheel), or 'no_go' (timeout).",
    "feedback_type": "Trial outcome: 'correct' (reward) or 'incorrect' (white noise).",
    "reward_volume_uL": "Volume of sugar water reward in microliters (0 for incorrect trials).",
}

# Mapping from IBL column names to NWB column names
# Only includes columns that need renaming (same-name columns handled automatically)
IBL_TO_NWB_COLUMNS = {
    "intervals_0": "start_time",
    "intervals_1": "stop_time",
    "goCue_times": "go_cue_time",
    "stimOn_times": "stim_on_time",
    "firstMovement_times": "first_movement_time",
    "response_times": "response_time",
    "feedback_times": "feedback_time",
    "stimOff_times": "stim_off_time",
    "probabilityLeft": "probability_left",
    "feedbackType": "feedback_type",
    "rewardVolume": "reward_volume_uL",
    # These are computed from contrastLeft/contrastRight, not direct mappings
    # "contrast_proportion": computed
    # "stimulus_side": computed
    # "choice": same name, but transformed values
}


class BrainwideMapTrialsInterface(BaseIBLDataInterface):
    """Interface for trial behavioral data (revision-dependent processed data)."""

    # Trials use BWM standard revision
    REVISION: str | None = "2025-05-06"

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

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, stub_test: bool = False, stub_trials: int = 10):
        """
        Add trial data to NWBFile.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWBFile to add data to.
        metadata : dict
            Metadata dictionary (not used, kept for interface compatibility).
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

        # Apply tidy data transformations
        trials = self._apply_tidy_transformations(trials)

        # Column definitions: (nwb_name, source_column) in chronological/logical order
        columns_spec = [
            ("start_time", "intervals_0"),
            ("stop_time", "intervals_1"),
            # Chronological event times
            ("go_cue_time", "goCue_times"),
            ("stim_on_time", "stimOn_times"),
            ("first_movement_time", "firstMovement_times"),
            ("response_time", "response_times"),
            ("feedback_time", "feedback_times"),
            ("stim_off_time", "stimOff_times"),
            # Stimulus
            ("contrast_proportion", "contrast"),
            ("stimulus_side", "stimulus_side"),
            ("probability_left", "probabilityLeft"),
            # Response and outcome
            ("choice", "choice"),
            ("feedback_type", "feedbackType"),
            ("reward_volume_uL", "rewardVolume"),
        ]

        columns = []
        for nwb_name, source_col in columns_spec:
            columns.append(
                VectorData(
                    name=nwb_name,
                    description=TRIAL_COLUMN_DESCRIPTIONS[nwb_name],
                    data=trials[source_col].values,
                )
            )

        nwbfile.add_time_intervals(
            TimeIntervals(
                name="trials",
                description="Trial intervals and conditions.",
                columns=columns,
            )
        )

    @staticmethod
    def _apply_tidy_transformations(trials: pd.DataFrame) -> pd.DataFrame:
        """
        Apply tidy data transformations to trials DataFrame.

        Transformations:
        - choice: -1/0/+1 -> "left"/"no_go"/"right"
        - feedbackType: -1/+1 -> "incorrect"/"correct"
        - contrastLeft/contrastRight -> contrast + stimulus_side

        Parameters
        ----------
        trials : pd.DataFrame
            Raw trials data from SessionLoader.

        Returns
        -------
        pd.DataFrame
            Transformed trials with tidy column formats.
        """
        trials = trials.copy()

        # Transform choice: -1 -> "left", 0 -> "no_go", +1 -> "right"
        choice_map = {-1.0: "left", 0.0: "no_go", 1.0: "right"}
        trials["choice"] = trials["choice"].map(choice_map)

        # Transform feedback_type: -1 -> "incorrect", +1 -> "correct"
        feedback_map = {-1.0: "incorrect", 1.0: "correct"}
        trials["feedbackType"] = trials["feedbackType"].map(feedback_map)

        # Consolidate contrast columns into contrast + stimulus_side
        def compute_stimulus_side(left, right):
            if pd.isna(left) and pd.isna(right):
                return "none"
            return "left" if left > 0 else "right"

        def compute_contrast(left, right):
            if pd.isna(left) and pd.isna(right):
                return np.nan
            return left if left > 0 else right

        trials["stimulus_side"] = [
            compute_stimulus_side(l, r) for l, r in zip(trials["contrastLeft"], trials["contrastRight"])
        ]
        trials["contrast"] = [compute_contrast(l, r) for l, r in zip(trials["contrastLeft"], trials["contrastRight"])]

        return trials

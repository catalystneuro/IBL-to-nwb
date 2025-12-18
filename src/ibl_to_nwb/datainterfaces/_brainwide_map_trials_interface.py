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


# Single source of truth for trials column metadata
# Keys are NWB column names (dict order = column order in NWB file)
# Values contain IBL source column name and description
# Note: Some IBL columns are transformed before mapping:
#   - choice: -1/0/+1 -> "left"/"no_go"/"right"
#   - feedbackType: -1/+1 -> "incorrect"/"correct"
#   - contrastLeft/contrastRight -> "contrast" + "stimulus_side"
TRIALS_COLUMNS = {
    # Temporal columns (chronological order within a trial)
    "start_time": {
        "ibl_name": "intervals_0",
        "description": "The beginning of the trial.",
    },
    "stop_time": {
        "ibl_name": "intervals_1",
        "description": "The end of the trial.",
    },
    "auditory_cue_time": {
        "ibl_name": "goCue_times",
        "description": "Start time of the auditory go cue tone (100ms 5kHz sine wave), recorded via soundcard sync fed back into Bpod.",
    },
    "stimulus_onset_time": {
        "ibl_name": "stimOn_times",
        "description": "Time when the Gabor patch appears on screen, detected by photodiode over the sync square.",
    },
    "first_wheel_movement_time": {
        "ibl_name": "firstMovement_times",
        "description": "Time of first wheel movement >= 0.1 radians, occurring between go cue and feedback.",
    },
    "choice_registration_time": {
        "ibl_name": "response_times",
        "description": "Time when the mouse's choice was registered (wheel crossed +/-35 deg threshold, or 60s timeout).",
    },
    "feedback_time": {
        "ibl_name": "feedback_times",
        "description": "Time of feedback delivery (valve TTL for correct, white noise trigger for incorrect).",
    },
    "stimulus_offset_time": {
        "ibl_name": "stimOff_times",
        "description": "Time when the Gabor patch disappears from screen, recorded by external photodiode.",
    },
    # Stimulus columns
    "gabor_contrast": {
        "ibl_name": "contrast",  # computed from contrastLeft/contrastRight
        "description": "Contrast of the Gabor patch stimulus as a proportion (0 to 1, where 1 is 100% contrast). NaN for catch trials.",
    },
    "stimulus_side": {
        "ibl_name": "stimulus_side",  # computed from contrastLeft/contrastRight
        "description": "Side where stimulus appeared: 'left' (-35 deg), 'right' (+35 deg), or 'none' (catch trial).",
    },
    "probability_left": {
        "ibl_name": "probabilityLeft",
        "description": "Prior probability of left stimulus (0.2, 0.5, or 0.8 in biasedChoiceWorld).",
    },
    # Response and outcome columns
    "mouse_choice": {
        "ibl_name": "choice",  # transformed from -1/0/+1 to strings
        "description": "Mouse's choice: 'left' (CCW wheel turn), 'right' (CW wheel turn), or 'no_go' (timeout).",
    },
    "trial_outcome": {
        "ibl_name": "feedbackType",  # transformed from -1/+1 to strings
        "description": "Trial outcome: 'correct' (rewarded) or 'incorrect' (white noise burst).",
    },
    "reward_volume_uL": {
        "ibl_name": "rewardVolume",
        "description": "Volume of sugar water reward in microliters (0 for incorrect trials).",
    },
}

# Derived mappings for convenience (generated from master table)
IBL_TO_NWB_COLUMNS = {v["ibl_name"]: k for k, v in TRIALS_COLUMNS.items()}


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

        # Build columns using the master TRIALS_COLUMNS table
        columns = []
        for nwb_name, col_info in TRIALS_COLUMNS.items():
            columns.append(
                VectorData(
                    name=nwb_name,
                    description=col_info["description"],
                    data=trials[col_info["ibl_name"]].values,
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

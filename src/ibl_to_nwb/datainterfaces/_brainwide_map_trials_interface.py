from typing import Optional
import logging
import math
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
#   - choice: -1/0/+1 -> "left"/"no_response"/"right"
#   - feedbackType: -1/+1 -> True/False (is_mouse_rewarded)
#   - contrastLeft/contrastRight -> "gabor_stimulus_contrast" + "gabor_stimulus_side"
#   - probabilityLeft -> also used to derive "block_index" and "block_type"
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
    "quiescence_period": {
        "ibl_name": "quiescencePeriod",
        "description": "Required duration (seconds) the mouse must hold the wheel still before stimulus presentation. Sampled from exponential distribution (400-700ms, mean ~550ms). If wheel moves during this period, the timer resets. Relationship: gabor_stimulus_onset_time ≈ start_time + quiescence_period.",
    },
    "gabor_stimulus_onset_time": {
        "ibl_name": "stimOn_times",
        "description": "Time when the visual stimulus (Gabor patch) appears on screen, detected by photodiode. Coincides with auditory go cue.",
    },
    "auditory_cue_time": {
        "ibl_name": "goCue_times",
        "description": "Time of the auditory go cue (100ms, 5kHz tone) signaling the mouse may respond. Presented simultaneously with visual stimulus.",
    },
    "wheel_movement_onset_time": {
        "ibl_name": "firstMovement_times",
        "description": "Time of first detected wheel movement (>= 0.1 radians threshold) after go cue.",
    },
    "choice_registration_time": {
        "ibl_name": "response_times",
        "description": "Time when the mouse's choice was registered: either wheel movement reached the +/-35 degree threshold, or 60-second timeout elapsed.",
    },
    "feedback_time": {
        "ibl_name": "feedback_times",
        "description": "Time of feedback delivery: water reward for correct responses, or white noise pulse + 2-second timeout for incorrect responses.",
    },
    "gabor_stimulus_offset_time": {
        "ibl_name": "stimOff_times",
        "description": "Time when the Gabor patch disappears from screen, recorded by external photodiode.",
    },
    # Stimulus columns
    "gabor_stimulus_contrast": {
        "ibl_name": "gabor_stimulus_contrast",  # computed from contrastLeft/contrastRight, multiplied by 100
        "description": "Contrast of the Gabor patch as a percentage (0, 6.25, 12.5, 25, or 100). Uniformly sampled across trials. At 0% contrast (no visible stimulus), mice can still perform above chance using block probability prior.",
    },
    "gabor_stimulus_side": {
        "ibl_name": "gabor_stimulus_side",  # computed from contrastLeft/contrastRight
        "description": "Side where stimulus was assigned: 'left' or 'right'. Even at 0% contrast (invisible), trials are assigned a correct side based on block probability, allowing mice to use prior information.",
    },
    # Response and outcome columns
    "mouse_wheel_choice": {
        "ibl_name": "choice",  # transformed from -1/0/+1 to strings
        "description": "Mouse's response: 'left' (CCW wheel turn moving stimulus rightward), 'right' (CW wheel turn moving stimulus leftward), or 'no_response' (no response within 60s timeout).",
    },
    "is_mouse_rewarded": {
        "ibl_name": "is_mouse_rewarded",  # transformed from feedbackType: +1 -> True, -1 -> False
        "description": "Whether the mouse received a water reward (True) or negative feedback consisting of white noise pulse and 2-second timeout (False).",
    },
    "reward_volume_uL": {
        "ibl_name": "rewardVolume",
        "description": "Volume of water reward in microliters (0 for incorrect/timeout trials).",
    },
    # Block structure columns (derived from probability_left)
    "probability_left": {
        "ibl_name": "probabilityLeft",
        "description": "Block prior probability for stimulus on left side. After initial 90 unbiased trials (0.5), blocks alternate between 0.2 (right-biased) and 0.8 (left-biased). Block lengths: 20-100 trials from truncated geometric distribution (mean 51). Block changes are not cued.",
    },
    "block_type": {
        "ibl_name": "block_type",  # computed from probabilityLeft
        "description": "Block type based on stimulus probability bias: 'unbiased' (probability_left=0.5), 'left_block' (probability_left=0.8, stimulus 80% likely on left), or 'right_block' (probability_left=0.2, stimulus 80% likely on right).",
    },
    "block_index": {
        "ibl_name": "block_index",  # computed from probabilityLeft
        "description": "Zero-indexed block number. Increments each time probability_left changes. Block 0 is typically the initial unbiased block (~90 trials at 0.5 probability).",
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
            "exact_files_options": {
                # BWM format: consolidated parquet table (preferred)
                "bwm_format": ["alf/_ibl_trials.table.pqt"],
                # Legacy format: individual npy files
                "legacy_format": [
                    "alf/_ibl_trials.intervals.npy",
                    "alf/_ibl_trials.choice.npy",
                    "alf/_ibl_trials.feedbackType.npy",
                    "alf/_ibl_trials.rewardVolume.npy",
                    "alf/_ibl_trials.contrastLeft.npy",
                    "alf/_ibl_trials.contrastRight.npy",
                    "alf/_ibl_trials.probabilityLeft.npy",
                    "alf/_ibl_trials.feedback_times.npy",
                    "alf/_ibl_trials.response_times.npy",
                    "alf/_ibl_trials.stimOff_times.npy",
                    "alf/_ibl_trials.stimOn_times.npy",
                    "alf/_ibl_trials.goCue_times.npy",
                    "alf/_ibl_trials.firstMovement_times.npy",
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
                    data=trials[col_info["ibl_name"]].to_numpy(),
                )
            )

        trials_description = (
            "Trial data from the IBL decision-making task. "
            "On each trial, a visual stimulus (Gabor patch) appears on the left or right of a screen, "
            "and the mouse must move it to the center by turning a wheel with its front paws within 60 seconds. "
            "Correct responses are rewarded with water; incorrect responses trigger a white noise pulse and 2-second timeout. "
            "Trial timeline: (1) start_time begins a quiescence period where the mouse must hold the wheel still; "
            "(2) after quiescence_period elapses, the stimulus and auditory go cue appear simultaneously (gabor_stimulus_onset_time); "
            "(3) the mouse responds by turning the wheel to move the stimulus; "
            "(4) feedback_time marks reward or punishment delivery; "
            "(5) stop_time marks trial end. "
            "Stimulus contrast is uniformly sampled from 5 values (0%, 6.25%, 12.5%, 25%, 100%). "
            "On 0% contrast trials, no stimulus is visible but a correct side is still assigned based on block probability, "
            "allowing mice to perform above chance using prior information. "
            "After an initial 90 unbiased trials, stimulus probability alternates between left-biased (80:20) and right-biased (20:80) blocks "
            "of 20-100 trials (mean 51). Block changes are not cued. "
            "See IBL et al. (2021) eLife 10:e63711 for full task details."
        )

        nwbfile.add_time_intervals(
            TimeIntervals(
                name="trials",
                description=trials_description,
                columns=columns,
            )
        )

    @staticmethod
    def _apply_tidy_transformations(trials: pd.DataFrame) -> pd.DataFrame:
        """
        Apply tidy data transformations to trials DataFrame.

        Transformations:
        - choice: -1/0/+1 -> "left"/"no_response"/"right"
        - feedbackType: -1/+1 -> True/False (is_mouse_rewarded)
        - contrastLeft/contrastRight -> gabor_stimulus_contrast + gabor_stimulus_side
        - probabilityLeft -> block_index (increments on change) + block_type (categorical)

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

        # Transform choice: -1 -> "left", 0 -> "no_response", +1 -> "right"
        choice_map = {-1.0: "left", 0.0: "no_response", 1.0: "right"}
        trials["choice"] = trials["choice"].map(choice_map)

        # Transform feedbackType to boolean: +1 -> True (rewarded), -1 -> False (not rewarded)
        trials["is_mouse_rewarded"] = trials["feedbackType"] == 1.0

        # Consolidate contrast columns into gabor_stimulus_contrast + gabor_stimulus_side
        #
        # IBL encodes stimulus side using contrastLeft/contrastRight columns where one column
        # contains the contrast value and the other is NaN. This comes from the IBL extraction
        # pipeline (ibllib/io/extractors/biased_trials.py ContrastLR extractor):
        #
        #   contrastLeft = [t['contrast'] if np.sign(t['position']) < 0 else np.nan ...]
        #   contrastRight = [t['contrast'] if np.sign(t['position']) > 0 else np.nan ...]
        #
        # The stimulus position determines which column gets the value:
        #   - position < 0 (left, -35 deg): contrastLeft = contrast, contrastRight = NaN
        #   - position > 0 (right, +35 deg): contrastRight = contrast, contrastLeft = NaN
        #
        # This applies to ALL contrast levels including 0% contrast trials. For example:
        #   - Left 25% trial: contrastLeft=0.25, contrastRight=NaN
        #   - Right 0% trial: contrastLeft=NaN, contrastRight=0.0
        #
        # We consolidate into two tidy columns: gabor_stimulus_contrast and gabor_stimulus_side
        def compute_gabor_stimulus_side(left, right):
            # Determine side based on which column has a non-NaN value
            left_valid = not pd.isna(left)
            right_valid = not pd.isna(right)
            if left_valid and not right_valid:
                return "left"
            elif right_valid and not left_valid:
                return "right"
            elif left_valid and right_valid:
                # Both have values - should not happen in valid IBL data, but handle defensively
                return "left" if left >= right else "right"
            else:
                return "none"  # Both NaN - unexpected, indicates corrupted data

        def compute_gabor_stimulus_contrast(left, right):
            # Return the non-NaN contrast value as percentage (could be 0 for 0% contrast trials)
            # Multiply by 100 and round to 2 decimal places
            if not pd.isna(left) and (pd.isna(right) or left > 0):
                return round(left * 100, 2)
            elif not pd.isna(right):
                return round(right * 100, 2)
            else:
                return np.nan  # Both NaN - unexpected

        trials["gabor_stimulus_side"] = [
            compute_gabor_stimulus_side(l, r) for l, r in zip(trials["contrastLeft"], trials["contrastRight"])
        ]
        trials["gabor_stimulus_contrast"] = [
            compute_gabor_stimulus_contrast(l, r) for l, r in zip(trials["contrastLeft"], trials["contrastRight"])
        ]

        # Compute block_index and block_type from probabilityLeft
        # Validate: probabilityLeft must not contain NaN (indicates corrupted trial data)
        prob_left = trials["probabilityLeft"].values
        nan_mask = pd.isna(prob_left)
        if np.any(nan_mask):
            nan_indices = np.where(nan_mask)[0].tolist()
            raise ValueError(
                f"probabilityLeft contains NaN values at trial indices {nan_indices}. "
                "This indicates corrupted or incomplete trial data."
            )

        # block_index increments each time probabilityLeft changes
        block_index = np.zeros(len(prob_left), dtype=int)
        current_block = 0
        for i in range(1, len(prob_left)):
            if not math.isclose(prob_left[i], prob_left[i - 1]):
                current_block += 1
            block_index[i] = current_block
        trials["block_index"] = block_index

        # block_type: categorical based on probabilityLeft value
        def compute_block_type(prob):
            if math.isclose(prob, 0.5):
                return "unbiased"
            elif math.isclose(prob, 0.8):
                return "left_block"
            elif math.isclose(prob, 0.2):
                return "right_block"
            else:
                return f"p={prob}"  # Unexpected value, preserve it
        trials["block_type"] = trials["probabilityLeft"].apply(compute_block_type)

        return trials

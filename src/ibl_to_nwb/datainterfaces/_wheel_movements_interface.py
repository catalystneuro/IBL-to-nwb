"""Interface for detected wheel movement epochs."""

import logging
import time
from typing import Optional

import numpy as np
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb.epoch import TimeIntervals

from ._base_ibl_interface import BaseIBLDataInterface


class WheelMovementsInterface(BaseIBLDataInterface):
    """Interface for detected wheel movement epochs (intervals + peak amplitude)."""

    # Wheel data uses BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(self, one: ONE, session: str):
        self.one = one
        self.session = session
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for wheel movements.

        Returns
        -------
        dict
            Data requirements with exact file paths
        """
        return {
            "exact_files_options": {
                "standard": [
                    "alf/wheelMoves.intervals.npy",
                    "alf/wheelMoves.peakAmplitude.npy",
                ],
            },
        }

    @classmethod
    def get_load_object_kwargs(cls) -> dict:
        """Return kwargs for one.load_object() call."""
        return {"obj": "wheelMoves", "collection": "alf"}

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
        Download wheel movement data.

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
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading wheel movements data for session {eid} (revision {revision})")

        start_time = time.time()

        if logger:
            logger.info("  Loading wheelMoves")
        one.load_object(
            id=eid,
            revision=revision,
            download_only=download_only,
            **cls.get_load_object_kwargs(),
        )

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded wheel movements in {download_time:.2f}s")

        return {
            "success": True,
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def add_to_nwbfile(self, nwbfile, metadata: dict, stub_test: bool = False, stub_duration: float = 10.0):
        """
        Add wheel movement epochs to NWBFile.

        Parameters
        ----------
        nwbfile : NWBFile
            The NWBFile to add data to.
        metadata : dict
            Metadata dictionary.
        stub_test : bool, default: False
            If True, only add the first stub_duration seconds of data for testing.
        stub_duration : float, default: 10.0
            Duration in seconds to include when stub_test=True.
        """
        wheel_moves = self.one.load_object(id=self.session, revision=self.revision, **self.get_load_object_kwargs())

        # Subset data if stub_test
        if stub_test:
            # Use first movement start as reference time
            if len(wheel_moves["intervals"]) > 0:
                first_time = wheel_moves["intervals"][0, 0]
                stub_limit = first_time + stub_duration
                interval_mask = wheel_moves["intervals"][:, 0] <= stub_limit
                if not interval_mask.any():
                    interval_mask = np.zeros(len(wheel_moves["intervals"]), dtype=bool)
                    interval_mask[: min(100, len(interval_mask))] = True
                wheel_moves["intervals"] = wheel_moves["intervals"][interval_mask]
                wheel_moves["peakAmplitude"] = wheel_moves["peakAmplitude"][interval_mask]

        # Wheel movement intervals
        wheel_movement_intervals = TimeIntervals(
            name="WheelMovement",
            description=(
                "The onset and offset times of all detected movements. "
                "Movements are defined as a wheel movement of at least 0.012 rad over 200ms. "
                "For a rotary encoder of resolution 1024 in X4 encoding, this is equivalent to around 8 ticks. "
                "Movements below 50ms are discarded and two detected movements within 100ms of one another "
                "are considered as a single movement. For the onsets a lower threshold is used to find a more "
                "precise onset time. The wheel diameter is 6.2 cm and the number of ticks is 4096 per revolution."
            ),
        )
        for start_time, stop_time in wheel_moves["intervals"]:
            wheel_movement_intervals.add_row(start_time=start_time, stop_time=stop_time)
        wheel_movement_intervals.add_column(
            name="peak_amplitude",
            description="The absolute maximum amplitude of each detected wheel movement, relative to onset position.",
            data=wheel_moves["peakAmplitude"],
        )

        wheel_module = get_module(nwbfile=nwbfile, name="wheel", description="Wheel behavioral data.")
        wheel_module.add(wheel_movement_intervals)

"""Interface for raw wheel position data from quadrature encoder."""

import logging
import time
from typing import Optional

import numpy as np
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb.behavior import SpatialSeries

from ._base_ibl_interface import BaseIBLDataInterface


class WheelPositionInterface(BaseIBLDataInterface):
    """Interface for raw wheel position data (event-driven encoder output)."""

    # Wheel data uses BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(self, one: ONE, session: str):
        self.one = one
        self.session = session
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for wheel position.

        Returns
        -------
        dict
            Data requirements with exact file paths
        """
        return {
            "exact_files_options": {
                "standard": [
                    "alf/wheel.position.npy",
                    "alf/wheel.timestamps.npy",
                ],
            },
        }

    @classmethod
    def get_load_object_kwargs(cls) -> dict:
        """Return kwargs for one.load_object() call."""
        return {"obj": "wheel", "collection": "alf"}

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
        Download wheel position data.

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
            logger.info(f"Downloading wheel position data for session {eid} (revision {revision})")

        start_time = time.time()

        if logger:
            logger.info("  Loading wheel")
        one.load_object(
            id=eid,
            revision=revision,
            download_only=download_only,
            **cls.get_load_object_kwargs(),
        )

        download_time = time.time() - start_time

        if logger:
            logger.info(f"  Downloaded wheel position in {download_time:.2f}s")

        return {
            "success": True,
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def add_to_nwbfile(self, nwbfile, metadata: dict, stub_test: bool = False, stub_duration: float = 10.0):
        """
        Add raw wheel position data to NWBFile.

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
        wheel = self.one.load_object(id=self.session, revision=self.revision, **self.get_load_object_kwargs())

        # Subset data if stub_test
        if stub_test:
            original_times = wheel["timestamps"].copy()
            original_position = wheel["position"].copy()

            if original_times.size == 0:
                raise ValueError("Wheel timestamps array is empty; cannot create stub dataset.")

            stub_limit = original_times[0] + stub_duration
            time_mask = original_times <= stub_limit
            if not time_mask.any():
                sample_limit = min(1000, original_times.size)
                time_mask = np.zeros_like(original_times, dtype=bool)
                time_mask[:sample_limit] = True

            wheel["timestamps"] = original_times[time_mask]
            wheel["position"] = original_position[time_mask]

        if wheel["timestamps"].size < 2:
            raise ValueError("Wheel timestamps must contain at least two samples.")

        # Raw wheel position with irregular timestamps from encoder
        wheel_position_series = SpatialSeries(
            name="WheelPosition",
            description=(
                "Absolute unwrapped wheel angle recorded from a quadrature rotary encoder. "
                "The wheel (diameter 6.2 cm) is positioned under the mouse's forepaws and serves "
                "as the primary behavioral input device for reporting perceptual decisions. "
                "Sampling is event-driven: timestamps are recorded only when the wheel moves "
                "(i.e., when the encoder generates TTL edges), resulting in irregular inter-sample "
                "intervals. The encoder uses X4 decoding of two 90-degree phase-shifted channels, "
                "providing 4096 effective counts per revolution (angular resolution ~0.088 degrees "
                "or 2*pi/4096 radians). Position is NOT periodic: values grow unboundedly as the "
                "wheel rotates, accumulating across multiple full revolutions (e.g., 3 full turns "
                "clockwise = -6*pi radians). The position is never wrapped back to [0, 2*pi]. "
                "Sign convention follows mathematical standard: counter-clockwise rotation "
                "(from the subject's perspective) is positive."
            ),
            data=wheel["position"],
            timestamps=wheel["timestamps"],
            unit="radians",
            reference_frame="Initial angle at session start is defined as zero. Counter-clockwise is positive.",
        )

        wheel_module = get_module(nwbfile=nwbfile, name="wheel", description="Wheel behavioral data.")
        wheel_module.add(wheel_position_series)

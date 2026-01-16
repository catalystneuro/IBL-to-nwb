"""Interface for raw wheel position data from quadrature encoder."""

from pathlib import Path
from typing import Optional
import logging
import time

import numpy as np
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file
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
            obj="wheel",
            collection="alf",
            revision=revision,
            download_only=download_only,
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

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        metadata.update(load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "wheel_position.yml"))
        return metadata

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
        wheel = self.one.load_object(id=self.session, obj="wheel", collection="alf", revision=self.revision)

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
            name=metadata["WheelPosition"]["name"],
            description=metadata["WheelPosition"]["description"],
            data=wheel["position"],
            timestamps=wheel["timestamps"],
            unit="radians",
            reference_frame="Initial angle at start time is zero. Counter-clockwise is positive.",
        )

        wheel_module = get_module(nwbfile=nwbfile, name="wheel", description="Wheel behavioral data.")
        wheel_module.add(wheel_position_series)

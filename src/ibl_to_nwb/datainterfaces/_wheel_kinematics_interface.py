"""Interface for derived wheel kinematics (filtered position, velocity, acceleration)."""

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
from brainbox.behavior import wheel as wheel_methods
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import TimeSeries
from pynwb.behavior import SpatialSeries

from ._base_ibl_interface import BaseIBLDataInterface


class WheelKinematicsInterface(BaseIBLDataInterface):
    """Interface for derived wheel kinematics (interpolated position, velocity, acceleration)."""

    # Wheel data uses BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(self, one: ONE, session: str):
        self.one = one
        self.session = session
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for wheel kinematics.

        Note: This interface derives kinematics from the raw wheel position data.

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
        Download wheel position data (used to derive kinematics).

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
            logger.info(f"Downloading wheel data for kinematics (session {eid}, revision {revision})")

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
            logger.info(f"  Downloaded wheel data in {download_time:.2f}s")

        return {
            "success": True,
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        metadata.update(load_dict_from_file(file_path=Path(__file__).parent.parent / "_metadata" / "wheel_kinematics.yml"))
        return metadata

    def add_to_nwbfile(self, nwbfile, metadata: dict, stub_test: bool = False, stub_duration: float = 10.0):
        """
        Add derived wheel kinematics to NWBFile.

        Processing pipeline (hardcoded IBL defaults):
        1. Interpolate position to 1000 Hz (linear)
        2. Apply 8th order Butterworth lowpass filter (20 Hz corner, zero-phase)
        3. Compute velocity as derivative of filtered position
        4. Compute acceleration as derivative of velocity

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

        # Interpolate and filter position, compute velocity and acceleration
        interpolation_frequency = 1000.0  # Hz (IBL standard)
        interpolated_position, interpolated_timestamps = wheel_methods.interpolate_position(
            re_ts=wheel["timestamps"], re_pos=wheel["position"], freq=interpolation_frequency
        )
        velocity, acceleration = wheel_methods.velocity_filtered(pos=interpolated_position, fs=interpolation_frequency)

        # Regular sampling parameters
        interpolated_starting_time = interpolated_timestamps[0]
        interpolated_rate = 1 / (interpolated_timestamps[1] - interpolated_timestamps[0])

        # Filtered position (interpolated to 1000 Hz, Butterworth lowpass)
        filtered_position_series = SpatialSeries(
            name=metadata["WheelPositionFiltered"]["name"],
            description=metadata["WheelPositionFiltered"]["description"],
            data=interpolated_position,
            starting_time=interpolated_starting_time,
            rate=interpolated_rate,
            unit="radians",
            reference_frame="Interpolated to 1000 Hz, 8th order Butterworth 20 Hz lowpass, zero-phase.",
        )

        # Velocity derived from filtered position
        velocity_series = TimeSeries(
            name=metadata["WheelVelocity"]["name"],
            description=metadata["WheelVelocity"]["description"],
            data=velocity,
            starting_time=interpolated_starting_time,
            rate=interpolated_rate,
            unit="rad/s",
        )

        # Acceleration derived from velocity
        acceleration_series = TimeSeries(
            name=metadata["WheelAcceleration"]["name"],
            description=metadata["WheelAcceleration"]["description"],
            data=acceleration,
            starting_time=interpolated_starting_time,
            rate=interpolated_rate,
            unit="rad/s^2",
        )

        wheel_module = get_module(nwbfile=nwbfile, name="wheel", description="Wheel behavioral data.")
        wheel_module.add(filtered_position_series)
        wheel_module.add(velocity_series)
        wheel_module.add(acceleration_series)

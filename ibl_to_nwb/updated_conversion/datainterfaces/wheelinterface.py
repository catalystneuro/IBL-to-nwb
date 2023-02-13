from pathlib import Path

from brainbox.behavior import wheel as wheel_methods
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import H5DataIO, TimeSeries
from pynwb.behavior import CompassDirection, SpatialSeries
from pynwb.epoch import TimeIntervals


class WheelInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str):
        self.one = one
        self.session = session

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        metadata.update(load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "wheel.yml"))

        return metadata

    def run_conversion(self, nwbfile, metadata: dict):
        wheel_moves = self.one.load_object(id=self.session, obj="wheelMoves", collection="alf")
        wheel = self.one.load_object(id=self.session, obj="wheel", collection="alf")

        # Estimate velocity and acceleration
        interpolation_frequency = 1000.0  # Hz
        interpolated_position, interpolated_timestamps = wheel_methods.interpolate_position(
            re_ts=wheel["timestamps"], re_pos=wheel["position"], freq=interpolation_frequency
        )
        velocity, acceleration = wheel_methods.velocity_smoothed(
            pos=interpolated_position, freq=interpolation_frequency
        )

        # Wheel intervals of movement
        wheel_movement_intervals = TimeIntervals(
            name="WheelMovementIntervals",
            description=metadata["WheelMovement"]["description"],
        )
        for start_time, stop_time in wheel_moves["intervals"]:
            wheel_movement_intervals.add_row(start_time=start_time, stop_time=stop_time)
        wheel_movement_intervals.add_column(
            name=metadata["WheelMovement"]["columns"]["peakAmplitude"]["name"],
            description=metadata["WheelMovement"]["columns"]["peakAmplitude"]["description"],
            data=H5DataIO(wheel_moves["peakAmplitude"], compression=True),
        )

        # Wheel position over time
        compass_direction = CompassDirection(
            spatial_series=SpatialSeries(
                name=metadata["WheelPosition"]["name"],
                description=metadata["WheelPosition"]["description"],
                data=H5DataIO(wheel["position"], compression=True),
                timestamps=H5DataIO(wheel["timestamps"], compression=True),
                unit="rad",
                reference_frame="Initial angle at start time is zero. Counter-clockwise is positive.",
            )
        )
        velocity_series = TimeSeries(
            name=metadata["WheelVelocity"]["name"],
            description=metadata["WheelVelocity"]["description"],
            data=H5DataIO(velocity, compression=True),
            timestamps=H5DataIO(interpolated_timestamps, compression=True),
            unit="rad/s",
        )
        acceleration_series = TimeSeries(
            name=metadata["WheelAcceleration"]["name"],
            description=metadata["WheelAcceleration"]["description"],
            data=H5DataIO(acceleration, compression=True),
            timestamps=H5DataIO(interpolated_timestamps, compression=True),
            unit="rad/s^2",
        )

        behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="Processed behavioral data.")
        behavior_module.add(wheel_movement_intervals)
        behavior_module.add(compass_direction)
        behavior_module.add(velocity_series)
        behavior_module.add(acceleration_series)

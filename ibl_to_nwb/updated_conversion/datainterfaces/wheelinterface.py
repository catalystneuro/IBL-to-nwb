from pathlib import Path

from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file
from one.api import ONE
from pynwb import H5DataIO
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
                unit="rads",
                reference_frame="Initial angle at start time is zero. Counter-clockwise is positive.",
            )
        )

        behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="Processed behavioral data.")
        behavior_module.add(wheel_movement_intervals)
        behavior_module.add(compass_direction)

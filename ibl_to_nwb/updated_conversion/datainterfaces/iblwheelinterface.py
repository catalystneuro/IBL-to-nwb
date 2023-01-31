from pathlib import Path

from one.api import ONE
from pydantic import DirectoryPath
from pynwb import H5DataIO
from pynwb.behavior import SpatialSeries, CompassDirection
from pynwb.epoch import TimeIntervals
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from neuroconv.utils import load_dict_from_file


class IblWheelInterface(BaseDataInterface):
    def __init__(self, session: str, cache_folder: DirectoryPath):
        self.session = session
        self.cache_folder = cache_folder

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        metadata.update(load_dict_from_file(file_path=Path(__file__).parent.parent / "wheel.yml"))
        return metadata

    def run_conversion(self, nwbfile, metadata: dict):
        one = ONE(
            base_url='https://openalyx.internationalbrainlab.org',
            password='international',
            silent=True,
            cache_folder=self.cache_folder
        )

        behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="")  # TODO match description

        wheel_moves = one.load_object(
            id=self.session_id, obj="wheelMoves", collection="alf", cach_folder=self.cache_folder
        )
        wheel = one.load_object(id=self.session_id, obj="wheel", collection="alf", cach_folder=self.cache_folder)

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
        behavior_module.add(wheel_movement_intervals)

        # Wheel position over time
        compass_direction = CompassDirection(
          spatial_series=SpatialSeries(
                name=metadata["WheelPosition"]["name"],
                description=metadata["WheelPosition"]["description"],
                data=H5DataIO(wheel["position"], compression=True),
                timestamps=H5DataIO(wheel["timestamps"], compression=True),
                unit="rads",
            )
        )
        behavior_module.add(compass_direction)

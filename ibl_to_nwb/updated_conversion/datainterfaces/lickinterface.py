from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import H5DataIO
from pynwb.file import DynamicTable


class LickInterface(BaseDataInterface):
    def __init__(self, session: str, cache_folder: DirectoryPath):
        self.session = session
        self.cache_folder = cache_folder

    def run_conversion(self, nwbfile, metadata: dict):
        one = ONE(
            base_url="https://openalyx.internationalbrainlab.org",
            password="international",
            silent=True,
            cache_folder=self.cache_folder,
        )

        licks = one.load_object(id=self.session_id, obj="licks", collection="alf")

        behavior_module = get_module(nwbfile=nwbfile, name="behavior", description="")  # TODO match description

        lick_events_table = DynamicTable(
            name="LickTimes",
            description=(
                "Time stamps of licks as detected from tongue dlc traces. "
                "If left and right camera exist, the licks detected from both cameras are combined."
            ),
        )
        lick_events_table.add_column(
            name="lick_time",
            description="Time stamps of licks as detected from tongue dlc traces",
            data=H5DataIO(licks["times"], compression=True),
        )
        behavior_module.add(lick_events_table)

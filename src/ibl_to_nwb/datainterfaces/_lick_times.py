from typing import Optional

from hdmf.common import VectorData
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile
from pynwb.file import DynamicTable


class LickInterface(BaseDataInterface):
    def __init__(self, one: ONE, session: str, revision: Optional[str] = None):
        self.one = one
        self.session = session
        self.revision = one.list_revisions(session)[-1] if revision is None else revision

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict):
        # licks = self.one.load_object(id=self.session, obj="licks", collection="alf")
        licks = self.one.load_dataset(self.session, "licks.times", collection="alf", revision=self.revision)

        lick_events_table = DynamicTable(
            name="LickTimes",
            description=(
                "Time stamps of licks as detected from tongue dlc traces. "
                "If left and right camera exist, the licks detected from both cameras are combined."
            ),
            columns=[
                VectorData(
                    name="lick_time",
                    description="Time stamps of licks as detected from tongue dlc traces",
                    data=licks,
                )
            ],
        )

        camera_module = get_module(nwbfile=nwbfile, name="camera", description="Processed camera data.")
        camera_module.add(lick_events_table)

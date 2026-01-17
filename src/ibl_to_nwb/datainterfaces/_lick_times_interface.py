from ndx_events import Events
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile

from ._base_ibl_interface import BaseIBLDataInterface


class LickInterface(BaseIBLDataInterface):
    """Interface for lick detection data (revision-dependent processed data)."""

    # Lick detection uses BWM standard revision
    REVISION: str | None = "2025-05-06"

    def __init__(self, one: ONE, session: str):
        self.one = one
        self.session = session
        self.revision = self.REVISION

    @classmethod
    def get_data_requirements(cls) -> dict:
        """
        Declare exact data files required for lick detection.

        Returns
        -------
        dict
            Data requirements specification with exact file path
        """
        return {
            "exact_files_options": {
                "standard": [
                    "alf/licks.times.npy",
                ],
            },
        }

    @classmethod
    def get_load_dataset_kwargs(cls) -> dict:
        """Return kwargs for one.load_dataset() call."""
        return {"dataset": "licks.times", "collection": "alf"}

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict):
        lick_timestamps = self.one.load_dataset(self.session, revision=self.revision, **self.get_load_dataset_kwargs())

        # Use ndx-events Events type for point events (timestamps only)
        lick_events = Events(
            name="EventsLickTimes",
            description=(
                "Lick event timestamps detected from tongue pose estimation (Lightning Pose). "
                "Detection algorithm: frame-to-frame position changes in tongue landmarks "
                "(tongue_end_l_x, tongue_end_l_y, tongue_end_r_x, tongue_end_r_y) are computed, "
                "and frames where any coordinate changes by more than std(diff)/4 are marked as lick events. "
                "If left and right camera data exist, the licks detected from both cameras are combined."
            ),
            timestamps=lick_timestamps,
        )

        lick_times_module = get_module(nwbfile=nwbfile, name="lick_times", description="Discrete behavioral events.")
        lick_times_module.add(lick_events)

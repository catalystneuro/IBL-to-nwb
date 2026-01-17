import logging
from typing import Optional

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
        Download lick times data.

        Uses one.load_dataset() directly. Will raise exception if file missing.

        NOTE: Uses class-level REVISION attribute automatically.

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
            Download status with list of files downloaded
        """
        requirements = cls.get_data_requirements()

        # Use class-level REVISION attribute
        revision = cls.REVISION

        if logger:
            logger.info(f"Downloading lick times for session {eid} (revision {revision})")

        # NO try-except - let it fail if file missing!
        one.load_dataset(
            eid,
            revision=revision,
            download_only=download_only,
            **cls.get_load_dataset_kwargs(),
        )

        return {
            "success": True,
            "downloaded_objects": [],
            "downloaded_files": requirements["exact_files_options"]["standard"],
            "already_cached": [],
            "alternative_used": None,
            "data": None,
        }

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

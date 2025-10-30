from typing import Optional
import logging

from hdmf.common import VectorData
from neuroconv.tools.nwb_helpers import get_module
from one.api import ONE
from pynwb import NWBFile
from pynwb.file import DynamicTable

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
            "one_objects": [],  # Uses load_dataset directly, not load_object
            "exact_files_options": {
                "standard": [
                    "alf/licks.times.npy",
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
            "licks.times",
            collection="alf",
            revision=revision,
            download_only=download_only,
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

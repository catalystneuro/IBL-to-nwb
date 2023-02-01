from shutil import rmtree
from typing import Optional

from neuroconv import ConverterPipe
from one.api import ONE
from pydantic import DirectoryPath
from pynwb import NWBFile


class IblConverter(ConverterPipe):
    def __init__(self, cache_folder: DirectoryPath, data_interfaces: list):
        self.cache_folder = cache_folder
        super().__init__(data_interfaces=data_interfaces)

    def get_metadata(self):
        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)
        # TODO: fetch session and subject-level metadata, including comments/notes

    def run_conversion(
        self,
        nwbfile_path: Optional[str] = None,
        nwbfile: Optional[NWBFile] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = False,
        conversion_options: Optional[dict] = None,
    ):
        super().run_conversion(
            nwbfile_path=nwbfile_path,
            nwbfile=nwbfile,
            metadata=metadata,
            overwrite=overwrite,
            conversion_options=conversion_options,
        )

        rmtree(self.cache_folder)

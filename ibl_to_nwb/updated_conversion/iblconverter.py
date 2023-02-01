"""Primary base class for all IBL converters."""
import json
from datetime import datetime
from shutil import rmtree
from typing import Optional

from pynwb import NWBFile
from one.api import ONE
from neuroconv import ConverterPipe


class IblConverter(ConverterPipe):
    def __init__(self, one: ONE, data_interfaces: list):
        self.one = one
        super().__init__(data_interfaces=data_interfaces)

    def get_metadata(self):
        metadata = super().get_metadata()  # Aggregates from the interfaces

        session_metadata = self.one.alyx.rest(url='sessions', action='list', id=self.session)[0]
        lab_metadata = next(lab for lab in self.one.alyx.rest('labs', 'list') if lab["name"] == session_metadata["lab"])

        metadata["NWBFile"]["session_id"] = f"{metadata['NWBFile']['session_start_time']}_{session_metadata['number']}"
        metadata["NWBFile"]["identifier"] = session_metadata["id"]  # The eid is more appropriate in place of a UUID
        metadata["NWBFile"]["lab"] = session_metadata["lab"]
        metadata["NWBFile"]["institution"] = lab_metadata["institution"]
        metadata["NWBFile"]["protocol"] = session_metadata['task_protocol']

        subject_metadata = self.one.alyx.rest(url='subjects', action='list', field_filter1=session_metadata["subject"])

        subject_extra_metadata = dict()
        subject_extra_metadata_name_mapping = dict(
            last_water_restriction="last_water_restriction",  # ISO
            remaining_water="remaining_water_ml",
            expected_water="expected_water_ml",
            url="url",
        )
        for ibl_key, nwb_name in subject_extra_metadata_name_mapping.items():
            if ibl_key not in subject_metadata:
                continue
            subject_extra_metadata.update({nwb_name: subject_metadata[ibl_key]})
        metadata["Subject"]["description"] = json.dumps(subject_extra_metadata)

        metadata["Subject"]["subject_id"] = subject_metadata["nickname"]
        metadata["Subject"]["sex"] = subject_metadata["sex"]
        metadata["Subject"]["species"] = "Mus musculus"  # Though it's a field in their schema, it's never specified
        metadata["Subject"]["weight"] = subject_metadata["reference_weight"] * 1e-3  # Convert from grams to kilograms
        metadata["Subject"]["date_of_birth"] = datetime.strptime(subject_metadata["date"], "%Y-%m-%d")
        # There's also 'age_weeks' but I'm excluding that based on existence of DOB

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
            conversion_options=conversion_options
        )

        rmtree(self.cache_folder)

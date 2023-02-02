"""Primary base class for all IBL converters."""
import json
from datetime import datetime
from typing import Optional

from dateutil import tz
from neuroconv import ConverterPipe
from one.api import ONE
from pynwb import NWBFile


class IblConverter(ConverterPipe):
    def __init__(self, one: ONE, session: str, data_interfaces: list):
        self.one = one
        self.session = session
        super().__init__(data_interfaces=data_interfaces)

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()

        metadata_schema[
            "additionalProperties"
        ] = True  # way of manually overriding custom metadata for interfaces we don't care about validating

        return metadata_schema

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()  # Aggregates from the interfaces

        session_metadata = self.one.alyx.rest(url="sessions", action="list", id=self.session)[0]
        lab_metadata = next(lab for lab in self.one.alyx.rest("labs", "list") if lab["name"] == session_metadata["lab"])

        # TODO: include session_metadata['number'] in the extension attributes
        session_start_time = datetime.fromisoformat(session_metadata["start_time"])
        tzinfo = tz.gettz(lab_metadata["timezone"])
        session_start_time = session_start_time.replace(tzinfo=tzinfo)
        metadata["NWBFile"]["session_start_time"] = session_start_time
        metadata["NWBFile"]["session_id"] = session_metadata["id"]
        metadata["NWBFile"]["lab"] = session_metadata["lab"]
        metadata["NWBFile"]["institution"] = lab_metadata["institution"]
        metadata["NWBFile"]["protocol"] = session_metadata["task_protocol"]

        subject_metadata = self.one.alyx.rest(url="subjects", action="list", field_filter1=session_metadata["subject"])[
            0
        ]

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

        if "Subject" not in metadata:
            metadata.update(Subject=dict())

        metadata["Subject"]["description"] = json.dumps(subject_extra_metadata)

        metadata["Subject"]["subject_id"] = subject_metadata["nickname"]
        metadata["Subject"]["sex"] = subject_metadata["sex"]
        metadata["Subject"]["species"] = "Mus musculus"  # Though it's a field in their schema, it's never specified
        metadata["Subject"]["weight"] = subject_metadata["reference_weight"] * 1e-3  # Convert from grams to kilograms
        date_of_birth = datetime.strptime(subject_metadata["birth_date"], "%Y-%m-%d")
        date_of_birth = date_of_birth.replace(tzinfo=tzinfo)
        metadata["Subject"]["date_of_birth"] = date_of_birth
        # There's also 'age_weeks' but I'm excluding that based on existence of DOB

        return metadata

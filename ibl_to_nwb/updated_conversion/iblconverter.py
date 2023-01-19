from datetime import datetime

from one.api import ONE
from neuroconv import ConverterPipe


class IblConverter(ConverterPipe):
    def __init__(self, session: str, data_interfaces: list):
        self.session = session
        super().__init__(data_interfaces=data_interfaces)

    def get_metadata(self):
        metadata = super().get_metadata()  # Aggregates from the interfaces

        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)

        session_metadata = one.alyx.rest(url='sessions', action='list', id=self.session)[0]
        lab_metadata = next(lab for lab in one.alyx.rest('labs', 'list') if lab["name"] == session_metadata["lab"])

        session_description = ""
        # Might need to append more after this
        metadata["NWBFile"]["session_description"] = session_description

        metadata["NWBFile"]["session_id"] = f"{metadata['NWBFile']['session_start_time']}_session_metadata['number']"
        metadata["NWBFile"]["identifier"] = session_metadata["id"]  # The eid is more appropriate in place of a UUID
        metadata["NWBFile"]["lab"] = session_metadata["lab"]
        metadata["NWBFile"]["institution"] = lab_metadata["institution"]
        metadata["NWBFile"]["protocol"] = session_metadata['task_protocol']

        subject_metadata = one.alyx.rest(url='subjects', action='list', field_filter1=session_metadata["subject"])

        subject_description = ""
        if subject_metadata["last_water_restriction"]:
            subject_description += f"Last water restriction was on {subject_metadata['last_water_restriction']}. "
        subject_description += f"Remaining water amount was {subject_metadata['remaining_water']}. "
        subject_description += f"Expected water amount was {subject_metadata['expected_water']}. "
        subject_description += f"For more information, visit {subject_metadata['url']}."
        metadata["Subject"]["description"] = subject_description

        metadata["Subject"]["subject_id"] = subject_metadata["nickname"]
        metadata["Subject"]["sex"] = subject_metadata["sex"]
        metadata["Subject"]["species"] = "Mus musculus"  # Though it's a field in their schema, it's never specified
        metadata["Subject"]["weight"] = subject_metadata["reference_weight"] * 1e-3  # Convert from grams to kilograms
        metadata["Subject"]["date_of_birth"] = datetime.strptime(subject_metadata["date"], "%Y-%m-%d")
        # There's also 'age_weeks' but I'm excluding that based on existence of DOB

        # TODO: extra metadata that is always specified includes 'responsible_user' (anonymous hash), a UUID 'id'

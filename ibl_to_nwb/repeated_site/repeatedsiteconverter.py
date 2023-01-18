from datetime import datetime

from one.api import ONE
from neuroconv import ConverterPipe

class RepeatedSiteConverter(ConverterPipe):
    def __init__(self, session: str, data_interfaces: list):
        self.session = session
        super().__init__(data_interfaces=data_interfaces)
  
    def get_metadata(self):
        metadata = super().get_metadata()  # Aggregates from the interfaces
      
        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)
        
        # TODO: fetch session and subject-level metadata, including comments/notes
        session_metadata = one.alyx.rest(url='sessions', action='list', id=self.session)[0]

        metadata["NWBFile"]["session_id"] = f"{metadata['NWBFile']['session_start_time']}_session_metadata['number']"
        metadata["NWBFile"]["identifier"] = session_metadata["id"]  # The eid is more appropriate in place of a UUID
        metadata["NWBFile"]["session_description"] = f"Task protocal: {session_metadata['task_protocol']}"
        metadata["NWBFile"]["lab"] = session_metadata["lab"]  # might need to strip "_ucla" from churchland, other looks OK
        # metadata["NWBFile"]["institution"] = ...  # Need to form a mapping from unique lab names to institution
        metadata["NWBFile"]["experiment_description"] = "..."  # Hardcode paper abstract
        metadata["NWBFile"]["related_publications"] = "..." # Hardcode paper DOI for these sessions


        subject_metadata = one.alyx.rest(url='subjects', action='list', field_filter1=session_metadata["subject"])
        
        metadata["Subject"]["subject_id"] = subject_metadata["nickname"]
        metadata["Subject"]["description"] = f"{subject_metadata['description']}. For more information, visit {subject_metadata['url']}."  # TODO: check if any description is not empty
        if subject_metadata["genotype"]:
            metadata["Subject"]["genotype"] = 1  # TODO: check if this is ever not empty
        metadata["Subject"]["sex"] = subject_metadata["sex"]  # TODO: make sure all subjects adhere to DANDI requirements
        subject_species = subject_metadata["species"] or ""
        metadata["Subject"]["species"] = subject_species
        metadata["Subject"]["subject_id"] = 1
        metadata["Subject"]["weight"] = subject_metadata["reference_weight"]  # TODO: need to check units
        metadata["Subject"]["date_of_birth"] = datetime.strptime(subject_metadata["date"], "%Y-%m-%d") # TODO: check if this is same format string all the time
        if subject_metadata["strain"]:  # TODO: there's also 'line', how to reconcile?
            metadata["Subject"]["strain"] = subject_metadata["strain"] # TODO: check if this is ever not None
        
        # TODO: extra metadata includes 'litter', 'source', 'responsible_user' (anonymous hash), a UUID 'id', 'alive'
        # and water-related things  'last_water_restriction', 'expected_water', 'remaining_water'
        # There's also 'age_weeks' but I'm excluding that based on existence of DOB (need to check if always present though)
        
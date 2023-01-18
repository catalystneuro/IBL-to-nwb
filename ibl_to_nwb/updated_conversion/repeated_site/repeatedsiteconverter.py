from one.api import ONE
from neuroconv import ConverterPipe

class RepeatedSiteConverter(ConverterPipe):
    def __init__(self, session: str, data_interfaces: list):
        self.session = session
        super().__init__(data_interfaces=data_interfaces)
  
    def get_metadata(self):
        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)
        
        # TODO: fetch session and subject-level metadata, including comments/notes
from one.api import ONE

from ..iblconverter import IblConverter


class BrainwideMapConverter(IblConverter):

    def get_metadata(self):
        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)

        # TODO: fetch session and subject-level metadata, including comments/notes
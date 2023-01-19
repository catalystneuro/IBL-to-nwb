from one.api import ONE
from pynwb import NWBFile
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import BaseDataInterface


class BrainwideMapTrialsInterface(BaseDataInterface):
    def __init__(self, session: str):
        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)

        self.trials = one.load_object(id=session["id"], obj="trials", collection="alf")

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        metadata["Trials"] = dict()  # TODO: fill with descriptions
        return metadata

    def run_conversion(self, nwbfile: NWBFile, metadata: dict):
        column_name_mapping = dict(
          TODO="TODO"
        )  # TODO

        column_ordering = []  # TODO

        for start_time, stop_time in self.trials["intervals"]:
            nwbfile.add_trial(start_time=start_time, stop_time=stop_time)

        for column_name in column_ordering:
            nwbfile.add_trial_column(
                name=column_name,
                description=metadata["Trials"][column_name]["description"],
                data=self.trials[column_name],  # TODO: just wrap this step in H5DataIO if below does not work
            )
        # TODO: would like to compress these columns if set_dataio can work

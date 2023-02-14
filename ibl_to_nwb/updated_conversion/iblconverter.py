"""Primary base class for all IBL converters."""
import json
from datetime import datetime
from typing import Optional

from dateutil import tz
from ndx_ibl_metadata import IblSubject
from neuroconv import ConverterPipe
from neuroconv.tools.nwb_helpers import make_or_load_nwbfile
from neuroconv.utils import dict_deep_update
from one.api import ONE
from pynwb import NWBFile


class IblConverter(ConverterPipe):
    def __init__(self, one: ONE, session: str, data_interfaces: list, verbose: bool = True):
        self.one = one
        self.session = session
        super().__init__(data_interfaces=data_interfaces, verbose=verbose)

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()

        # way of manually overriding custom metadata for interfaces we don't care about validating
        metadata_schema["additionalProperties"] = True

        return metadata_schema

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()  # Aggregates from the interfaces

        session_metadata_list = self.one.alyx.rest(url="sessions", action="list", id=self.session)
        assert len(session_metadata_list) == 1, "More than one session metadata returned by query."
        session_metadata = session_metadata_list[0]

        lab_metadata_list = self.one.alyx.rest("labs", "list", name=session_metadata["lab"])
        assert len(lab_metadata_list) == 1, "More than one lab metadata returned by query."
        lab_metadata = lab_metadata_list[0]

        # TODO: include session_metadata['number'] in the extension attributes
        session_start_time = datetime.fromisoformat(session_metadata["start_time"])
        tzinfo = tz.gettz(lab_metadata["timezone"])
        session_start_time = session_start_time.replace(tzinfo=tzinfo)
        metadata["NWBFile"]["session_start_time"] = session_start_time
        metadata["NWBFile"]["session_id"] = session_metadata["id"]
        metadata["NWBFile"]["lab"] = session_metadata["lab"].replace("lab", "").capitalize()
        metadata["NWBFile"]["institution"] = lab_metadata["institution"]
        metadata["NWBFile"]["protocol"] = session_metadata["task_protocol"]
        # Setting publication and experiment description at project-specific converter level

        subject_metadata_list = self.one.alyx.rest("subjects", "list", nickname=session_metadata["subject"])
        assert len(subject_metadata_list) == 1, "More than one subject metadata returned by query."
        subject_metadata = subject_metadata_list[0]

        if "Subject" not in metadata:
            metadata.update(Subject=dict())

        subject_extra_metadata_name_mapping = dict(
            last_water_restriction="last_water_restriction",  # ISO
            remaining_water="remaining_water_ml",
            expected_water="expected_water_ml",
            url="url",
        )
        for ibl_key, nwb_name in subject_extra_metadata_name_mapping.items():
            if ibl_key not in subject_metadata:
                continue
            metadata["Subject"].update({nwb_name: subject_metadata[ibl_key]})

        # Subject description set at project-specific converter level
        metadata["Subject"]["subject_id"] = subject_metadata["nickname"]
        metadata["Subject"]["sex"] = subject_metadata["sex"]
        metadata["Subject"]["species"] = "Mus musculus"  # Though it's a field in their schema, it's never specified
        metadata["Subject"]["weight"] = subject_metadata["reference_weight"] * 1e-3  # Convert from grams to kilograms
        date_of_birth = datetime.strptime(subject_metadata["birth_date"], "%Y-%m-%d")
        date_of_birth = date_of_birth.replace(tzinfo=tzinfo)
        metadata["Subject"]["date_of_birth"] = date_of_birth
        # There's also 'age_weeks' but I'm excluding that based on existence of DOB

        return metadata

    def run_conversion(
        self,
        nwbfile_path: Optional[str] = None,
        nwbfile: Optional[NWBFile] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = False,
        conversion_options: Optional[dict] = None,
    ) -> NWBFile:
        """
        Run the NWB conversion over all the instantiated data interfaces.

        Parameters
        ----------
        nwbfile_path: FilePathType
            Path for where to write or load (if overwrite=False) the NWBFile.
            If specified, the context will always write to this location.
        nwbfile: NWBFile, optional
            An in-memory NWBFile object to write to the location.
        metadata: dict, optional
            Metadata dictionary with information used to create the NWBFile when one does not exist or overwrite=True.
        overwrite: bool, optional
            Whether or not to overwrite the NWBFile if one exists at the nwbfile_path.
            The default is False (append mode).
        verbose: bool, optional
            If 'nwbfile_path' is specified, informs user after a successful write operation.
            The default is True.
        conversion_options: dict, optional
            Similar to source_data, a dictionary containing keywords for each interface for which non-default
            conversion specification is requested.

        Returns
        -------
        nwbfile: NWBFile
            The in-memory NWBFile object after all conversion operations are complete.
        """
        subject_metadata = metadata.pop("Subject")
        ibl_subject = IblSubject(**subject_metadata)

        if metadata is None:
            metadata = self.get_metadata()
        self.validate_metadata(metadata=metadata)

        if conversion_options is None:
            conversion_options = dict()
        default_conversion_options = self.get_conversion_options()
        conversion_options_to_run = dict_deep_update(default_conversion_options, conversion_options)
        self.validate_conversion_options(conversion_options=conversion_options_to_run)

        with make_or_load_nwbfile(
            nwbfile_path=nwbfile_path,
            nwbfile=nwbfile,
            metadata=metadata,
            overwrite=overwrite,
            verbose=self.verbose,
        ) as nwbfile_out:
            nwbfile_out.subject = ibl_subject
            for interface_name, data_interface in self.data_interface_objects.items():
                data_interface.run_conversion(
                    nwbfile=nwbfile_out, metadata=metadata, **conversion_options_to_run.get(interface_name, dict())
                )

        return nwbfile_out

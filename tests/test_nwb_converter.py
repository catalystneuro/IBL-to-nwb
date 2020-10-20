from .utils import json_iblsession_schema, json_iblsubject_schema
from oneibl.one import ONE
from ibl_nwb import Alyx2NWBConverter
from ibl_nwb import Alyx2NWBMetadata
from ibl_nwb import NWBToIBLSession
import json
import pytest
import jsonschema


@pytest.fixture(scope='function')
def get_one_data(tmp_path):
    eid_temp = 'da188f2c-553c-4e04-879b-c9ea2d1b9a93'
    metadata_converter = Alyx2NWBMetadata(eid=eid_temp, one_obj=ONE())
    nwbsaveloc = str(tmp_path/'test.nwb')
    converter_nwb = Alyx2NWBConverter(
        metadata_obj=metadata_converter,
        saveloc=nwbsaveloc,
        save_raw=False,
        save_camera_raw=False)
    converter_nwb.run_conversion()
    converter_nwb.write_nwb()
    yield nwbsaveloc


def test_metadata_converter(tmp_path, get_one_data):
    json_session_path = tmp_path/'sessions.json'
    json_subject_path = tmp_path/'subject.json'
    nwb2ibl = NWBToIBLSession(get_one_data)
    nwb2ibl.write_json(json_session_path, 'sessions')
    nwb2ibl.write_json(json_subject_path, 'subject')
    with open(json_session_path, 'r') as a, open(json_subject_path, 'r') as b:
        session_info = json.load(a)
        subject_info = json.load(b)
        jsonschema.validate(session_info, json_iblsession_schema)
        jsonschema.validate(subject_info, json_iblsubject_schema)

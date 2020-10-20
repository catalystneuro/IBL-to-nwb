import json
from pathlib import Path

nonetype=type(None)

_schema_loc = Path(__file__).parent/'metafile.schema.json'
_iblsession_schema_loc = Path(__file__).parent/'ibl_sessions.schema.json'
_iblsubject_schema_loc = Path(__file__).parent/'ibl_subject.schema.json'
with open(_schema_loc,'r') as a, open(_iblsession_schema_loc,'r') as b, open(_iblsubject_schema_loc,'r') as c:
    json_schema = json.load(a)
    json_iblsession_schema = json.load(b)
    json_iblsubject_schema = json.load(c)

raw_file_names = ['ephysData.raw.ap','ephysData.raw.lf','ephysData.raw.nidq']
camera_raw_file_names = ['_iblrig_Camera.raw']
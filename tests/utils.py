import json
from pathlib import Path

nonetype=type(None)

_schema_loc = Path(__file__).parent/'metafile.schema.json'
with open(_schema_loc,'r') as f:
    json_schema = json.load(f)
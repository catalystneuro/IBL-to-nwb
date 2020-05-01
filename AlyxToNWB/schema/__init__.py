import json
import os
dir_path = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(dir_path, 'metafile.schema.json')) as f:
    metafile=json.load(f)
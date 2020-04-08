import json
import os
with open(os.path.join(os.getcwd(), 'metafile.schema.json')) as f:
    metafile=json.load(f)

with open(os.path.join(os.getcwd(), 'template_metafile.schema.json')) as f:
    template_metafile=json.load(f)
import json
import os
with open(os.path.join(os.getcwd(), 'metafile.schema.json')) as f:
    metafile=json.load(f)

with open(os.path.join(os.getcwd(), 'template_metafile.schema.json')) as f:
    template_metafile=json.load(f)

with open(os.path.join(os.getcwd(), 'dataset_format_list.json')) as f:
    dataset_format_list=json.load(f)
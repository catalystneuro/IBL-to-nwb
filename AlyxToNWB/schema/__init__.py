import json
import os
dir_path = os.path.dirname(os.path.realpath(__file__))
with open(os.path.join(dir_path, 'metafile.schema.json')) as f:
    metafile=json.load(f)

with open(os.path.join(dir_path, 'template_metafile.schema.json')) as f:
    template_metafile=json.load(f)

with open(os.path.join(dir_path, 'dataset_description_list.json')) as f:
    dataset_details_list=json.load(f)

with open(os.path.join(dir_path, 'alyx_subject_list.json')) as f:
    alyx_subject_list=json.load(f)
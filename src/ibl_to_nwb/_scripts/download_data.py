# %% imports
from pathlib import Path
from one.api import ONE
import sys

# %% session selection
# eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"  # a BWM eid with dual probe
# eid = "09394481-8dd2-4d5c-9327-f2753ede92d7"  # the spike timestamps issue for Heberto
eid = "6713a4a7-faed-4df2-acab-ee4e63326f8d"  # the LF timestamps issue

# %% path setup
base_path = Path.home() / "ibl_scratch"  # local directory
session_path = base_path / "ibl_conversion" / eid
cache_folder = base_path / "ibl_conversion" / eid / "cache"
one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=False,
    cache_dir=cache_folder,
)

# %% revision selection
revisions = one.list_revisions(eid)
revision = revisions[-1]  # latest revision
revision = "2025-05-06"  # the revision used for the BWM conversion

# %% inpsection
datasets = one.list_datasets(eid)
collections = one.list_collections(eid)

# %% download processed only
# datasets = one.list_datasets(eid, collection="alf*")
# for dataset in datasets:
#     one.load_dataset(eid, dataset, download_only=True)

# %% download everything
for dataset in datasets:
    one.load_dataset(eid, dataset, download_only=True)

# %% downloads just raw ephys data
# collections = one.list_collections(eid, collection="raw_ephys_data/*")
# for collection in collections:
#     datasets = one.list_datasets(eid, collection=collection)
#     for dataset in datasets:
#         one.load_dataset(eid, dataset, download_only=True)

# %% downloads just the video data
# datasets = one.list_datasets(eid, collection="raw_video_data")
# for dataset in datasets:
#     one.load_dataset(eid, dataset, download_only=True)

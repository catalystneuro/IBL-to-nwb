# %%
from pathlib import Path

from one.api import ONE

# %%
eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"  # a BWM eid with dual probe

base_path = Path.home() / "ibl_scratch"  # local directory

# Download behavior and spike sorted data for this eid
session_path = base_path / "ibl_conversion" / eid
cache_folder = base_path / "ibl_conversion" / eid / "cache"
session_one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=False,
    cache_dir=cache_folder,
)

# %% latest revision
revisions = session_one.list_revisions(eid)
revision = revisions[-1]

# %% list all datasets
datasets = session_one.list_datasets(eid)

# %% list all collections
collections = session_one.list_collections(eid)

# %%
for dataset in datasets:
    session_one.load_dataset(eid, dataset, download_only=True)

# %% downloads all raw ephys data!
collections = session_one.list_collections(eid, collection="raw_ephys_data/*")
for collection in collections:
    datasets = session_one.list_datasets(eid, collection=collection)
    for dataset in datasets:
        session_one.load_dataset(eid, dataset, download_only=True)

# %% just the video data
datasets = session_one.list_datasets(eid, collection="raw_video_data")
for dataset in datasets:
    session_one.load_dataset(eid, dataset, download_only=True)

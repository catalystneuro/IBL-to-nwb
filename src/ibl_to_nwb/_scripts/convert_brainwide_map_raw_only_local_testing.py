# %%
from pathlib import Path

from one.api import ONE

from ibl_to_nwb.converters import BrainwideMapConverter, IblSpikeGlxConverter
from ibl_to_nwb.datainterfaces import RawVideoInterface

# select eid
# -> run download_data_local first with this eid to set up the local folder structure and one cache
eid = "caa5dddc-9290-4e27-9f5e-575ba3598614"

# folders
base_path = Path.home() / "ibl_scratch"
base_path.mkdir(exist_ok=True)
nwbfiles_folder_path = base_path / "nwbfiles"
nwbfiles_folder_path.mkdir(exist_ok=True)

# Initialize IBL (ONE) client to download processed data for this session
one_cache_folder_path = base_path / "ibl_conversion" / eid / "cache"
one = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=True,
    cache_dir=one_cache_folder_path,
)

data_interfaces = []

# %% ephys
session_folder = one.eid2path(eid)
spikeglx_source_folder_path = session_folder / "raw_ephys_data"

# Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
spikeglx_subconverter = IblSpikeGlxConverter(folder_path=spikeglx_source_folder_path, one=one, eid=eid)
data_interfaces.append(spikeglx_subconverter)

# %% video
# Raw video takes some special handling
metadata_retrieval = BrainwideMapConverter(one=one, session=eid, data_interfaces=[], verbose=False)
subject_id = metadata_retrieval.get_metadata()["Subject"]["subject_id"]

pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
for pose_estimation_file in pose_estimation_files:
    camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")

    video_interface = RawVideoInterface(
        nwbfiles_folder_path=nwbfiles_folder_path,
        subject_id=subject_id,
        one=one,
        session=eid,
        camera_name=camera_name,
    )
    data_interfaces.append(video_interface)

# Run conversion
session_converter = BrainwideMapConverter(one=one, session=eid, data_interfaces=data_interfaces, verbose=False)

metadata = session_converter.get_metadata()
subject_id = metadata["Subject"]["subject_id"]

subject_folder_path = nwbfiles_folder_path / f"sub-{subject_id}"
subject_folder_path.mkdir(exist_ok=True)
nwbfile_path = subject_folder_path / f"sub-{subject_id}_ses-{eid}_desc-raw.nwb"

session_converter.run_conversion(nwbfile_path=nwbfile_path, metadata=metadata, overwrite=True)

# TODO: add some kind of raw-specific check
# check_written_nwbfile_for_consistency(one=one, nwbfile_path=nwbfile_path)

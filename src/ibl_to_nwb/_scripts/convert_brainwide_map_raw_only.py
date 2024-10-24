from pathlib import Path

from one.api import ONE

from ibl_to_nwb.converters import BrainwideMapConverter, IblSpikeGlxConverter
from ibl_to_nwb.datainterfaces import RawVideoInterface

# session_id = "d32876dd-8303-4720-8e7e-20678dc2fd71"
session_id = "caa5dddc-9290-4e27-9f5e-575ba3598614"  # a BWM session with dual probe


# Specify the revision of the pose estimation data
# Setting to 'None' will use whatever the latest released revision is
revision = None

# base_path = Path("E:/IBL")
base_path = Path.home() / "ibl_scratch"  # local directory
base_path.mkdir(exist_ok=True)
nwbfiles_folder_path = base_path / "nwbfiles"
nwbfiles_folder_path.mkdir(exist_ok=True)

# Initialize IBL (ONE) client to download processed data for this session
one_cache_folder_path = base_path / "cache"
ibl_client = ONE(
    base_url="https://openalyx.internationalbrainlab.org",
    password="international",
    silent=True,
    cache_dir=one_cache_folder_path,
)

# Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
data_interfaces = []

# spikeglx_source_folder_path = Path("D:/example_data/ephy_testing_data/spikeglx/Noise4Sam_g0")
spikeglx_subconverter = IblSpikeGlxConverter(folder_path=spikeglx_source_folder_path, one=ibl_client)
data_interfaces.append(spikeglx_subconverter)

# Raw video takes some special handling
metadata_retrieval = BrainwideMapConverter(one=ibl_client, session=session_id, data_interfaces=[], verbose=False)
subject_id = metadata_retrieval.get_metadata()["Subject"]["subject_id"]

pose_estimation_files = ibl_client.list_datasets(eid=session_id, filename="*.dlc*")
for pose_estimation_file in pose_estimation_files:
    camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")

    video_interface = RawVideoInterface(
        nwbfiles_folder_path=nwbfiles_folder_path,
        subject_id=subject_id,
        one=ibl_client,
        session=session_id,
        camera_name=camera_name,
    )
    data_interfaces.append(video_interface)

# Run conversion
session_converter = BrainwideMapConverter(
    one=ibl_client, session=session_id, data_interfaces=data_interfaces, verbose=False
)

metadata = session_converter.get_metadata()
subject_id = metadata["Subject"]["subject_id"]

subject_folder_path = nwbfiles_folder_path / f"sub-{subject_id}"
subject_folder_path.mkdir(exist_ok=True)
nwbfile_path = subject_folder_path / f"sub-{subject_id}_ses-{session_id}_desc-raw_ecephys+image.nwb"

session_converter.run_conversion(
    nwbfile_path=nwbfile_path,
    metadata=metadata,
    overwrite=True,
)

# TODO: add some kind of raw-specific check
# check_written_nwbfile_for_consistency(one=ibl_client, nwbfile_path=nwbfile_path)

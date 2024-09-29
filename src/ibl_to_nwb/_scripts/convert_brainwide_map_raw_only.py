from pathlib import Path

from neuroconv.datainterfaces import SpikeGLXRecordingInterface
from one.api import ONE

from ibl_to_nwb.converters import BrainwideMapConverter
from ibl_to_nwb.datainterfaces import RawVideoInterface

session_id = "d32876dd-8303-4720-8e7e-20678dc2fd71"

# Specify the revision of the pose estimation data
# Setting to 'None' will use whatever the latest released revision is
revision = None

base_path = Path("E:/IBL")
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

# Specify the path to the SpikeGLX files on the server
probe_1_source_folder_path = Path("D:/example_data/ephy_testing_data/spikeglx/Noise4Sam_g0")
probe_2_source_folder_path = Path(
    "D:/example_data/ephy_testing_data/spikeglx/multi_trigger_multi_gate/SpikeGLX/5-19-2022-CI0/5-19-2022-CI0_g0/"
)

ap_1_file_path = probe_1_source_folder_path / "Noise4Sam_g0_imec0/Noise4Sam_g0_t0.imec0.ap.bin"
ap_2_file_path = probe_2_source_folder_path / "5-19-2022-CI0_g0_imec0/5-19-2022-CI0_g0_t0.imec0.ap.bin"

lf_1_file_path = probe_1_source_folder_path / "Noise4Sam_g0_imec0/Noise4Sam_g0_t0.imec0.lf.bin"
lf_2_file_path = probe_2_source_folder_path / "5-19-2022-CI0_g0_imec0/5-19-2022-CI0_g0_t0.imec0.lf.bin"

# Initialize as many of each interface as we need across the streams
data_interfaces = list()

# These interfaces should always be present in source data
data_interfaces.append(SpikeGLXRecordingInterface(file_path=ap_1_file_path))
data_interfaces.append(SpikeGLXRecordingInterface(file_path=ap_2_file_path))
data_interfaces.append(SpikeGLXRecordingInterface(file_path=lf_1_file_path))
data_interfaces.append(SpikeGLXRecordingInterface(file_path=lf_2_file_path))

pose_estimation_files = ibl_client.list_datasets(eid=session_id, filename="*.dlc*")
for pose_estimation_file in pose_estimation_files:
    camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
    data_interfaces.append(
        RawVideoInterface(
            nwbfiles_folder_path=nwbfiles_folder_path, one=ibl_client, session=session_id, camera_name=camera_name
        )
    )

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

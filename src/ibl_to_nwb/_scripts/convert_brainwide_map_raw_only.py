from pathlib import Path

from brainbox.io.one import EphysSessionLoader, SpikeSortingLoader
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

# Specify the path to the SpikeGLX files on the server but use ONE API for timestamps
probe_1_source_folder_path = Path("D:/example_data/ephy_testing_data/spikeglx/Noise4Sam_g0")
probe_2_source_folder_path = Path(
    "D:/example_data/ephy_testing_data/spikeglx/multi_trigger_multi_gate/SpikeGLX/5-19-2022-CI0/5-19-2022-CI0_g0/"
)


# Initialize interfaces one probe at a time and properly align raw timestamps
ephys_session_loader = EphysSessionLoader(one=ibl_client, eid=session_id)

probe_to_imec_map = {
    "probe00": 0,
    "probe01": 1,
}

data_interfaces = list()
for probe_name, pid in ephys_session_loader.probes.items():
    spike_sorting_loader = SpikeSortingLoader(pid=pid, one=ibl_client)

    probe_index = probe_to_imec_map[probe_name]
    for band in ["ap", "lf"]:
        file_path = probe_1_source_folder_path / f"Noise4Sam_g0_imec0/Noise4Sam_g0_t0.imec{probe_index}.{band}.bin"
        interface = SpikeGLXRecordingInterface(file_path=file_path)

        # This is the syntax for aligning the raw timestamps; I cannot test this without the actual data as stored
        # on your end, so please work with Heberto if there are any problems after uncommenting

        # band_info = spike_sorting_loader.raw_electrophysiology(band=band, stream=True)
        # aligned_timestamps = spike_sorting_loader.samples2times(numpy.arange(0, band_info.ns), direction='forward')
        # interface.set_aligned_timestamps(aligned_timestamps=aligned_timestamps)

        data_interfaces.append(interface)

# Raw video take some special handling
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

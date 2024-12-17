from pathlib import Path

import numpy as np
from numpy.testing import assert_array_equal, assert_array_less
from one.api import ONE
from pandas.testing import assert_frame_equal
from pynwb import NWBHDF5IO, NWBFile
from brainbox.io.one import SpikeSortingLoader


def check_written_nwbfile_for_consistency(*, one: ONE, nwbfile_path: Path):
    """
    Check the processed-only NWB file for consistency with the equivalent calls to the ONE API.

    Parameters
    ----------
    one : ONE
        Initialized ONE client.
    nwbfile_path : Path
        Path to the NWB file.
    """
    with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
        nwbfile = io.read()
        eid = nwbfile.session_id

        # run all consistentcy checks
        _check_wheel_data(eid=eid, nwbfile=nwbfile, one=one)
        _check_lick_data(eid=eid, nwbfile=nwbfile, one=one)
        _check_roi_motion_energy_data(eid=eid, nwbfile=nwbfile, one=one)
        _check_pose_estimation_data(eid=eid, nwbfile=nwbfile, one=one)
        _check_trials_data(eid=eid, nwbfile=nwbfile, one=one)
        _check_pupil_tracking_data(eid=eid, nwbfile=nwbfile, one=one)
        _check_spike_sorting_data(eid=eid, nwbfile=nwbfile, one=one)


def _check_wheel_data(*, eid: str, one: ONE, nwbfile: NWBFile, revision: str = None):
    processing_module = nwbfile.processing["wheel"]
    wheel_position_series = processing_module.data_interfaces["CompassDirection"].spatial_series["WheelPositionSeries"]
    wheel_movement_table = processing_module.data_interfaces["WheelMovementIntervals"][:]

    # wheel position
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheel.position", collection="alf")
    data_from_NWB = wheel_position_series.data[:]
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)

    # wheel timestamps
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheel.timestamps", collection="alf")
    data_from_NWB = wheel_position_series.timestamps[:]
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)

    # wheel movement intervals
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheelMoves.intervals", collection="alf")
    data_from_NWB = wheel_movement_table[["start_time", "stop_time"]].values
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)

    # peak amplitude of wheel movement
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheelMoves.peakAmplitude", collection="alf")
    data_from_NWB = wheel_movement_table["peak_amplitude"].values
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)


def _check_lick_data(*, eid: str, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["camera"]
    lick_times_table = processing_module.data_interfaces["LickTimes"][:]

    data_from_NWB = lick_times_table["lick_time"].values
    data_from_ONE = one.load_dataset(eid, "licks.times")
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)


def _check_roi_motion_energy_data(*, eid: str, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["camera"]

    camera_views = ["body", "left", "right"]
    for view in camera_views:
        camera_motion_energy = processing_module.data_interfaces[f"{view.capitalize()}CameraMotionEnergy"]

        # data
        data_from_NWB = camera_motion_energy.data[:]
        data_from_ONE = one.load_dataset(eid, f"{view}Camera.ROIMotionEnergy", collection="alf")
        assert_array_equal(x=data_from_ONE, y=data_from_NWB)

        # timestamps
        data_from_NWB = camera_motion_energy.timestamps[:]
        data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.times", collection="alf")
        assert_array_equal(x=data_from_ONE, y=data_from_NWB)


def _check_pose_estimation_data(*, eid: str, one: ONE, nwbfile: NWBFile, revision: str = None):
    processing_module = nwbfile.processing["camera"]

    camera_views = ["body", "left", "right"]
    for view in camera_views:
        pose_estimation_container = processing_module.data_interfaces[f"PoseEstimation{view.capitalize()}Camera"]

        nodes = pose_estimation_container.nodes[:]
        for node in nodes:
            # x
            data_from_NWB = pose_estimation_container.pose_estimation_series[node].data[:][:, 0]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.dlc.pqt", collection="alf")[f"{node}_x"].values
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)

            # y
            data_from_NWB = pose_estimation_container.pose_estimation_series[node].data[:][:, 1]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.dlc.pqt", collection="alf")[f"{node}_y"].values
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)

            # confidence
            data_from_NWB = pose_estimation_container.pose_estimation_series[node].confidence[:]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.dlc.pqt", collection="alf")[
                f"{node}_likelihood"
            ].values
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)

            # timestamps
            data_from_NWB = pose_estimation_container.pose_estimation_series[node].timestamps[:]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.times", collection="alf")
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)


def _check_trials_data(*, eid: str, one: ONE, nwbfile: NWBFile):
    data_from_NWB = nwbfile.trials[:]
    data_from_ONE = one.load_dataset(eid, "_ibl_trials.table", collection="alf")
    data_from_ONE["stimOff_times"] = one.load_dataset(eid, "_ibl_trials.stimOff_times", collection="alf")
    data_from_ONE.index.name = "id"

    naming_map = {
        "start_time": "intervals_0",
        "stop_time": "intervals_1",
        "choice": "choice",
        "feedback_type": "feedbackType",
        "reward_volume": "rewardVolume",
        "contrast_left": "contrastLeft",
        "contrast_right": "contrastRight",
        "probability_left": "probabilityLeft",
        "feedback_time": "feedback_times",
        "response_time": "response_times",
        "stim_off_time": "stimOff_times",
        "stim_on_time": "stimOn_times",
        "go_cue_time": "goCue_times",
        "first_movement_time": "firstMovement_times",
    }

    # reordering and renaming the columns
    data_from_ONE = data_from_ONE[[naming_map[col] for col in data_from_NWB.columns]]
    data_from_ONE.columns = naming_map.keys()

    assert_frame_equal(left=data_from_NWB, right=data_from_ONE)


def _check_pupil_tracking_data(*, eid: str, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["camera"]

    camera_views = ["left", "right"]
    for view in camera_views:
        pupil_tracking_container = processing_module.data_interfaces[f"{view.capitalize()}PupilTracking"]

        # raw
        data_from_NWB = pupil_tracking_container.time_series[f"{view.capitalize()}RawPupilDiameter"].data[:]
        data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.features.pqt", collection="alf")[
            "pupilDiameter_raw"
        ].values
        assert_array_equal(x=data_from_ONE, y=data_from_NWB)

        # smooth
        data_from_NWB = pupil_tracking_container.time_series[f"{view.capitalize()}SmoothedPupilDiameter"].data[:]
        data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.features.pqt", collection="alf")[
            "pupilDiameter_smooth"
        ].values

        assert_array_equal(x=data_from_ONE, y=data_from_NWB)


def _check_spike_sorting_data(*, eid: str, one: ONE, nwbfile: NWBFile, revision: str = None):
    units_table = nwbfile.units[:]
    probe_names = units_table["probe_name"].unique()

    if revision is None:
        revision = one.list_revisions(session)[-1]

    spike_times = {}
    spike_clusters = {}
    cluster_uuids = {}

    # for fast spike extraction
    def get_spikes_for_cluster(spike_clusters, spike_times, cluster):
        # requires that spike_times and spike_clusters are sorted
        start_ix, stop_ix = np.searchsorted(spike_clusters, [cluster, cluster + 1])
        return np.sort(spike_times[start_ix:stop_ix])

    # get and prep data once
    for probe_name in probe_names:
        collection = f"alf/{probe_name}/pykilosort"
        spike_times[probe_name] = one.load_dataset(eid, "spikes.times", collection=collection, revision=revision)
        spike_clusters[probe_name] = one.load_dataset(eid, "spikes.clusters", collection=collection, revision=revision)
        cluster_uuids[probe_name] = one.load_dataset(eid, "clusters.uuids", collection=collection, revision=revision)

        # pre-sort for fast access
        sort_ix = np.argsort(spike_clusters[probe_name])
        spike_clusters[probe_name] = spike_clusters[probe_name][sort_ix]
        spike_times[probe_name] = spike_times[probe_name][sort_ix]

    for ix in units_table.index:
        probe_name = units_table.loc[ix, "probe_name"]
        uuid = units_table.loc[ix, "cluster_uuid"]
        spike_times_from_NWB = units_table.loc[ix, "spike_times"]

        cluster_id = np.where(cluster_uuids[probe_name] == uuid)[0][0]
        spike_times_from_ONE = get_spikes_for_cluster(spike_clusters[probe_name], spike_times[probe_name], cluster_id)

        # more verbose but slower for more than ~20 checks
        # spike_times_from_ONE = spike_times[probe_name][spike_clusters[probe_name] == cluster_id]

        # testing
        assert_array_less(np.max((spike_times_from_ONE - spike_times_from_NWB) * 30000), 1)


def _check_raw_ephys_data(*, eid: str, one: ONE, nwbfile: NWBFile, pname: str = None, band: str = "ap"):
    # data_one
    pids, pnames_one = one.eid2pid(eid)
    pidname_map = dict(zip(pnames_one, pids))
    pid = pidname_map[pname]
    spike_sorting_loader = SpikeSortingLoader(pid=pid, one=one)
    sglx_streamer = spike_sorting_loader.raw_electrophysiology(band=band, stream=True)
    data_one = sglx_streamer._raw

    pname_to_imec = {
        "probe00": "Imec0",
        "probe01": "Imec1",
    }
    imec_to_pname = dict(zip(pname_to_imec.values(), pname_to_imec.keys()))
    imecs = [key.split(band.upper())[1] for key in list(nwbfile.acquisition.keys()) if band.upper() in key]
    pnames_nwb = [imec_to_pname[imec] for imec in imecs]

    assert set(pnames_one) == set(pnames_nwb)

    # nwb ephys data
    imec = pname_to_imec[pname]
    data_nwb = nwbfile.acquisition[f"ElectricalSeries{band.upper()}{imec}"].data

    # compare number of samples in both
    n_samples_one = data_one.shape[0]
    n_samples_nwb = data_nwb.shape[0]

    assert n_samples_nwb == n_samples_one

    # draw a random set of samples and check if they are equal in value
    n_samples, n_channels = data_nwb.shape

    ix = np.column_stack(
        [
            np.random.randint(n_samples, size=10),
            np.random.randint(n_channels, size=10),
        ]
    )

    samples_nwb = np.array([data_nwb[*i] for i in ix])
    samples_one = np.array([data_one[*i] for i in ix])
    np.testing.assert_array_equal(samples_nwb, samples_one)

    # check the time stamps
    nwb_timestamps = nwbfile.acquisition[f"ElectricalSeries{band.upper()}{imec}"].timestamps[:]

    # from brainbox.io
    brainbox_timestamps = spike_sorting_loader.samples2times(np.arange(0, sglx_streamer.ns), direction="forward")
    np.testing.assert_array_equal(nwb_timestamps, brainbox_timestamps)


def _check_raw_video_data(*, eid: str, one: ONE, nwbfile: NWBFile, nwbfile_path: str):
    # timestamps
    datasets = one.list_datasets(eid, "*Camera.times*", collection="alf")
    cameras = [key for key in nwbfile.acquisition.keys() if key.endswith("Camera")]
    for camera in cameras:
        timestamps_nwb = nwbfile.acquisition[camera].timestamps[:]

        dataset = [dataset for dataset in datasets if camera.split("OriginalVideo")[1].lower() in dataset.lower()]
        timestamps_one = one.load_dataset(eid, dataset)
        np.testing.assert_array_equal(timestamps_nwb, timestamps_one)

    # values (the first 100 bytes)
    datasets = one.list_datasets(eid, collection="raw_video_data")
    cameras = [key for key in nwbfile.acquisition.keys() if key.endswith("Camera")]

    for camera in cameras:
        cam = camera.split("OriginalVideo")[1].lower()
        dataset = [dataset for dataset in datasets if cam in dataset.lower()]
        one_video_path = one.load_dataset(eid, dataset)
        with open(one_video_path, "rb") as fH:
            one_video_bytes = fH.read(100)

        nwb_video_path = nwbfile_path.parent / Path(nwbfile.acquisition[camera].external_file[:][0])
        with open(nwb_video_path, "rb") as fH:
            nwb_video_bytes = fH.read(100)

        assert one_video_bytes == nwb_video_bytes

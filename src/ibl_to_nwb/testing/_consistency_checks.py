from pathlib import Path

import numpy as np
from numpy.testing import assert_array_equal, assert_array_less
from one.api import ONE
from pandas.testing import assert_frame_equal
from pynwb import NWBHDF5IO, NWBFile


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

        _check_wheel_data(eid=eid, nwbfile=nwbfile, one=one)
        # TODO: fill in the rest of the routed calls


def _check_wheel_data(*, eid: str, one: ONE, nwbfile: NWBFile, revision: str = None):
    processing_module = nwbfile.processing["behavior"]
    wheel_position_series = processing_module.data_interfaces["CompassDirection"].spatial_series["WheelPositionSeries"]
    wheel_movement_table = nwbfile.processing["behavior"].data_interfaces["WheelMovementIntervals"][:]

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
    assert_frame_equal(left=data_from_ONE, right=data_from_NWB)

    # peak amplitude of wheel movement
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheelMoves.peakAmplitude", collection="alf")
    data_from_NWB = wheel_movement_table["peak_amplitude"].values
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)


def _check_lick_data(*, eid: str, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["behavior"]
    lick_times_table = processing_module.data_interfaces["LickTimes"][:]

    data_from_NWB = lick_times_table["lick_time"].values
    data_from_ONE = one.load_dataset(eid, "licks.times")
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)


def _check_roi_motion_energy_data(*, eid: str, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["behavior"]

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
    processing_module = nwbfile.processing["behavior"]

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
    processing_module = nwbfile.processing["behavior"]

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

        # include revision TODO FIXME this will likely change - check back in with Miles
        if revision is not None:
            collection = f"alf/{probe_name}/pykilosort/{revision}"
        else:
            collection = f"alf/{probe_name}/pykilosort"

        spike_times[probe_name] = one.load_dataset(eid, "spikes.times", collection=collection)
        spike_clusters[probe_name] = one.load_dataset(eid, "spikes.clusters", collection=collection)
        cluster_uuids[probe_name] = one.load_dataset(eid, "clusters.uuids", collection=collection)

        # pre-sort for fast access
        sort_ix = np.argsort(spike_clusters[probe_name])
        spike_clusters[probe_name] = spike_clusters[probe_name][sort_ix]
        spike_times[probe_name] = spike_times[probe_name][sort_ix]

    for ix in units_table.index:
        probe_name = units_table.loc[ix, "probe_name"]
        uuid = units_table.loc[ix, "uuid"]
        spike_times_from_NWB = units_table.loc[ix, "spike_times"]

        cluster_id = np.where(cluster_uuids[probe_name] == uuid)[0][0]
        spike_times_from_ONE = get_spikes_for_cluster(spike_clusters[probe_name], spike_times[probe_name], cluster_id)

        # more verbose but slower for more than ~20 checks
        # spike_times_from_ONE = spike_times[probe_name][spike_clusters[probe_name] == cluster_id]

        # testing
        assert_array_less(np.max((spike_times_from_ONE - spike_times_from_NWB) * 30000), 1)

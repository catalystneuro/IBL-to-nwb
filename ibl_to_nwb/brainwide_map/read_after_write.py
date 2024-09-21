import os
import numpy as np
import pandas as pd
from pathlib import Path
import h5py
from pynwb import NWBHDF5IO, NWBFile
from one.api import ONE
import logging
from typing import Optional
from numpy import testing

def check_arrays(array_a: np.ndarray, array_b: np.ndarray, full_check: bool = False):
    """checks if two arrays contain the same numerical values

    Args:
        array_a (np.ndarray): _description_
        array_b (np.ndarray): _description_
        full_check (bool, optional): If True, compares all values of the arrays. If False, checks a small subsample only. Defaults to False.
    """

    # if full check, check all samples
    if full_check:
        testing.assert_allclose(array_a, array_b)

    # check just a random subset of samples
    else:
        inds = np.random.randint(0, np.prod(array_a.shape), size=10)
        testing.assert_allclose(np.ravel(array_a)[inds], np.ravel(array_b)[inds])
        


def check_series(series_a: pd.Series, series_b: pd.Series, full_check: bool = False):
    """checks if two pd.Series contain the same numerical values. Checks if NaN values are the same.

    Args:
        series_a (pd.Series): _description_
        series_b (pd.Series): _description_
        full_check (bool, optional): _description_. Defaults to False.
    """

    # -> all of this functionality is now moved to check_arrays()
    # this function as of now is obsolete but kept for potential future integration
    
    check_arrays(series_a.values, series_b.values, full_check=full_check)


def check_tables(table_a: pd.DataFrame, table_b: pd.DataFrame, naming_map: dict = None, full_check: bool = False):
    """checks if two pd.DataFrames contain the same numerical values. Performs an "is in" comparison: checks if data of table_a is present in table_b.

    Args:
        table_a (pd.DataFrame): _description_
        table_b (pd.DataFrame): _description_
        naming_map (dict, optional): if naming map is given, it is used to map the names of columns of table_a to those of table_b. Defaults to None, checks if columns are identical.
        full_check (bool, optional): _description_. Defaults to False.
    """
    # convert column names if necessary
    if naming_map is not None:
        table_a_cols = table_a.columns
        table_b_cols = [naming_map[col] for col in table_a.columns]
    else:
        # if no map is given, columns have to be the same (but not in the same order)
        assert np.all([col in table_b.columns for col in table_a.columns])
        table_a_cols = table_a.columns
        table_b_cols = table_a.columns

    for col_a, col_b in zip(table_a_cols, table_b_cols):
        check_series(table_a[col_a], table_b[col_b], full_check=full_check)


def test_WheelInterface(
    nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
):
    """_summary_

    Args:
        nwbfile (NWBFile): nwbfile object
        one (ONE): ONE object
        eid (str): ONE experiment uuid
        full_check (bool, optional): if True, verifies all values, if False, performs checks on a sample. Defaults to False.
        verbose (bool, optional): _description_. Defaults to False.
        revision (str, optional): _description_. Defaults to None.
    """

    # wheel position
    data_nwb = (
        nwbfile.processing["behavior"].data_interfaces["CompassDirection"].spatial_series["WheelPositionSeries"].data[:]
    )
    data_one = one.load_dataset(eid, "_ibl_wheel.position", collection="alf")
    check_arrays(data_nwb, data_one, full_check=full_check)

    # wheel timestamps
    data_nwb = (
        nwbfile.processing["behavior"]
        .data_interfaces["CompassDirection"]
        .spatial_series["WheelPositionSeries"]
        .timestamps[:]
    )
    data_one = one.load_dataset(eid, "_ibl_wheel.timestamps", collection="alf")
    check_arrays(data_nwb, data_one, full_check=full_check)

    # wheel moves
    table = nwbfile.processing["behavior"].data_interfaces["WheelMovementIntervals"][:]

    # intervals
    data_nwb = table[["start_time", "stop_time"]].values
    data_one = one.load_dataset(eid, "_ibl_wheelMoves.intervals", collection="alf")
    check_arrays(data_nwb, data_one, full_check=full_check)

    # peak amplitude
    data_nwb = table["peak_amplitude"].values
    data_one = one.load_dataset(eid, "_ibl_wheelMoves.peakAmplitude", collection="alf")
    check_arrays(data_nwb, data_one, full_check=full_check)


def test_LickInterface(
    nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
):
    """read-after-write test for the datainterface `LickInterface`.
    TODO DOCME

    Args:
        nwbfile (NWBFile): nwbfile object.
        one (ONE): ONE object.
        eid (str): experiment uuid / equivalent to session_id
    """
    table = nwbfile.processing["behavior"].data_interfaces["LickTimes"][:]
    data_nwb = table["lick_time"].values
    data_one = one.load_dataset(eid, "licks.times")
    check_arrays(data_nwb, data_one, full_check=full_check)


def test_RoiMotionEnergyInterface(
    nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
):
    """read-after-write test for the datainterface `RoiMotionEnergyInterface`.
    TODO DOCME

    Args:
        nwbfile (NWBFile): nwbfile object.
        one (ONE): ONE object.
        eid (str): experiment uuid / equivalent to session_id
    """
    camera_views = ["body", "left", "right"]

    for view in camera_views:
        # data
        data_nwb = nwbfile.processing["behavior"].data_interfaces["%sCameraMotionEnergy" % view.capitalize()].data[:]
        data_one = one.load_dataset(eid, "%sCamera.ROIMotionEnergy" % view, collection="alf")
        check_arrays(data_nwb, data_one, full_check=full_check)

        # timestamps
        data_nwb = (
            nwbfile.processing["behavior"].data_interfaces["%sCameraMotionEnergy" % view.capitalize()].timestamps[:]
        )
        data_one = one.load_dataset(eid, "_ibl_%sCamera.times" % view, collection="alf")
        check_arrays(data_nwb, data_one, full_check=full_check)


def test_IblPoseEstimationInterface(
    nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
):
    """read-after-write test for the datainterface `IblPoseEstimationInterface`.
    TODO DOCME

    Args:
        nwbfile (NWBFile): nwbfile object.
        one (ONE): ONE object.
        eid (str): experiment uuid / equivalent to session_id
    """

    camera_views = ["body", "left", "right"]

    for view in camera_views:
        nodes = nwbfile.processing["behavior"].data_interfaces["PoseEstimation%sCamera" % view.capitalize()].nodes[:]

        for node in nodes:
            # x
            data_nwb = (
                nwbfile.processing["behavior"]
                .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
                .pose_estimation_series[node]
                .data[:][:, 0]
            )
            data_one = one.load_dataset(eid, "_ibl_%sCamera.dlc.pqt" % view, collection="alf")["%s_x" % node].values
            check_arrays(data_nwb, data_one, full_check=full_check)

            # y
            data_nwb = (
                nwbfile.processing["behavior"]
                .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
                .pose_estimation_series[node]
                .data[:][:, 1]
            )
            data_one = one.load_dataset(eid, "_ibl_%sCamera.dlc.pqt" % view, collection="alf")["%s_y" % node].values
            check_arrays(data_nwb, data_one, full_check=full_check)

            # confidence
            data_nwb = (
                nwbfile.processing["behavior"]
                .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
                .pose_estimation_series[node]
                .confidence[:]
            )
            data_one = one.load_dataset(eid, "_ibl_%sCamera.dlc.pqt" % view, collection="alf")[
                "%s_likelihood" % node
            ].values
            check_arrays(data_nwb, data_one, full_check=full_check)

            # timestamps
            data_nwb = (
                nwbfile.processing["behavior"]
                .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
                .pose_estimation_series[node]
                .timestamps[:]
            )
            data_one = one.load_dataset(eid, "_ibl_%sCamera.times" % view, collection="alf")
            check_arrays(data_nwb, data_one, full_check=full_check)


def test_BrainwideMapTrialsInterface(
    nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
):
    """read-after-write test for the datainterface `BrainwideMapTrialsInterface`.
    TODO DOCME

    Args:
        nwbfile (NWBFile): nwbfile object.
        one (ONE): ONE object.
        eid (str): experiment uuid / equivalent to session_id
    """

    data_nwb = nwbfile.trials[:]
    data_one = one.load_dataset(eid, "_ibl_trials.table", collection="alf")

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
        #   'stim_off_time': '',
        "stim_on_time": "stimOn_times",
        "go_cue_time": "goCue_times",
        "first_movement_time": "firstMovement_times",
    }
    naming_map = {v: k for k, v in naming_map.items()}

    check_tables(data_one, data_nwb, naming_map=naming_map)


def test_PupilTrackingInterface(
    nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
):
    """read-after-write test for the datainterface `PupilTrackingInterface`.
    TODO DOCME

    Args:
        nwbfile (NWBFile): nwbfile object.
        one (ONE): ONE object.
        eid (str): experiment uuid / equivalent to session_id
    """

    camera_views = ["left", "right"]
    for view in camera_views:
        # raw
        data_nwb = (
            nwbfile.processing["behavior"]
            .data_interfaces["%sPupilTracking" % view.capitalize()]
            .time_series["%sRawPupilDiameter" % view.capitalize()]
            .data[:]
        )
        data_one = one.load_dataset(eid, "_ibl_%sCamera.features.pqt" % view, collection="alf")[
            "pupilDiameter_raw"
        ].values

        check_arrays(data_nwb, data_one, full_check=full_check)

        # smooth
        data_nwb = (
            nwbfile.processing["behavior"]
            .data_interfaces["%sPupilTracking" % view.capitalize()]
            .time_series["%sSmoothedPupilDiameter" % view.capitalize()]
            .data[:]
        )
        data_one = one.load_dataset(eid, "_ibl_%sCamera.features.pqt" % view, collection="alf")[
            "pupilDiameter_smooth"
        ].values

        check_arrays(data_nwb, data_one, full_check=full_check)


def test_IblSortingInterface(
    nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
):
    """_summary_

    Args:
        nwbfile (_type_): _description_
        one (_type_): _description_
        eid (_type_): _description_
        full_check (bool, optional): _description_. Defaults to False.
        revision (_type_, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """

    units_table = nwbfile.units[:]
    probe_names = units_table["probe_name"].unique()

    if full_check:
        inds = units_table.index
    else:
        inds = units_table.sample(20).index

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

    for ix in inds:
        probe_name = units_table.loc[ix, "probe_name"]
        uuid = units_table.loc[ix, "uuid"]
        nwb_spike_times = units_table.loc[ix, "spike_times"]

        cluster_id = np.where(cluster_uuids[probe_name] == uuid)[0][0]
        one_spike_times = get_spikes_for_cluster(spike_clusters[probe_name], spike_times[probe_name], cluster_id)

        # more verbose but slower for more than ~20 checks
        # one_spike_times = spike_times[probe_name][spike_clusters[probe_name] == cluster_id]
        
        # testing
        testing.assert_array_less(np.max((one_spike_times - nwb_spike_times) * 30000), 1)

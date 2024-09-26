from pathlib import Path

from numpy.testing import assert_array_equal
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


def _check_wheel_data(*, eid: str, one: ONE, nwbfile: NWBFile):
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


# def _check_lick_data(*, eid: str, one: ONE, nwbfile: NWBFile):
#     """read-after-write test for the datainterface `LickInterface`.
#     TODO DOCME
#     Args:
#         nwbfile (NWBFile): nwbfile object.
#         one (ONE): ONE object.
#         eid (str): experiment uuid / equivalent to session_id
#     """
#     table = nwbfile.processing["behavior"].data_interfaces["LickTimes"][:]
#     data_nwb = table["lick_time"].values
#     data_one = one.load_dataset(eid, "licks.times")
#     check_arrays(data_nwb, data_one, full_check=full_check)
#
#
# def test_RoiMotionEnergyInterface(
#     nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
# ):
#     """read-after-write test for the datainterface `RoiMotionEnergyInterface`.
#     TODO DOCME
#     Args:
#         nwbfile (NWBFile): nwbfile object.
#         one (ONE): ONE object.
#         eid (str): experiment uuid / equivalent to session_id
#     """
#     camera_views = ["body", "left", "right"]
#
#     for view in camera_views:
#         # data
#         data_nwb = nwbfile.processing["behavior"].data_interfaces["%sCameraMotionEnergy" % view.capitalize()].data[:]
#         data_one = one.load_dataset(eid, "%sCamera.ROIMotionEnergy" % view, collection="alf")
#         check_arrays(data_nwb, data_one, full_check=full_check)
#
#         # timestamps
#         data_nwb = (
#             nwbfile.processing["behavior"].data_interfaces["%sCameraMotionEnergy" % view.capitalize()].timestamps[:]
#         )
#         data_one = one.load_dataset(eid, "_ibl_%sCamera.times" % view, collection="alf")
#         check_arrays(data_nwb, data_one, full_check=full_check)
#
#
# def test_IblPoseEstimationInterface(
#     nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
# ):
#     """read-after-write test for the datainterface `IblPoseEstimationInterface`.
#     TODO DOCME
#     Args:
#         nwbfile (NWBFile): nwbfile object.
#         one (ONE): ONE object.
#         eid (str): experiment uuid / equivalent to session_id
#     """
#
#     camera_views = ["body", "left", "right"]
#
#     for view in camera_views:
#         nodes = nwbfile.processing["behavior"].data_interfaces["PoseEstimation%sCamera" % view.capitalize()].nodes[:]
#
#         for node in nodes:
#             # x
#             data_nwb = (
#                 nwbfile.processing["behavior"]
#                 .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
#                 .pose_estimation_series[node]
#                 .data[:][:, 0]
#             )
#             data_one = one.load_dataset(eid, "_ibl_%sCamera.dlc.pqt" % view, collection="alf")["%s_x" % node].values
#             check_arrays(data_nwb, data_one, full_check=full_check)
#
#             # y
#             data_nwb = (
#                 nwbfile.processing["behavior"]
#                 .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
#                 .pose_estimation_series[node]
#                 .data[:][:, 1]
#             )
#             data_one = one.load_dataset(eid, "_ibl_%sCamera.dlc.pqt" % view, collection="alf")["%s_y" % node].values
#             check_arrays(data_nwb, data_one, full_check=full_check)
#
#             # confidence
#             data_nwb = (
#                 nwbfile.processing["behavior"]
#                 .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
#                 .pose_estimation_series[node]
#                 .confidence[:]
#             )
#             data_one = one.load_dataset(eid, "_ibl_%sCamera.dlc.pqt" % view, collection="alf")[
#                 "%s_likelihood" % node
#             ].values
#             check_arrays(data_nwb, data_one, full_check=full_check)
#
#             # timestamps
#             data_nwb = (
#                 nwbfile.processing["behavior"]
#                 .data_interfaces["PoseEstimation%sCamera" % view.capitalize()]
#                 .pose_estimation_series[node]
#                 .timestamps[:]
#             )
#             data_one = one.load_dataset(eid, "_ibl_%sCamera.times" % view, collection="alf")
#             check_arrays(data_nwb, data_one, full_check=full_check)
#
#
# def test_BrainwideMapTrialsInterface(
#     nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
# ):
#     """read-after-write test for the datainterface `BrainwideMapTrialsInterface`.
#     TODO DOCME
#     Args:
#         nwbfile (NWBFile): nwbfile object.
#         one (ONE): ONE object.
#         eid (str): experiment uuid / equivalent to session_id
#     """
#
#     data_nwb = nwbfile.trials[:]
#     data_one = one.load_dataset(eid, "_ibl_trials.table", collection="alf")
#
#     naming_map = {
#         "start_time": "intervals_0",
#         "stop_time": "intervals_1",
#         "choice": "choice",
#         "feedback_type": "feedbackType",
#         "reward_volume": "rewardVolume",
#         "contrast_left": "contrastLeft",
#         "contrast_right": "contrastRight",
#         "probability_left": "probabilityLeft",
#         "feedback_time": "feedback_times",
#         "response_time": "response_times",
#         #   'stim_off_time': '',
#         "stim_on_time": "stimOn_times",
#         "go_cue_time": "goCue_times",
#         "first_movement_time": "firstMovement_times",
#     }
#     naming_map = {v: k for k, v in naming_map.items()}
#
#     check_tables(data_one, data_nwb, naming_map=naming_map)
#
#
# def test_PupilTrackingInterface(
#     nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
# ):
#     """read-after-write test for the datainterface `PupilTrackingInterface`.
#     TODO DOCME
#     Args:
#         nwbfile (NWBFile): nwbfile object.
#         one (ONE): ONE object.
#         eid (str): experiment uuid / equivalent to session_id
#     """
#
#     camera_views = ["left", "right"]
#     for view in camera_views:
#         # raw
#         data_nwb = (
#             nwbfile.processing["behavior"]
#             .data_interfaces["%sPupilTracking" % view.capitalize()]
#             .time_series["%sRawPupilDiameter" % view.capitalize()]
#             .data[:]
#         )
#         data_one = one.load_dataset(eid, "_ibl_%sCamera.features.pqt" % view, collection="alf")[
#             "pupilDiameter_raw"
#         ].values
#
#         check_arrays(data_nwb, data_one, full_check=full_check)
#
#         # smooth
#         data_nwb = (
#             nwbfile.processing["behavior"]
#             .data_interfaces["%sPupilTracking" % view.capitalize()]
#             .time_series["%sSmoothedPupilDiameter" % view.capitalize()]
#             .data[:]
#         )
#         data_one = one.load_dataset(eid, "_ibl_%sCamera.features.pqt" % view, collection="alf")[
#             "pupilDiameter_smooth"
#         ].values
#
#         check_arrays(data_nwb, data_one, full_check=full_check)
#
#
# def test_IblSortingInterface(
#     nwbfile: NWBFile, one: ONE, eid: str, full_check: bool = False, verbose: bool = False, revision: str = None
# ):
#     """_summary_
#     Args:
#         nwbfile (_type_): _description_
#         one (_type_): _description_
#         eid (_type_): _description_
#         full_check (bool, optional): _description_. Defaults to False.
#         revision (_type_, optional): _description_. Defaults to None.
#     Returns:
#         _type_: _description_
#     """
#
#     units_table = nwbfile.units[:]
#     probe_names = units_table["probe_name"].unique()
#
#     if full_check:
#         inds = units_table.index
#     else:
#         inds = units_table.sample(20).index
#
#     spike_times = {}
#     spike_clusters = {}
#     cluster_uuids = {}
#
#     # for fast spike extraction
#     def get_spikes_for_cluster(spike_clusters, spike_times, cluster):
#         # requires that spike_times and spike_clusters are sorted
#         start_ix, stop_ix = np.searchsorted(spike_clusters, [cluster, cluster + 1])
#         return np.sort(spike_times[start_ix:stop_ix])
#
#     # get and prep data once
#     for probe_name in probe_names:
#
#         # include revision TODO FIXME this will likely change - check back in with Miles
#         if revision is not None:
#             collection = f"alf/{probe_name}/pykilosort/{revision}"
#         else:
#             collection = f"alf/{probe_name}/pykilosort"
#
#         spike_times[probe_name] = one.load_dataset(eid, "spikes.times", collection=collection)
#         spike_clusters[probe_name] = one.load_dataset(eid, "spikes.clusters", collection=collection)
#         cluster_uuids[probe_name] = one.load_dataset(eid, "clusters.uuids", collection=collection)
#
#         # pre-sort for fast access
#         sort_ix = np.argsort(spike_clusters[probe_name])
#         spike_clusters[probe_name] = spike_clusters[probe_name][sort_ix]
#         spike_times[probe_name] = spike_times[probe_name][sort_ix]
#
#     for ix in inds:
#         probe_name = units_table.loc[ix, "probe_name"]
#         uuid = units_table.loc[ix, "uuid"]
#         nwb_spike_times = units_table.loc[ix, "spike_times"]
#
#         cluster_id = np.where(cluster_uuids[probe_name] == uuid)[0][0]
#         one_spike_times = get_spikes_for_cluster(spike_clusters[probe_name], spike_times[probe_name], cluster_id)
#
#         # more verbose but slower for more than ~20 checks
#         # one_spike_times = spike_times[probe_name][spike_clusters[probe_name] == cluster_id]
#
#         # testing
#         testing.assert_array_less(np.max((one_spike_times - nwb_spike_times) * 30000), 1)

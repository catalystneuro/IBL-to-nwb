from pathlib import Path
import os
import numpy as np
from brainbox.io.one import SessionLoader, SpikeSortingLoader
from numpy.testing import assert_array_equal, assert_array_less
from one.api import ONE
from pandas.testing import assert_frame_equal
from pynwb import NWBHDF5IO, NWBFile
# from brainwidemap.bwm_loading import bwm_query
from ibl_to_nwb.fixtures import load_fixtures
from iblatlas.atlas import AllenAtlas

import logging
_logger = logging.getLogger('ibl_to_nwb')

def eid2pid(eid, bwm_df):
    _df = bwm_df.set_index("eid").loc[[eid]]
    pids = []
    pnames = []
    for i, row in _df.iterrows():
        pids.append(row.pid)
        pnames.append(row.probe_name)
    return pids, pnames

def pid2eid(pid, bwm_df):
    _df = bwm_df.set_index("pid").loc[pid]
    return _df["eid"], _df["probe_name"]


def check_nwbfile_for_consistency(*, one: ONE, nwbfile_path: Path):
    _logger.debug(f"verifying {nwbfile_path} for consistency")
    with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
        nwbfile = io.read()
        
        if 'processed_behavior+ecephys' in str(nwbfile_path):
            # run all consistentcy checks for processed data
            _check_trials_data(nwbfile=nwbfile, one=one)
            _check_wheel_data(nwbfile=nwbfile, one=one)
            _check_spike_sorting_data(nwbfile=nwbfile, one=one)
            # these are "optional"
            for data_interface_name in nwbfile.processing['camera'].data_interfaces.keys():
                if 'Pose' in data_interface_name:
                    _check_pose_estimation_data(nwbfile=nwbfile, one=one)
                if 'Motion' in data_interface_name:
                    _check_roi_motion_energy_data(nwbfile=nwbfile, one=one)
                if 'Pupil' in data_interface_name:
                    _check_pupil_tracking_data(nwbfile=nwbfile, one=one)
                if 'Lick' in data_interface_name:
                    _check_lick_data(nwbfile=nwbfile, one=one)

        if 'raw_ecephys+image' in str(nwbfile_path):
            # run checks for raw files
            _check_raw_ephys_data(one=one, nwbfile=nwbfile)
            _check_raw_video_data(one=one, nwbfile=nwbfile, nwbfile_path=nwbfile_path)


def _check_wheel_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    load_kwargs = dict(collection='alf', revision=revision)

    processing_module = nwbfile.processing["wheel"]
    wheel_position_series = processing_module.data_interfaces["CompassDirection"].spatial_series["WheelPositionSeries"]
    wheel_movement_table = processing_module.data_interfaces["WheelMovementIntervals"][:]

    # wheel position
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheel.position", **load_kwargs)
    data_from_NWB = wheel_position_series.data[:]
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)

    # wheel timestamps
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheel.timestamps", **load_kwargs)
    data_from_NWB = wheel_position_series.timestamps[:]
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)

    # wheel movement intervals
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheelMoves.intervals", **load_kwargs)
    data_from_NWB = wheel_movement_table[["start_time", "stop_time"]].values
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)

    # peak amplitude of wheel movement
    data_from_ONE = one.load_dataset(id=eid, dataset="_ibl_wheelMoves.peakAmplitude", **load_kwargs)
    data_from_NWB = wheel_movement_table["peak_amplitude"].values
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)
    _logger.debug(f"wheel data passed")


def _check_lick_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    load_kwargs = dict(collection='alf', revision=revision)

    processing_module = nwbfile.processing["camera"]
    lick_times_table = processing_module.data_interfaces["LickTimes"][:]

    data_from_NWB = lick_times_table["lick_time"].values
    data_from_ONE = one.load_dataset(eid, "licks.times", **load_kwargs)
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)
    _logger.debug(f"lick data passed")


def _check_roi_motion_energy_data(*, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["camera"]
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    load_kwargs = dict(collection='alf', revision=revision)

    camera_views = ["body", "left", "right"]
    for view in camera_views:
        data_interface_name = f"{view.capitalize()}CameraMotionEnergy"
        if data_interface_name in processing_module.data_interfaces.keys():
            camera_motion_energy = processing_module.data_interfaces[data_interface_name]

            # data
            data_from_NWB = camera_motion_energy.data[:]
            data_from_ONE = one.load_dataset(eid, f"{view}Camera.ROIMotionEnergy", **load_kwargs)
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)

            # timestamps
            data_from_NWB = camera_motion_energy.timestamps[:]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.times", **load_kwargs)
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)
            _logger.debug(f"roi motion energy for {view} passed")
        # _logger.debug(f"roi motion energy for {view} passed")


def _check_pose_estimation_data(*, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["camera"]
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    load_kwargs = dict(collection='alf', revision=revision)

    camera_views = ["body", "left", "right"]
    for view in camera_views:
        data_interface_name = f"PoseEstimation{view.capitalize()}Camera"
        if data_interface_name in processing_module.data_interfaces.keys():
            pose_estimation_container = processing_module.data_interfaces[data_interface_name]

            nodes = pose_estimation_container.nodes[:]
            for node in nodes:
                # x
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].data[:][:, 0]
                data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.dlc.pqt", **load_kwargs)[
                    f"{node}_x"
                ].values
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)

                # y
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].data[:][:, 1]
                data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.dlc.pqt", **load_kwargs)[
                    f"{node}_y"
                ].values
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)

                # confidence
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].confidence[:]
                data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.dlc.pqt", **load_kwargs)[
                    f"{node}_likelihood"
                ].values
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)

                # timestamps
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].timestamps[:]
                data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.times", **load_kwargs)
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)
            _logger.debug(f"pose estimation for {view} passed")


def _check_trials_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision

    data_from_NWB = nwbfile.trials[:].reset_index(drop=True)
    session_loader = SessionLoader(one=one, eid=eid, revision=revision)
    session_loader.load_trials()
    data_from_ONE = session_loader.trials.reset_index(drop=True)

    # data_from_ONE = one.load_dataset(eid, "_ibl_trials.table", collection="alf")
    # data_from_ONE["stimOff_times"] = one.load_dataset(eid, "_ibl_trials.stimOff_times", collection="alf")
    # data_from_ONE.index.name = "id"

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
    _logger.debug(f"trials table passed")


def _check_pupil_tracking_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    load_kwargs = dict(collection='alf', revision=revision)

    processing_module = nwbfile.processing["camera"]

    camera_views = ["left", "right"]
    for view in camera_views:
        data_interface_name = f"{view.capitalize()}PupilTracking"
        if data_interface_name in processing_module.data_interfaces.keys():
            pupil_tracking_container = processing_module.data_interfaces[data_interface_name]

            # raw
            data_from_NWB = pupil_tracking_container.time_series[f"{view.capitalize()}RawPupilDiameter"].data[:]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.features.pqt", **load_kwargs)[
                "pupilDiameter_raw"
            ].values
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)

            # smooth
            data_from_NWB = pupil_tracking_container.time_series[f"{view.capitalize()}SmoothedPupilDiameter"].data[:]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.features.pqt", **load_kwargs)[
                "pupilDiameter_smooth"
            ].values

            assert_array_equal(x=data_from_ONE, y=data_from_NWB)
            _logger.debug(f"pupil data for {view} passed")


def _check_spike_sorting_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    bwm_df = load_fixtures.load_bwm_df()
    pids, probe_names = eid2pid(eid, bwm_df)
    pids = dict(zip(probe_names, pids))

    units_table = nwbfile.units[:]
    # probe_names = units_table["probe_name"].unique()

    # spike_times = {}
    # spike_clusters = {}
    # cluster_uuids = {}
    spikes = {}
    clusters = {}

    # for fast spike extraction
    def get_spikes_for_cluster(spike_clusters, spike_times, cluster):
        # requires that spike_times and spike_clusters are sorted
        start_ix, stop_ix = np.searchsorted(spike_clusters, [cluster, cluster + 1])
        return np.sort(spike_times[start_ix:stop_ix])

    # get and prep data
    for probe_name in probe_names:
        spike_sorting_loader = SpikeSortingLoader(eid=eid, pname=probe_name, pid=pids[probe_name], one=one)
        spikes_, clusters_, _ = spike_sorting_loader.load_spike_sorting(revision=revision)
        spikes[probe_name] = spikes_
        clusters[probe_name] = clusters_

        # pre-sort for fast access
        sort_ix = np.argsort(spikes[probe_name]["clusters"])
        spikes[probe_name]["times"] = spikes[probe_name]["times"][sort_ix]
        spikes[probe_name]["clusters"] = spikes[probe_name]["clusters"][sort_ix]

    for ix in units_table.index:
        probe_name, uuid = units_table.loc[ix, ["probe_name", "cluster_uuid"]]
        assert uuid in clusters[probe_name]["uuids"].values
        spike_times_from_NWB = units_table.loc[ix, "spike_times"]

        cluster_id = np.where(clusters[probe_name]["uuids"] == uuid)[0][0]
        spikes[probe_name]["clusters"]
        spike_times_from_ONE = get_spikes_for_cluster(
            spikes[probe_name]["clusters"], spikes[probe_name]["times"], cluster_id
        )

        # more verbose but slower for more than ~20 checks
        # spike_times_from_ONE = spike_times[probe_name][spike_clusters[probe_name] == cluster_id]

        # testing
        assert_array_less(np.max((spike_times_from_ONE - spike_times_from_NWB) * 30000), 1)
    _logger.debug(f"spike times passed")

    # test unit locations
    units_nwb = nwbfile.units[:]
    units_df = load_fixtures.load_bwm_units_df()
    units_ids = units_df.groupby('eid').get_group(eid)['uuids']
    
    # beryl
    one_beryl = units_df.set_index('uuids').loc[units_ids, 'Beryl']
    nwb_beryl = units_nwb.set_index('cluster_uuid').loc[units_ids, 'beryl_location']
    np.testing.assert_array_equal(one_beryl.values, nwb_beryl.values)

    # allen
    atlas = AllenAtlas()
    atlas_ids = units_df.set_index('uuids').loc[units_ids, 'atlas_id']
    one_allen = np.array([atlas.regions.id2acronym(i)[0] for i in atlas_ids])
    nwb_allen = units_nwb.set_index('cluster_uuid').loc[units_ids, 'allen_location'].values
    np.testing.assert_array_equal(one_allen, nwb_allen)
    _logger.debug(f"brain regions for units passed")


def _check_raw_ephys_data(*, one: ONE, nwbfile: NWBFile, pname: str = None, band: str = "ap"):
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    
    # comparing probe names
    # get the pid/pname mapping for this eid
    bwm_df = load_fixtures.load_bwm_df()
    pids, pnames_one = eid2pid(eid, bwm_df)
    # pidname_map = dict(zip(pnames_one, pids))
    # pidname_map = bwm_df.set_index("eid").loc[eid][["probe_name", "pid"]].to_dict()
    # pnames_one = bwm_df.set_index("eid").loc[eid]['probe_name'].values

    pname_to_imec = {
        "probe00": "Imec0",
        "probe01": "Imec1",
    }

    imec_to_pname = dict(zip(pname_to_imec.values(), pname_to_imec.keys()))
    imecs = [key.split(band.upper())[1] for key in list(nwbfile.acquisition.keys()) if band.upper() in key]
    pnames_nwb = [imec_to_pname[imec] for imec in imecs]

    assert set(pnames_one) == set(pnames_nwb)

    # comparing ephys samples
    for pname in pnames_nwb:
        for band in ["lf", "ap"]:
            # pid = pidname_map[pname]
            spike_sorting_loader = SpikeSortingLoader(eid=eid, pname=pname, one=one, revision=revision)
            # stream = False if "USE_SDSC_ONE" in os.environ else True
            stream = False # FIXME now forcing this to run only locally on SDSC
            sglx_streamer = spike_sorting_loader.raw_electrophysiology(band=band, stream=stream, revision=revision)
            data_one = sglx_streamer._raw

            # nwb ephys data
            imec = pname_to_imec[pname]
            data_nwb = nwbfile.acquisition[f"ElectricalSeries{band.upper()}{imec}"].data

            # compare number of samples in both
            n_samples_one = data_one.shape[0]
            n_samples_nwb = data_nwb.shape[0]

            assert n_samples_nwb == n_samples_one

            # draw a random set of samples and check if they are equal in value
            n_samples, n_channels = data_nwb.shape

            ix = np.random.randint(n_samples, size=10)

            for i in ix:
                samples_nwb = data_nwb[i]
                samples_one = data_one[int(i)][:-1]  # excluding the digital channel
                np.testing.assert_array_equal(samples_nwb, samples_one)

                # samples_nwb = np.array([data_nwb[*i] for i in ix])
                # samples_one = np.array([data_one[*i] for i in ix])
                # np.testing.assert_array_equal(samples_nwb, samples_one)
            _logger.debug(f"raw ephys data for {pname}/{band} passed")
            
            # check the time stamps
            nwb_timestamps = nwbfile.acquisition[f"ElectricalSeries{band.upper()}{imec}"].get_timestamps()[:]

            # from brainbox.io
            brainbox_timestamps = spike_sorting_loader.samples2times(
                np.arange(0, n_samples_one), direction="forward", band=band
            )

            np.testing.assert_array_equal(nwb_timestamps, brainbox_timestamps)
            _logger.debug(f"ephys data timestamps for {pname}/{band} passed")


def _check_raw_video_data(*, one: ONE, nwbfile: NWBFile, nwbfile_path: str):
    eid = nwbfile.session_id
    revision = nwbfile.lab_meta_data['ibl_bwm_metadata'].revision
    load_kwargs = dict(collection='alf', revision=revision)
    
    # timestamps
    datasets = one.list_datasets(eid, "*Camera.times*", collection=load_kwargs["collection"])
    cameras = [key for key in nwbfile.acquisition.keys() if key.endswith("Camera")]
    for camera in cameras:
        timestamps_nwb = nwbfile.acquisition[camera].timestamps[:]

        dataset = [dataset for dataset in datasets if camera.split("OriginalVideo")[1].lower() in dataset.lower()]
        timestamps_one = one.load_dataset(eid, dataset, revision=revision)
        np.testing.assert_array_equal(timestamps_nwb, timestamps_one)
        _logger.debug(f"video timestamps for {camera} passed")

    # values (the first 100 bytes)
    datasets = one.list_datasets(eid, collection="raw_video_data")
    cameras = [key for key in nwbfile.acquisition.keys() if key.endswith("Camera")]

    for camera in cameras:
        cam = camera.split("OriginalVideo")[1].lower()
        dataset = [dataset for dataset in datasets if cam in dataset.lower()]
        one_video_path = one.load_dataset(eid, dataset)
        with open(one_video_path, "rb") as fH:
            one_video_bytes = fH.read(100)

        
        nwb_video_path = Path(nwbfile_path).parent / Path(nwbfile_path).parent.parts[-1] / Path(nwbfile.acquisition[camera].external_file[:][0])
        with open(nwb_video_path, "rb") as fH:
            nwb_video_bytes = fH.read(100)

        assert one_video_bytes == nwb_video_bytes
        _logger.debug(f"video values for {camera} passed")

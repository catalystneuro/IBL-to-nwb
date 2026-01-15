import logging
from pathlib import Path

import numpy as np
from brainbox.io.one import SessionLoader, SpikeSortingLoader
from iblatlas.atlas import AllenAtlas
from numpy.testing import assert_array_equal, assert_array_less
from one.api import ONE
from pandas.testing import assert_frame_equal
from pynwb import NWBHDF5IO, NWBFile
import pandas as pd

# from brainwidemap.bwm_loading import bwm_query
from ibl_to_nwb.fixtures import load_fixtures
from ibl_to_nwb.datainterfaces._brainwide_map_trials_interface import IBL_TO_NWB_COLUMNS


def get_logger(eid: str):
    # helper to get the eid specific logger
    _logger = logging.getLogger(f"bwm_to_nwb.{eid}")
    return _logger


def eid2pid(eid, bwm_df):
    # helper to replace the online one functionality
    _df = bwm_df.set_index("eid").loc[[eid]]
    pids = []
    pnames = []
    for i, row in _df.iterrows():
        pids.append(row.pid)
        pnames.append(row.probe_name)
    return pids, pnames


def pid2eid(pid, bwm_df):
    # helper to replace the online one functionality
    _df = bwm_df.set_index("pid").loc[pid]
    return _df["eid"], _df["probe_name"]


def check_nwbfile_for_consistency(*, one: ONE, nwbfile_path: Path):
    # _logger.debug(f"verifying {nwbfile_path} for consistency")
    with NWBHDF5IO(path=nwbfile_path, mode="r") as io:
        nwbfile = io.read()

        # run all consistentcy checks for processed data
        if "processed_behavior+ecephys" in str(nwbfile_path):
            _check_trials_data(nwbfile=nwbfile, one=one)
            _check_wheel_data(nwbfile=nwbfile, one=one)
            _check_spike_sorting_data(nwbfile=nwbfile, one=one)

            # these are not always present for all datasets, therefore check for existence first
            if "camera" in nwbfile.processing:
                for data_interface_name in nwbfile.processing["camera"].data_interfaces.keys():
                    if "Pose" in data_interface_name:
                        _check_pose_estimation_data(nwbfile=nwbfile, one=one)
                    if "Motion" in data_interface_name:
                        _check_roi_motion_energy_data(nwbfile=nwbfile, one=one)
                    if "Pupil" in data_interface_name:
                        _check_pupil_tracking_data(nwbfile=nwbfile, one=one)
                    if "Lick" in data_interface_name:
                        _check_lick_data(nwbfile=nwbfile, one=one)

        # run checks for raw files
        if "raw_ecephys+image" in str(nwbfile_path):
            _check_raw_ephys_data(one=one, nwbfile=nwbfile)
            _check_raw_video_data(one=one, nwbfile=nwbfile, nwbfile_path=nwbfile_path)


def _check_wheel_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    load_kwargs = dict(collection="alf", revision=revision)

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
    _logger.debug("wheel data passed")


def _check_lick_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    load_kwargs = dict(collection="alf", revision=revision)

    processing_module = nwbfile.processing["camera"]
    lick_times_table = processing_module.data_interfaces["LickTimes"][:]

    data_from_NWB = lick_times_table["lick_time"].values
    data_from_ONE = one.load_dataset(eid, "licks.times", **load_kwargs)
    assert_array_equal(x=data_from_ONE, y=data_from_NWB)
    _logger.debug("lick data passed")


def _check_roi_motion_energy_data(*, one: ONE, nwbfile: NWBFile):
    processing_module = nwbfile.processing["camera"]
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    load_kwargs = dict(collection="alf", revision=revision)

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
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    load_kwargs = dict(collection="alf", revision=revision)

    session_loader = SessionLoader(one=one, eid=eid, revision=revision)
    session_loader.load_pose(tracker='dlc') # TODO to be externalized

    camera_views = ["body", "left", "right"]
    for view in camera_views:
        pose_data = session_loader.pose[f'{view}Camera']
        data_interface_name = f"PoseEstimation{view.capitalize()}Camera"
        if data_interface_name in processing_module.data_interfaces.keys():
            pose_estimation_container = processing_module.data_interfaces[data_interface_name]

            nodes = pose_estimation_container.nodes[:]
            for node in nodes:
                # x
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].data[:][:, 0]
                data_from_ONE = pose_data[f"{node}_x"].values
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)

                # y
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].data[:][:, 1]
                data_from_ONE = pose_data[f"{node}_y"].values
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)

                # confidence
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].confidence[:]
                data_from_ONE = pose_data[f"{node}_likelihood"].values
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)

                # timestamps
                data_from_NWB = pose_estimation_container.pose_estimation_series[node].timestamps[:]
                data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.times", **load_kwargs)
                assert_array_equal(x=data_from_ONE, y=data_from_NWB)
            _logger.debug(f"pose estimation for {view} passed")


def _apply_tidy_trials_transformations(trials: pd.DataFrame) -> pd.DataFrame:
    """
    Apply tidy data transformations to trials DataFrame for consistency checking.

    This mirrors the transformations in BrainwideMapTrialsInterface._apply_tidy_transformations
    to enable consistency checking between ONE source data and NWB output.

    Transformations applied:
    - choice: -1/0/+1 -> "left"/"no_go"/"right"
    - feedbackType: -1/+1 -> True/False (is_mouse_rewarded)
    - contrastLeft/contrastRight -> gabor_stimulus_contrast + gabor_stimulus_side

    Note: block_index and block_type are excluded from consistency checking because they are
    deterministically computed from probabilityLeft. If probabilityLeft matches, these
    derived columns will automatically be correct.
    """
    trials = trials.copy()

    # Transform choice: -1 -> "left", 0 -> "no_go", +1 -> "right"
    choice_map = {-1.0: "left", 0.0: "no_go", 1.0: "right"}
    trials["choice"] = trials["choice"].map(choice_map)

    # Transform feedbackType to boolean: +1 -> True (rewarded), -1 -> False (not rewarded)
    trials["is_mouse_rewarded"] = trials["feedbackType"] == 1.0

    # Consolidate contrast columns into gabor_stimulus_contrast + gabor_stimulus_side
    #
    # IBL encodes stimulus side using contrastLeft/contrastRight columns where one column
    # contains the contrast value and the other is NaN. This comes from the IBL extraction
    # pipeline (ibllib/io/extractors/biased_trials.py ContrastLR extractor):
    #
    #   contrastLeft = [t['contrast'] if np.sign(t['position']) < 0 else np.nan ...]
    #   contrastRight = [t['contrast'] if np.sign(t['position']) > 0 else np.nan ...]
    #
    # The stimulus position determines which column gets the value:
    #   - position < 0 (left, -35 deg): contrastLeft = contrast, contrastRight = NaN
    #   - position > 0 (right, +35 deg): contrastRight = contrast, contrastLeft = NaN
    #
    # This applies to ALL contrast levels including 0% contrast trials. For example:
    #   - Left 25% trial: contrastLeft=0.25, contrastRight=NaN
    #   - Right 0% trial: contrastLeft=NaN, contrastRight=0.0
    def compute_gabor_stimulus_side(left, right):
        # Determine side based on which column has a non-NaN value
        left_valid = not pd.isna(left)
        right_valid = not pd.isna(right)
        if left_valid and not right_valid:
            return "left"
        elif right_valid and not left_valid:
            return "right"
        elif left_valid and right_valid:
            # Both have values - should not happen in valid IBL data, but handle defensively
            return "left" if left >= right else "right"
        else:
            return "none"  # Both NaN - unexpected, indicates corrupted data

    def compute_gabor_stimulus_contrast(left, right):
        # Return the non-NaN contrast value as percentage (could be 0 for 0% contrast trials)
        # Multiply by 100 and round to 2 decimal places
        if not pd.isna(left) and (pd.isna(right) or left > 0):
            return round(left * 100, 2)
        elif not pd.isna(right):
            return round(right * 100, 2)
        else:
            return np.nan  # Both NaN - unexpected

    trials["gabor_stimulus_side"] = [
        compute_gabor_stimulus_side(l, r) for l, r in zip(trials["contrastLeft"], trials["contrastRight"])
    ]
    trials["gabor_stimulus_contrast"] = [
        compute_gabor_stimulus_contrast(l, r) for l, r in zip(trials["contrastLeft"], trials["contrastRight"])
    ]

    return trials


def _check_trials_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision

    data_from_NWB = nwbfile.trials[:].reset_index(drop=True)
    session_loader = SessionLoader(one=one, eid=eid, revision=revision)
    session_loader.load_trials()
    data_from_ONE = session_loader.trials.reset_index(drop=True)

    # Apply tidy transformations to match NWB format
    data_from_ONE = _apply_tidy_trials_transformations(data_from_ONE)

    # Use imported mapping (IBL -> NWB), invert it for NWB -> IBL lookup
    nwb_to_ibl = {nwb: ibl for ibl, nwb in IBL_TO_NWB_COLUMNS.items()}

    # Exclude derived columns from validation (block_type, block_index are deterministically
    # computed from probabilityLeft, so checking them is redundant)
    derived_columns = {"block_type", "block_index"}
    nwb_columns_to_check = [col for col in data_from_NWB.columns if col not in derived_columns]

    # reordering and renaming the columns
    data_from_ONE = data_from_ONE[[nwb_to_ibl[col] for col in nwb_columns_to_check]]
    data_from_NWB = data_from_NWB[nwb_columns_to_check]
    data_from_ONE.columns = nwb_columns_to_check

    assert_frame_equal(left=data_from_NWB, right=data_from_ONE)
    _logger.debug("trials table passed")


def _check_pupil_tracking_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    load_kwargs = dict(collection="alf", revision=revision)

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

            # timestamps
            timestamps_from_NWB = pupil_tracking_container.time_series[f"{view.capitalize()}RawPupilDiameter"].timestamps[:]
            timestamps_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.times.npy", **load_kwargs)
            assert_array_equal(x=timestamps_from_NWB, y=timestamps_from_ONE)

            # smooth
            data_from_NWB = pupil_tracking_container.time_series[f"{view.capitalize()}SmoothedPupilDiameter"].data[:]
            data_from_ONE = one.load_dataset(eid, f"_ibl_{view}Camera.features.pqt", **load_kwargs)[
                "pupilDiameter_smooth"
            ].values
            assert_array_equal(x=data_from_ONE, y=data_from_NWB)

            _logger.debug(f"pupil data for {view} passed")


def _check_spike_sorting_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    bwm_df = load_fixtures.load_bwm_df()

    raw_ephys_datasets = one.list_datasets(eid=eid, collection="raw_ephys_data/*")
    probe_names = set([filename.split("/")[1] for filename in raw_ephys_datasets])
    # pids, probe_names = eid2pid(eid, bwm_df)
    # pids = dict(zip(probe_names, pids))

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
        spike_sorting_loader = SpikeSortingLoader(eid=eid, pname=probe_name, one=one)
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
        # spikes[probe_name]["clusters"]
        spike_times_from_ONE = get_spikes_for_cluster(
            spikes[probe_name]["clusters"], spikes[probe_name]["times"], cluster_id
        )

        # more verbose but slower for more than ~20 checks
        # spike_times_from_ONE = spike_times[probe_name][spike_clusters[probe_name] == cluster_id]

        # testing - the original assertion
        assert_array_less(np.max((spike_times_from_ONE - spike_times_from_NWB) * 30000), 1.0)
        # assert_array_less(np.max(np.absolute(spike_times_from_ONE - spike_times_from_NWB)), 1e-6)
    _logger.debug("spike times passed")

    # test unit locations
    units_nwb = nwbfile.units[:]
    units_df = load_fixtures.load_bwm_units_df()
    units_ids = units_df.groupby("eid").get_group(eid)["uuids"]

    # beryl
    # one_beryl = units_df.set_index("uuids").loc[units_ids, "Beryl"]
    # nwb_beryl = units_nwb.set_index("cluster_uuid").loc[units_ids, "beryl_location"]
    # np.testing.assert_array_equal(one_beryl.values, nwb_beryl.values)

    # allen
    atlas = AllenAtlas()
    atlas_ids = units_df.set_index("uuids").loc[units_ids, "atlas_id"]
    one_allen = np.array([atlas.regions.id2acronym(i)[0] for i in atlas_ids])
    nwb_allen = units_nwb.set_index("cluster_uuid").loc[units_ids, "allen_location"].values
    np.testing.assert_array_equal(one_allen, nwb_allen)
    _logger.debug("brain regions for units passed")


def _check_raw_ephys_data(*, one: ONE, nwbfile: NWBFile, pname: str = None, band: str = "ap"):
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision

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
            # forcing this to run only with one in local mode (as required for SDSC)
            stream = False
            # stream = False if "USE_SDSC_ONE" in os.environ else True
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
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    load_kwargs = dict(collection="alf", revision=revision)

    # timestamps
    datasets = one.list_datasets(eid, "*Camera.times*", collection=load_kwargs["collection"])
    cameras = [key for key in nwbfile.acquisition.keys() if key.endswith("Camera")]
    for camera in cameras:
        timestamps_nwb = nwbfile.acquisition[camera].timestamps[:]

        dataset = [dataset for dataset in datasets if camera.split("Video")[1].lower() in dataset.lower()]
        timestamps_one = one.load_dataset(eid, dataset, revision=revision)
        np.testing.assert_array_equal(timestamps_nwb, timestamps_one)
        _logger.debug(f"video timestamps for {camera} passed")

    # values (the first 100 bytes)
    datasets = one.list_datasets(eid, collection="raw_video_data")
    cameras = [key for key in nwbfile.acquisition.keys() if key.endswith("Camera")]

    for camera in cameras:
        cam = camera.split("Video")[1].lower()
        (dataset,) = [dataset for dataset in datasets if cam in dataset.lower() and "timestamps" not in dataset]
        one_video_path = one.load_dataset(eid, dataset)
        with open(one_video_path, "rb") as fH:
            one_video_bytes = fH.read(100)

        nwb_video_path = (
            Path(nwbfile_path).parent
            / Path(nwbfile_path).parent.parts[-1]
            / Path(nwbfile.acquisition[camera].external_file[:][0])
        )
        with open(nwb_video_path, "rb") as fH:
            nwb_video_bytes = fH.read(100)

        assert one_video_bytes == nwb_video_bytes
        _logger.debug(f"video values for {camera} passed")


def _check_passive_data(*, one: ONE, nwbfile: NWBFile):
    eid = nwbfile.session_id
    _logger = get_logger(eid)
    revision = nwbfile.lab_meta_data["ibl_metadata"].revision
    load_kwargs = dict(collection="alf", revision=revision)

    # check which datasets are present
    datasets = one.list_datasets(eid)

    # has passive epochs
    if "alf/_ibl_passivePeriods.intervalsTable.csv" in datasets:
        passive_intervals_df = one.load_dataset(eid, "alf/_ibl_passivePeriods.intervalsTable.csv")
        epochs = nwbfile.intervals['epochs'][:]
        for protocol, group in epochs.groupby('protocol_name'):
            if protocol != 'experiment':
                start_time, stop_time = passive_intervals_df[protocol]
                assert group['start_time'].values == start_time
                assert group['stop_time'].values == stop_time

    # has replay
    if "alf/_ibl_passiveGabor.table.csv" in datasets:
        taskreplay_events_df = one.load_dataset(eid, "alf/_ibl_passiveStims.table.csv")
        one_passive_df = []

        for col_name in ['valve','tone','noise']:
            cols = [col for col in taskreplay_events_df.columns if col.startswith(col_name)]
            df = taskreplay_events_df[cols].copy()
            df.loc[:, 'stim_type'] = col_name
            df.columns = ['start_time','stop_time','stim_type']
            one_passive_df.append(df)
        one_passive_df = pd.concat(one_passive_df,axis=0).sort_values('start_time').reset_index(drop=True)
        one_passive_df.index.name = 'id'
        nwb_passive_df = nwbfile.processing['passive_protocol'].data_interfaces['passive_task_replay'][:]
        assert_frame_equal(one_passive_df, nwb_passive_df)

        one_gabor_events_df = one.load_dataset(eid, "alf/_ibl_passiveGabor.table.csv")
        drop_cols = [col for col in one_gabor_events_df.columns if col.startswith('Unnamed')]
        one_gabor_events_df = one_gabor_events_df.drop(drop_cols, axis=1)
        one_gabor_events_df.index.name = 'id'
        one_gabor_events_df = one_gabor_events_df.rename(columns={'start':'start_time', 'stop':'stop_time'})
        nwb_gabor_events_df = nwbfile.processing['passive_protocol'].data_interfaces['gabor_table'][:]
        assert_frame_equal(one_gabor_events_df, nwb_gabor_events_df)

    # receptrive field mapping
    if "alf/_ibl_passiveRFM.times.npy" in datasets:
        nwb_timestamps = nwbfile.processing['passive_protocol'].data_interfaces['rfm_stim'].timestamps[:]
        one_timestamps = one.load_dataset(eid, "alf/_ibl_passiveRFM.times.npy")
        assert_array_equal(nwb_timestamps, one_timestamps)
        nwb_data = nwbfile.processing['passive_protocol'].data_interfaces['rfm_stim'].data[:]
        path = one.load_dataset(eid, "raw_passive_data/_iblrig_RFMapStim.raw.bin")
        one_data = np.fromfile(path, dtype=np.uint8).reshape((one_timestamps.shape[0], 15, 15))
        assert_array_equal(nwb_data, one_data)
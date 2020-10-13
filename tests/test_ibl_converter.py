import datetime
import shutil
import tempfile
from ndx_ibl_metadata import IblSessionData, IblSubject, IblProbes
from pynwb import NWBHDF5IO, NWBFile
import h5py
from collections import Iterable
from .utils import *
from oneibl.one import ONE
from AlyxToNWB.alyx_to_nwb_converter import Alyx2NWBConverter
from AlyxToNWB.alyx_to_nwb_metadata import Alyx2NWBMetadata
import json, yaml
from pathlib import Path
import pytest
import numpy as np
from hdmf.common.table import VectorData
import pandas as pd
from pynwb.behavior import Position, SpatialSeries
import pickle
import h5py


@pytest.fixture(scope='module')
def build_converter(tmp_path):
    eid_temp = 'da188f2c-553c-4e04-879b-c9ea2d1b9a93'
    metadata_converter = Alyx2NWBMetadata(eid=eid_temp, one_obj=ONE())
    yield metadata_converter
    yield metadata_converter


def test_metadata_converter(tmp_path, build_converter):
    converter_name_json = tmp_path/'temp.json'
    converter_name_yaml = tmp_path/'temp.yaml'
    full_metadata = build_converter.complete_metadata
    # check base keys
    for i in full_metadata:
        assert i in metafile_base_fields
    # check nwbfile related fields:
    for i, j in nwbfile_required_dict.items():
        assert i in full_metadata['NWBFile']
        if isinstance(j, Iterable):
            assert type(full_metadata['NWBFile'][i]) in j
        else:
            assert type(full_metadata['NWBFile'][i]) == j
        _ = full_metadata['NWBFile'].pop(i)
    check_args(full_metadata['NWBFile'], nwbfile_optional_dict)
    # check sessions,subject, probes fields:
    check_args(full_metadata['IBLSessionsData'], sessions_data_dict)
    check_args(full_metadata['IBLSubject'], subject_data_dict)
    assert isinstance(full_metadata['Probes'], list)
    for probe in full_metadata['Probes']:
        check_args(probe, probes_data_dict)
    # check trials, units, electrode_table:
    assert isinstance(full_metadata['Trials'], list)
    for i in full_metadata['Trials']:
        check_args(i, dt_columns_data_dict)
    assert isinstance(full_metadata['Units'], list)
    for i in full_metadata['Units']:
        check_args(i, dt_columns_data_dict)
    assert isinstance(full_metadata['ElectrodeTable'], list)
    for i in full_metadata['ElectrodeTable']:
        check_args(i, dt_columns_data_dict)
    # Ecephys: Device:
    assert 'Device' in full_metadata['Ecephys']
    assert isinstance(full_metadata['Ecephys']['Device'], list)
    for i in full_metadata['Ecephys']['Device']:
        check_args(i, device_data_dict)
    # Ecephys: ElectrodeGroup:
    assert 'ElectrodeGroup' in full_metadata['Ecephys']
    assert isinstance(full_metadata['Ecephys']['ElectrodeGroup'], list)
    for i in full_metadata['Ecephys']['ElectrodeGroup']:
        check_args(i, electrode_group_data_dict)
    # Ecephys: Ecephys:
    assert 'Ecephys' in full_metadata['Ecephys']
    assert isinstance(full_metadata['Ecephys']['Ecephys'], dict)
    for i, j in full_metadata['Ecephys']['Ecephys'].items():
        assert isinstance(j, list)
        for j1 in j:
            if i == 'Spectrum':
                _ = j1.pop('timestamps')
                _ = j1.pop('data')
                check_args(j1, spectrum_data_dict)
            else:
                check_args(j1, timeseries_data_dict)
    # Acquisition:
    assert isinstance(full_metadata['Acquisition'], dict)
    for i, j in full_metadata['Acquisition'].items():
        assert isinstance(j, list)
        for j1 in j:
            if i == 'DecompositionSeries':
                check_args(j1, decomposition_data_dict)
            else:
                check_args(j1, timeseries_data_dict)
    # Behavior:
    assert isinstance(full_metadata['Behavior'], dict)
    for i, j in full_metadata['Behavior'].items():
        assert isinstance(j, dict)
        for i1, j1 in j.items():
            assert i1 in ['time_series', 'interval_series', 'spatial_series']
            for j11 in j1:
                check_args(j11, timeseries_data_dict)
    # save yaml/json files and check types:
    build_converter.write_metadata(converter_name_json, savetype='.json')
    build_converter.write_metadata(converter_name_yaml, savetype='.yaml')
    with open(converter_name_json, 'r') as f:
        json_load = json.load(f)
        assert isinstance(json_load, dict)
        assert 'session_start_time' in json_load['NWBFile']
        assert 'date_of_birth' in json_load['IBLSubject']
    with open(converter_name_yaml, 'r') as f:
        yaml_load = yaml.load(f)
        assert isinstance(yaml_load, dict)
        assert 'session_start_time' in json_load['NWBFile']
        assert 'date_of_birth' in json_load['IBLSubject']


def test_nwb_converter(tmp_path, build_converter):
    nwbfileloc = tmp_path/'test.nwb'
    full_metadata = build_converter.complete_metadata
    converter_nwb1 = Alyx2NWBConverter(
        nwb_metadata_file=build_converter.complete_metadata,
        saveloc=nwbfileloc,
        save_raw=False,
        save_camera_raw=False)
    converter_nwb2 = Alyx2NWBConverter(
        metadata_obj=build_converter,
        saveloc=nwbfileloc,
        save_raw=False,
        save_camera_raw=False)
    # test run conversion:
    converter_nwb1.run_conversion()
    # test writing nwb roundtrip:
    converter_nwb1.write_nwb()

    with NWBHDF5IO(nwbfileloc, 'r') as io:
        nwbfile = io.read()
        # test nwbfile fields:
        for i, j in full_metadata['NWBFile'].items():
            assert getattr(nwbfile, i, False) is not False
            if not i == 'session_start_time':
                if isinstance(getattr(nwbfile, i), h5py.Dataset):
                    assert all(getattr(nwbfile, i)[()] == j)
                else:
                    if i == 'experimenter':
                        assert list(getattr(nwbfile, i)) == j
                    else:
                        assert getattr(nwbfile, i) == j
        # test iblsubject:
        for i, j in full_metadata['IBLSubject'].items():
            assert getattr(nwbfile.subject, i, False) is not False
            if not 'date' in i:
                if isinstance(getattr(nwbfile.subject, i), h5py.Dataset):
                    assert all(getattr(nwbfile.subject, i)[()] == j)
                else:
                    assert getattr(nwbfile.subject, i) == j
        # test iblsessions:
        for i, j in full_metadata['IBLSessionsData'].items():
            assert nwbfile.lab_meta_data['Ibl_session_data'].fields.get(i) is not None
            if isinstance(nwbfile.lab_meta_data['Ibl_session_data'].fields.get(i), h5py.Dataset):
                assert all(nwbfile.lab_meta_data['Ibl_session_data'].fields.get(i)[()] == j)
            else:
                if i not in ['json', 'extended_qc']:
                    assert nwbfile.lab_meta_data['Ibl_session_data'].fields.get(i) == j
                else:
                    assert len(set(j).difference(set(nwbfile.lab_meta_data['Ibl_session_data'].fields.get(i)))) == 0
        # test probes:
        if full_metadata['Ecephys']['Ecephys'].get('Device'):
            device_dict = full_metadata['Ecephys']['Ecephys']['Device']
            name = device_dict.pop('name')
            assert name in nwbfile.devices
            assert nwbfile.devices[name].fields == device_dict
        for probe in full_metadata['Probes']:
            name = probe.pop('name')
            assert name in nwbfile.devices
            traj_est = nwbfile.devices[name].fields.pop('trajectory_estimate')
            traj_est0 = probe.pop('trajectory_estimate')
            assert all(traj_est[()] == traj_est0)
            assert nwbfile.devices[name].fields == probe
        # test trials:
        for trlcol in full_metadata['Trials']:
            assert trlcol['name'] in nwbfile.trials.colnames
            dtcol = [nwbfile.trials.columns[no] for no, i in enumerate(nwbfile.trials.colnames)
                     if trlcol['name'] == i and isinstance(nwbfile.trials.columns[no], VectorData)][0]
            # assert dtcol.description==trlcol['description']
            if trlcol['data'].split('.')[-1] != 'intervals':
                data = converter_nwb1._loaded_datasets.get(trlcol['data']).data
                assert data == dtcol.data.values
        # test units:
        unit_data_len = sum(converter_nwb1._data_attrs_dump['unit_table_length'])
        for unitcol in full_metadata['Units']:
            assert unitcol['name'] in nwbfile.units.colnames
            dtcol = [nwbfile.units.columns[no] for no, i in enumerate(nwbfile.units.colnames) if unitcol['name'] == i][
                0]
            assert dtcol.description == unitcol['description']
            assert dtcol.data.shape[0] == unit_data_len
            # -- check consistency of only clusters.* and except the df: clusters.metrics
            if unitcol['data'].split('.')[-1] not in ['metrics', 'times'] and unitcol['data'].split('.')[
                0] == 'clusters':
                data = np.concatenate(converter_nwb1._loaded_datasets.get(unitcol['data']).data)
                assert data == dtcol.data.values
        # test electrode group:
        for group in full_metadata['Ecephys']['ElectrodeGroup']:
            name = group.pop('name')
            assert name in nwbfile.electrode_groups
            assert group == nwbfile.electrode_groups[name]
        # test electrode table:
        elec_tbl_len = sum(converter_nwb1._data_attrs_dump['electrode_table_length'])
        for electrode in full_metadata['ElectrodeTable']:
            assert electrode['name'] in nwbfile.electrodes.colnames
            dtcol = [nwbfile.electrodes.columns[no] for no, i in enumerate(nwbfile.electrodes.colnames) if
                     electrode['name'] == i][0]
            assert dtcol.description == electrode['description']
            assert dtcol.data.shape[0] == elec_tbl_len  # -- only checking length
        # test timeseries ephys:
        ephys_datasets = nwbfile.processing['Ecephys'].data_interfaces
        for i, j in full_metadata['Ecephys']['Ecephys'].items():
            for j1 in j:
                assert j1['data'] in converter_nwb1._data_attrs_dump.keys()
                field_names = converter_nwb1._data_attrs_dump[j1['data']]
                for k in field_names:
                    assert k in ephys_datasets.keys()
                    if 'Spectrum' in i:
                        assert isinstance(ephys_datasets[k], Spectrum)  # TODO: validate Spectrum dataset further
                    else:
                        assert isinstance(ephys_datasets[k], TimeSeries)
        # test behavior:
        ephys_datasets = nwbfile.processing['Behavior'].data_interfaces
        for i, j in full_metadata['Behavior'].items():
            assert i in ephys_datasets.keys()
            for i1, j1 in j.items():
                for j11 in j1:
                    assert j11['name'] in getattr(ephys_datasets[i], i1).keys()
                    if i == 'Position':
                        assert isinstance(getattr(ephys_datasets[i], i1)[j11['name']], SpatialSeries)
                    else:
                        assert isinstance(getattr(ephys_datasets[i], i1)[j11['name']], TimeSeries)
        # test acquisition: test only presence of names of datasets:
        acq_datasets = nwbfile.processing['Acquisition']
        for i, j in full_metadata['Acquisition'].items():
            for j1 in j:
                assert any([True for h in acq_datasets.keys() if j1['name'] in h])

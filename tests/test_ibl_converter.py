from pynwb import NWBHDF5IO, TimeSeries
from .utils import json_schema, raw_file_names, camera_raw_file_names
from oneibl.one import ONE
from ibl_to_nwb import Alyx2NWBConverter
from ibl_to_nwb import Alyx2NWBMetadata
import json, yaml
import pytest
from numpy.testing import assert_array_equal
from hdmf.common.table import VectorData
from pynwb.behavior import SpatialSeries
import h5py
import jsonschema
from ndx_spectrum import Spectrum
from datetime import datetime
import requests


@pytest.fixture(scope='module')
def build_converter():
    eid_temp = 'da188f2c-553c-4e04-879b-c9ea2d1b9a93'
    try:
        metadata_converter = Alyx2NWBMetadata(eid=eid_temp, one_obj=ONE())
    except (requests.exceptions.HTTPError, ConnectionError) as e:
        metadata_converter = e
    yield metadata_converter


def test_metadata_converter(tmp_path, build_converter):
    converter_name_json = tmp_path/'temp.json'
    converter_name_yaml = tmp_path/'temp.yaml'
    if isinstance(build_converter, Exception):
        print(str(build_converter))
        return
    full_metadata = build_converter.complete_metadata
    full_metadata['NWBFile']['session_start_time'] = datetime.strftime(
        full_metadata['NWBFile']['session_start_time'], '%Y-%m-%dT%X')
    full_metadata['IBLSubject']['date_of_birth'] = datetime.strftime(
        full_metadata['IBLSubject']['date_of_birth'], '%Y-%m-%dT%X')
    jsonschema.validate(full_metadata, json_schema)
    # save yaml/json files and check types:
    build_converter.write_metadata(converter_name_json, savetype='.json')
    build_converter.write_metadata(converter_name_yaml, savetype='.yaml')
    with open(converter_name_json, 'r') as f:
        json_load = json.load(f)
        jsonschema.validate(json_load, json_schema)
    with open(converter_name_yaml, 'r') as f:
        yaml_load = yaml.load(f)
        jsonschema.validate(json_load, json_schema)


def test_nwb_converter(tmp_path, build_converter):
    nwbfileloc = str(tmp_path/'test.nwb')
    if isinstance(build_converter, Exception):
        print(str(build_converter))
        return
    full_metadata = build_converter.complete_metadata
    save_raw = False
    save_camera_raw = False
    converter_nwb1 = Alyx2NWBConverter(
        nwb_metadata_file=build_converter.complete_metadata,
        saveloc=nwbfileloc,
        save_raw=save_raw,
        save_camera_raw=save_camera_raw)
    converter_nwb2 = Alyx2NWBConverter(
        metadata_obj=build_converter,
        saveloc=nwbfileloc,
        save_raw=save_raw,
        save_camera_raw=save_camera_raw)
    converter_nwb1.run_conversion()
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
            if trlcol['data'].split('.')[-1] != 'intervals':
                data = converter_nwb1._loaded_datasets.get(trlcol['data']).data[0]
                assert_array_equal(data, dtcol.data[()])
        # test units:
        unit_data_len = sum(converter_nwb1._data_attrs_dump['unit_table_length'])
        dt_column_names = [getattr(nwbfile.units, i['name']).name for i in full_metadata['Units']]
        for no, unitcol in enumerate(full_metadata['Units']):
            assert unitcol['name'] == dt_column_names[no]
        assert nwbfile.units.id.shape[0] == unit_data_len
        # test electrode group:
        for group in full_metadata['Ecephys']['ElectrodeGroup']:
            name = group.pop('name')
            assert name in nwbfile.electrode_groups
            electrode_group_dict = nwbfile.electrode_groups[name].fields
            if electrode_group_dict.get('device'):
                electrode_group_dict['device'] = electrode_group_dict['device'].name
            assert group == electrode_group_dict
        # test electrode table:
        elec_tbl_len = sum(converter_nwb1._data_attrs_dump['electrode_table_length'])
        for electrode in full_metadata['ElectrodeTable']:
            assert electrode['name'] in nwbfile.electrodes.colnames
        assert nwbfile.electrodes.id.shape[0] == elec_tbl_len
        # test timeseries ephys:
        ephys_datasets = nwbfile.processing['Ecephys'].data_interfaces
        for i, j in full_metadata['Ecephys']['Ecephys'].items():
            for j1 in j:
                assert j1['data'] in converter_nwb1._data_attrs_dump.keys()
                field_names = converter_nwb1._data_attrs_dump[j1['data']]
                for k in field_names:
                    assert k in ephys_datasets.keys()
                    if 'Spectrum' in i:
                        assert isinstance(ephys_datasets[k], Spectrum)
                    else:
                        assert isinstance(ephys_datasets[k], TimeSeries)
        # test behavior:
        ephys_datasets = nwbfile.processing['Behavior'].data_interfaces
        for i, j in full_metadata['Behavior'].items():
            for i1, j1 in j.items():
                for j11 in j1:
                    assert i in ephys_datasets.keys()
                    if j11['name'] != 'camera_dlc':
                        assert j11['name'] in getattr(ephys_datasets[i], i1).keys()
                        if i == 'Position':
                            assert isinstance(getattr(ephys_datasets[i], i1)[j11['name']], SpatialSeries)
                        else:
                            assert isinstance(getattr(ephys_datasets[i], i1)[j11['name']], TimeSeries)
        # test acquisition: test only presence of names of datasets:
        if save_raw and save_camera_raw:
            acq_datasets = nwbfile.acquisition
            for i, j in full_metadata['Acquisition'].items():
                for j1 in j:
                    assert any([True for h in acq_datasets.keys() if j1['name'] in h])

import datetime
import os
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
import json,yaml
from pathlib import Path

nonetype=type(None)

class TestConverter:

    def check_args(self, full_metadata_dict, original_dict):
        for i, j in full_metadata_dict.items():
            assert i in original_dict.keys()
            if isinstance(original_dict[i], Iterable):
                assert type(j) in original_dict[i] or isinstance(j,nonetype)
            else:
                assert type(j) in [original_dict[i],nonetype]

    def test_metadata_converter(self):
        eid_temp = 'da188f2c-553c-4e04-879b-c9ea2d1b9a93'
        temp_path = Path(tempfile.mkdtemp())
        converter_name_json = temp_path / 'temp.json'
        converter_name_yaml = temp_path/'temp.yaml'
        one=ONE()
        converter_metadata = Alyx2NWBMetadata(eid=eid_temp, one_obj=one)
        full_metadata = converter_metadata.complete_metadata
        #check base keys
        for i in full_metadata:
            assert i in metafile_base_fields
        # check nwbfile related fields:
        for i,j in nwbfile_required_dict.items():
            assert i in full_metadata['NWBFile']
            if isinstance(j,Iterable):
                assert type(full_metadata['NWBFile'][i]) in j
            else:
                assert type(full_metadata['NWBFile'][i])==j
            _ = full_metadata['NWBFile'].pop(i)
        self.check_args(full_metadata['NWBFile'], nwbfile_optional_dict)
        #check sessions,subject, probes fields:
        self.check_args(full_metadata['IBLSessionsData'], sessions_data_dict)
        self.check_args(full_metadata['IBLSubject'], subject_data_dict)
        assert isinstance(full_metadata['Probes'],list)
        for probe in full_metadata['Probes']:
            self.check_args(probe, probes_data_dict)
        #check trials, units, electrode_table:
        assert isinstance(full_metadata['Trials'],list)
        for i in full_metadata['Trials']:
            self.check_args(i,dt_columns_data_dict)
        assert isinstance(full_metadata['Units'], list)
        for i in full_metadata['Units']:
            self.check_args(i,dt_columns_data_dict)
        assert isinstance(full_metadata['ElectrodeTable'], list)
        for i in full_metadata['ElectrodeTable']:
            self.check_args(i, dt_columns_data_dict)
        # Ecephys: Device:
        assert 'Device' in full_metadata['Ecephys']
        assert isinstance(full_metadata['Ecephys']['Device'],list)
        for i in full_metadata['Ecephys']['Device']:
            self.check_args(i,device_data_dict)
        # Ecephys: ElectrodeGroup:
        assert 'ElectrodeGroup' in full_metadata['Ecephys']
        assert isinstance(full_metadata['Ecephys']['ElectrodeGroup'], list)
        for i in full_metadata['Ecephys']['ElectrodeGroup']:
            self.check_args(i, electrode_group_data_dict)
        # Ecephys: Ecephys:
        assert 'Ecephys' in full_metadata['Ecephys']
        assert isinstance(full_metadata['Ecephys']['Ecephys'], dict)
        for i,j in full_metadata['Ecephys']['Ecephys'].items():
            assert isinstance(j,list)
            for j1 in j:
                if i=='Spectrum':
                    _ = j1.pop('timestamps')
                    _ = j1.pop('data')
                    self.check_args(j1, spectrum_data_dict)
                else:
                    self.check_args(j1, timeseries_data_dict)
        #Acquisition:
        assert isinstance(full_metadata['Acquisition'], dict)
        for i, j in full_metadata['Acquisition'].items():
            assert isinstance(j, list)
            for j1 in j:
                if i == 'DecompositionSeries':
                    self.check_args(j1, decomposition_data_dict)
                else:
                    self.check_args(j1, timeseries_data_dict)
        #Behavior:
        assert isinstance(full_metadata['Behavior'],dict)
        for i, j in full_metadata['Behavior'].items():
            assert isinstance(j,dict)
            for i1,j1 in j.items():
                assert i1 in ['time_series','interval_series','spatial_series']
                for j11 in j1:
                    self.check_args(j11,timeseries_data_dict)
        #save yaml/json files and check types:
        converter_metadata.write_metadata(converter_name_json,savetype='.json')
        converter_metadata.write_metadata(converter_name_yaml,savetype='.yaml')
        with open(converter_name_json,'r') as f:
            json_load = json.load(f)
            assert isinstance(json_load,dict)
        with open(converter_name_yaml,'r') as f:
            yaml_load = yaml.load(f)
            assert isinstance(yaml_load,dict)

    def test_nwb_converter(self):
        pass


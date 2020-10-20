import sys
import uuid
from copy import copy, deepcopy
from datetime import datetime

import h5py
from ndx_ibl_metadata import IblProbes
from pynwb import NWBHDF5IO

from .field_map import *


def _convert_numpy_to_python_dtype(dict_to_convert_in):
    dict_to_convert_out = dict()
    for key, val in dict_to_convert_in.items():
        if 'numpy' in str(type(val)):
            dict_to_convert_out[key] = val.item()
        elif isinstance(val, dict):
            dict_to_convert_out[key] = _convert_numpy_to_python_dtype(val)
        else:
            dict_to_convert_out[key] = val
    return dict_to_convert_out


def nwb_to_ibl_dict(nwb_dict, key_map):
    out = dict()
    for i, j in key_map.items():
        if i in nwb_dict.keys():
            if isinstance(nwb_dict[i], (h5py.Dataset, list)):
                temp = list()
                for no, it in enumerate(nwb_dict[i]):
                    temp.append(j['dtype'](it))
                out[j['name']] = temp
            else:
                out[j['name']] = j['dtype'](nwb_dict[i])
        else:
            out[j['name']] = ''
    return out


class NWBToIBLSession:

    def __init__(self, nwbfile_loc):
        self.nwbfileloc = nwbfile_loc
        self.nwbfile = NWBHDF5IO(nwbfile_loc, 'r', load_namespaces=True).read()
        self.nwb_h5file = h5py.File(nwbfile_loc, 'r')
        # self.url_schema = self._schema_gen()
        self.session_json = self._build_sessions_table()
        self.subject_json = self._build_subject_table()
        # updating session fields:
        self.session_json['url'] = nwbfile_loc
        self.session_json['data_dataset_session_related'] = self._get_nwb_data()

    def _build_subject_table(self):
        sub_dict_out = dict()
        if self.nwbfile.subject:
            sub_dict = dict()
            for i, j in self.nwbfile.subject.fields.items():
                sub_dict[i] = j
            all_fields = deepcopy(field_map_subject)
            all_fields.update(field_map_IBL_subject)
            sub_dict_out = nwb_to_ibl_dict(sub_dict, all_fields)
        return sub_dict_out

    def _build_sessions_table(self):
        nwbdict = dict()
        for i, j in field_map_nwbfile.items():
            nwbdict[i] = getattr(self.nwbfile, i)
        nwb_data = nwb_to_ibl_dict(nwbdict, field_map_nwbfile)
        if self.nwbfile.lab_meta_data.get('Ibl_session_data'):
            nwb_data.update(nwb_to_ibl_dict(
                self.nwbfile.lab_meta_data.get('Ibl_session_data').fields, field_map_session_data))
        # adding subject name:
        if self.nwbfile.fields.get('nickname'):
            nwb_data['subject'] = self.nwbfile.fields.get('nickname')
        else:
            nwb_data['subject'] = ''
        # adding ntrials, n_correct_trials, narrative:
        nwb_data['n_trials'] = len(self.nwbfile.trials) if self.nwbfile.trials else 0
        nwb_data['n_correct_trials'] = sum(self.nwbfile.trials['choice'].data[()] != 0) \
            if self.nwbfile.trials.get('choice') else len(self.nwbfile.trials)
        nwb_data['narrative'] = ''
        # adding probes:
        count = 0
        nwb_data['probe_insertion'] = []
        for i, j in self.nwbfile.devices.items():
            if isinstance(j, IblProbes):
                nwb_data['probe_insertion'].append(j.fields)
                temp = copy(nwb_data['probe_insertion'][count]['trajectory_estimate'][()])
                nwb_data['probe_insertion'][count]['trajectory_estimate'] = \
                    [json.loads(ii) for ii in temp]
                nwb_data['probe_insertion'][count]['name'] = j.name
                count = count + 1
        return nwb_data

    def _get_nwb_data(self):
        out = []
        if 'intervals' in self.nwb_h5file:
            for trl_keys in self.nwb_h5file['intervals/trials']:
                out.append(dict(
                    id=str(uuid.uuid1()),
                    name=trl_keys,
                    dataset_type='trials.' + trl_keys,
                    data_url='intervals/trials/' + trl_keys,
                    url=self.nwbfileloc,
                    file_size=sys.getsizeof(self.nwb_h5file['intervals/trials/' + trl_keys])))
        if 'units' in self.nwb_h5file:
            for units_keys in self.nwb_h5file['units']:
                out.append(dict(
                    id=str(uuid.uuid1()),
                    name=units_keys,
                    dataset_type='clusters.' + units_keys,
                    url=self.nwbfileloc,
                    data_url='units/' + units_keys,
                    file_size=sys.getsizeof(self.nwb_h5file['units/' + units_keys])))
        if 'processing' in self.nwb_h5file:
            if 'ecephys' in self.nwb_h5file['processing']:
                for ecephys_keys in self.nwb_h5file['processing/ecephys']:
                    out.append(dict(
                        id=str(uuid.uuid1()),
                        name=ecephys_keys,
                        dataset_type='spikes.' + ecephys_keys,
                        url=self.nwbfileloc,
                        data_url='processing/ecephys/' + ecephys_keys,
                        file_size=sys.getsizeof(self.nwb_h5file['processing/ecephys/' + ecephys_keys])))
        if 'general/extracellular_ephys/electrodes' in self.nwb_h5file:
            for electrode_keys in self.nwb_h5file['general/extracellular_ephys/electrodes']:
                out.append(dict(
                    id=str(uuid.uuid1()),
                    name=electrode_keys,
                    dataset_type='channels.' + electrode_keys,
                    url=self.nwbfileloc,
                    data_url='general/extracellular_ephys/electrodes/' + electrode_keys,
                    file_size=sys.getsizeof(
                        self.nwb_h5file['general/extracellular_ephys/electrodes/' + electrode_keys])))
        return out

    def write_json(self, filename, metadata_type):
        if metadata_type == 'sessions':
            dumpfile = self.session_json
        elif metadata_type == 'subject':
            dumpfile = self.subject_json
        dumpfile_py = _convert_numpy_to_python_dtype(dumpfile)
        time_key = [i for i in dumpfile_py if 'time' in i or 'date' in i]
        if time_key:
            time_key = time_key[0]
            try:
                dumpfile_py[time_key] = datetime.strftime(dumpfile_py[time_key], '%Y-%m-%dT%X')
            except TypeError:
                pass
        with open(filename, 'w') as f:
            json.dump(dumpfile_py, f, indent=2)

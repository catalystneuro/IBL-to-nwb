import json
import genson
from oneibl.one import ONE
from pynwb import NWBFile, NWBHDF5IO
import uuid
import h5py
import sys
from datetime import datetime


class NWBToIBLSession:
    field_map_nwbfile = {'session_start_time': 'start_time',
                         'institution': 'lab',
                         'experiment_description': 'project',
                         'experimenter': 'users',
                         'lab': 'lab',
                         'protocol': 'task_protocol',
                         'session_description': 'narrative'}

    field_map_subject = {'subject_id': 'id',
                         'description': 'description',
                         'genotype': 'genotype',
                         'sex': 'sex',
                         'species': 'species',
                         'weight': 'reference_weight',
                         'date_of_birth': 'birth_date',
                         'age': 'age_weeks'}

    def __init__(self, nwbfile_loc):
        self.nwbfileloc = nwbfile_loc
        self.nwbfile = NWBHDF5IO(nwbfile_loc, 'r').read()
        self.nwb_h5file = h5py.File(nwbfile_loc,'r')
        # self.url_schema = self._schema_gen()
        self.session_json = self._get_nwb_info('nwbfile')
        self.subject_json = self._get_nwb_info('subject')
        # updating subject fields:
        self.subject_json['projects'] = [self.session_json['project']]
        self.subject_json['lab'] = self.session_json['lab']
        self.subject_json['responsible_user'] = self.session_json['users'][0]
        self.subject_json['nickname'] = self.session_json['users']
        # updating session fields:
        self.session_json['url'] = nwbfile_loc
        if self.nwbfile.trials:
            self.session_json['n_trials'] = len(self.nwbfile.trials.id)
        else:
            self.session_json['n_trials'] = 1
        self.session_json['data_dataset_session_related'] = self._get_nwb_data()

    def _create_ibl_dict(self, nwb_dict, key_map):
        out = dict()
        for i,j in key_map.items():
            if i in nwb_dict.keys():
                out[j] = nwb_dict[i]
            else:
                out[j] = ''
        return out

    # def _schema_gen(self):
    #     eid = self.one.search(dataset_types=['spikes.times'])
    #     return self.one.alyx.rest('sessions/' + eid[0], 'list')
    #     schema = genson.SchemaBuilder()
    #     schema.add_schema({'type': 'object', 'properties': {}})
    #     schema.add_object(self.url_resp)
    #     return schema.to_schema()

    def _get_nwb_info(self, nwbkey):
        if nwbkey == 'subject':
            if self.nwbfile.subject:
                return self._create_ibl_dict(self.nwbfile.subject.fields, self.field_map_subject)
            else:
                return dict()
        if nwbkey == 'nwbfile':
            nwbdict=dict()
            for i,j in self.field_map_nwbfile.items():
                nwbdict[i] = getattr(self.nwbfile,i)
            return self._create_ibl_dict(nwbdict,self.field_map_nwbfile)

    def _get_nwb_data(self):
        out = []
        if 'intervals' in self.nwb_h5file:
            for trl_keys in self.nwb_h5file['intervals/trials']:
                out.append(dict(
                    id=str(uuid.uuid1()),
                    name=trl_keys,
                    dataset_type='trials.'+trl_keys,
                    data_url='intervals/trials/'+trl_keys,
                    url=self.nwbfileloc,
                    size=sys.getsizeof(self.nwb_h5file['intervals/trials/'+trl_keys])))
        if 'units' in self.nwb_h5file:
            for units_keys in self.nwb_h5file['units']:
                out.append(dict(
                    id=str(uuid.uuid1()),
                    name=units_keys,
                    dataset_type='clusters.'+units_keys,
                    url=self.nwbfileloc,
                    data_url='units/'+units_keys,
                    size=sys.getsizeof(self.nwb_h5file['units/'+units_keys])))
        if 'processing' in self.nwb_h5file:
            if 'Ecephys' in self.nwb_h5file['processing']:
                for ecephys_keys in self.nwb_h5file['processing/Ecephys']:
                    out.append(dict(
                        id=str(uuid.uuid1()),
                        name=ecephys_keys,
                        dataset_type='spikes.' + ecephys_keys,
                        url=self.nwbfileloc,
                        data_url='processing/Ecephys/' + ecephys_keys,
                        size=sys.getsizeof(self.nwb_h5file['processing/Ecephys/' + ecephys_keys])))
        if 'general/extracellular_ephys/electrodes' in self.nwb_h5file:
            for electrode_keys in self.nwb_h5file['general/extracellular_ephys/electrodes']:
                out.append(dict(
                    id=str(uuid.uuid1()),
                    name=electrode_keys,
                    dataset_type='channels.' + electrode_keys,
                    url=self.nwbfileloc,
                    data_url='general/extracellular_ephys/electrodes/' + electrode_keys,
                    size=sys.getsizeof(self.nwb_h5file['general/extracellular_ephys/electrodes/' + electrode_keys])))
        return out

    def write_json(self, filename, metadata_type):
        if metadata_type == 'sessions':
            dumpfile = self.session_json
        elif metadata_type == 'subject':
            dumpfile = self.subject_json
        time_key = [i for i in dumpfile if 'time' in i or 'date' in i]
        if time_key:
            time_key=time_key[0]
            dumpfile[time_key] = datetime.strftime(dumpfile[time_key],'%Y-%m-%dT%X')
        with open(filename,'w') as f:
            json.dump(dumpfile, f, indent=2)

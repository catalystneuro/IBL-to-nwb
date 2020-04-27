import re
import json
from oneibl.one import ONE
from .schema import metafile as nwb_schema
from .schema import template_metafile as nwb_schema_template
from .schema import dataset_details_list
from .schema import alyx_subject_list


class Alyx2NWBSchema:

    def __init__(self, eid=None, one_obj: ONE = None, **one_kwargs):
        self._one_obj = one_obj
        self.one_kwargs = one_kwargs
        self.schema_template = nwb_schema_template
        self.schema = nwb_schema
        self.one_obj = one_obj
        if not one_obj:
            self.one_obj = ONE()
        elif not isinstance(one_obj, ONE):
            raise Exception('one_obj is not of ONE class')
        self.eid_list = self._get_eid_list(eid)
        self.eid_session_info = self._retrieve_eid_endpoint()
        self.dataset_type_list = self._list_eid_metadata('dataset_type')
        self.users_list = self._list_eid_metadata('users')
        self.subjects_list = self._list_eid_metadata('subjects')
        self.labs_list = self._list_eid_metadata('labs')
        self.dataset_details, self.dataset_simple = self._dataset_type_parse()
        self._get_lab_table()
        self._get_subject_table()

    def _get_eid_list(self, eid_list):
        if eid_list:
            if not isinstance(eid_list, list):
                eid_list = [eid_list]
        else:
            eid_list = self._one_obj.search(**self.one_kwargs)
        return eid_list

    def _get_dataset_details(self):
        list_type_returned = [None]*len(self.eid_list)
        for val, e_id in enumerate(self.eid_list):
            dataset_dict = self.eid_session_info[val]['data_dataset_session_related']
            list_type_returned[val] = [i['name'] for i in dataset_dict]
        return list_type_returned

    def _list_eid_metadata(self, list_type):
        list_type_returned = [None]*len(self.eid_list)
        for val, e_id in enumerate(self.eid_list):
            list_type_returned[val] = self.one_obj.list(e_id, list_type)
        return list_type_returned

    def _retrieve_eid_endpoint(self):
        eid_sess_info = [None]*len(self.eid_list)
        for val, ceid in enumerate(self.eid_list):
            eid_sess_info[val] = self.one_obj.alyx.rest('sessions/' + ceid, 'list')
            for i in eid_sess_info[val]:
                if not eid_sess_info[val][i]:
                    eid_sess_info[val][i] = 'None'
        return eid_sess_info

    def _get_lab_table(self):
        self.lab_table = self.one_obj.alyx.rest('labs', 'list')

    def _get_subject_table(self):
        self.subject_table = [dict()]*len(self.eid_list)
        sub_name_list = [i['nickname'] for i in alyx_subject_list]
        for val, e_id in enumerate(self.eid_list):
            sub_id = [i for j, i in enumerate(sub_name_list) if i == self.eid_session_info[val]['subject']]
            if sub_id:
                self.subject_table[val] = alyx_subject_list[sub_id[0]]
            else:
                for kk in alyx_subject_list[0]:
                    self.subject_table[val][kk] = 'None'

    def _dataset_type_parse(self):
        """
        :return: list of dict. Each item as a dict with values as list of dict with keys: name and description
        -<dataset object name>: (eg. spikes, clusters etc)
            -name: objects attribute type (eg. times, intervals etc
             description: attributes description
            -name: objects attribute type (eg. times, intervals etc
             description: attributes description
             .
             .
             .
        """
        dataset_type_list = [None]*len(self.eid_list)
        dataset_type_list_simple = [None]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            dataset_description_list = dict()
            for data_id in dataset_details_list:
                dataset_description_list[data_id['name']] = data_id['description']
            split_list_objects = [i.split('.')[0] for i in self.dataset_type_list[val]]
            split_list_attributes = [i.split('.')[1] for i in self.dataset_type_list[val]]
            dataset_description = [dataset_description_list[i] for i in self.dataset_type_list[val]]
            # dataset_extension = [u['name'].split('.')[-1] for u in self.eid_session_info[val]['data_dataset_session_related']]
            split_list_objects_dict_details = dict()
            split_list_objects_dict = dict()
            for obj in set(split_list_objects):
                split_list_objects_dict_details[obj] = []
                split_list_objects_dict[obj] = []
            for att_idx, attrs in enumerate(split_list_attributes):
                append_dict = {'name': attrs,
                               'description': dataset_description[att_idx]}
                # 'extension': dataset_extension[att_idx] }
                split_list_objects_dict_details[split_list_objects[att_idx]].extend([append_dict])
                split_list_objects_dict[split_list_objects[att_idx]].extend([attrs])
            dataset_type_list[val] = split_list_objects_dict_details
            dataset_type_list_simple[val] = split_list_objects_dict
        return dataset_type_list, dataset_type_list_simple

    def _unpack_dataset_details(self, dataset_details, object_name, custom_attrs=None, match_str=' '):
        """
        helper function to split object and attributes of the IBL datatypes into
        names: obj_attr; data= obj.attr; desc for each
        :param dataset_details:
        :param object_name:
        :param custom_attrs:
        :param match_str:
        :return:
        """
        cond = lambda x: re.match(match_str, x)
        datafiles_all = [object_name + '.' + ii['name'] for ii in dataset_details[object_name] if not cond(ii['name'])]
        datafiles_names_all = [object_name + '_' + ii['name'] for ii in dataset_details[object_name] if
                               not cond(ii['name'])]
        datafiles_desc_all = [ii['description'] for ii in dataset_details[object_name] if not cond(ii['name'])]
        if custom_attrs:
            datafiles_inc = [i for i in datafiles_all if i in object_name + '.' + custom_attrs]
            datafiles_names_inc = [datafiles_names_all[j] for j, i in enumerate(datafiles_all) if
                                   i in object_name + '.' + custom_attrs]
            datafiles_desc_inc = [datafiles_desc_all[j] for j, i in enumerate(datafiles_all) if
                                  i in object_name + '.' + custom_attrs]
        else:
            datafiles_inc = datafiles_all
            datafiles_names_inc = datafiles_names_all
            datafiles_desc_inc = datafiles_desc_all
        return datafiles_inc, datafiles_names_inc, datafiles_desc_inc

    def _initialize_container_dict(self, name=None, default_value=None):
        if default_value is None:
            default_value = dict()
        if name:
            return [{name: default_value}]*len(self.eid_list)
        else:
            return [[]]*len(self.eid_list)

    def _get_all_object_names(self):
        outlist = [[]]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            outlist[val] = sorted(list(set([i.split('.')[0] for i in self.dataset_type_list[val]])))
        return outlist

    def _get_current_object_names(self, obj_list):
        out_list = [['']*len(obj_list)]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            for j, k in enumerate(obj_list):
                if k in self._get_all_object_names()[val]:
                    out_list[val][j] = [i for i in self._get_all_object_names()[val] if k == i][0]
                else:
                    out_list[val][j] = ''
        return out_list

    def _get_timeseries_object(self, dataset_details, object_name, ts_name, custom_attrs=None, **kwargs):
        """
        :param dataset_details: self.dataset_details
        :param object_name: name of hte object_name in the IBL datatype
        :param custom_attrs: if there are a subset of IBL object's attributes for which to create time series.
        :param ts_name: timeseries key name like 'time_series', can also be 'interval_series' in some cases
        :param kwargs: if there are additional fields that need to be created within the times series object. This happens
        when the neuro_datatype is like roi response series, electrical series etc (classes that inherit from timeseries in pynwb)
        generate a dictionary like:
        {
        "time_series": [
            {
              "name": "face_motionEnergy",
              "data": "face.motionEnergy",
              "timestamps": "face.timestamps",
              "description": "Features extracted from the video of the frontal aspect of the subject, including the subject\\'s face and forearms."
            },
            {
              "name": "_ibl_lickPiezo_times",
              "data": "_ibl_lickPiezo.raw",
              "timestamps": "_ibl_lickPiezo.timestamps",
              "description": "Voltage values from a thin-film piezo connected to the lick spout, so that values are proportional to deflection of the spout and licks can be detected as peaks of the signal."
            }
        ]
        }
        """
        matchstr = r'.*time.*|.*interval.*'
        timeattr_name = [i['name'] for i in dataset_details[object_name] if re.match(matchstr, i['name'])]
        datafiles, datafiles_names, datafiles_desc = \
            self._unpack_dataset_details(dataset_details, object_name, custom_attrs, match_str=matchstr)
        datafiles_timedata, datafiles_time_name, datafiles_time_desc = \
            self._unpack_dataset_details(dataset_details, object_name, timeattr_name[0])
        if not datafiles:
            datafiles_names = datafiles_time_name
            datafiles_desc = datafiles_time_desc
            datafiles = ['None']
        timeseries_dict = {ts_name: [None]*len(datafiles)}
        for i, j in enumerate(datafiles):
            timeseries_dict[ts_name][i] = {'name': datafiles_names[i],
                                           'description': datafiles_desc[i],
                                           'timestamps': datafiles_timedata[0],
                                           'data': datafiles[i]}
            timeseries_dict[ts_name][i].update(**kwargs)
        return timeseries_dict

    def _attrnames_align(self, attrs_dict, custom_names):
        attrs_list = [i['name'] for i in attrs_dict]
        out_list = []
        idx_list = []
        if custom_names:
            append_set = set(attrs_list).difference(set(custom_names.values()))
            for i in custom_names.values():
                idx = [ii for ii, k in enumerate(attrs_list) if k in i][0]
                idx_list.extend([idx])
                out_list.extend([attrs_list[idx]])
            out_list.extend(list(append_set))
            idx_list.extend(list(set(range(len(attrs_list))).difference(set(idx_list))))
        else:
            idx_list = range(len(attrs_list))
            out_list = attrs_list
        out_dict = [attrs_dict[i] for i in idx_list]
        return out_dict, out_list

    def _get_dynamictable_array(self, **kwargs):
        custom_keys = list(kwargs.keys())
        custom_data = list(kwargs.values())
        out_list = [None]*len(custom_data[0])
        for ii, jj in enumerate(custom_data[0]):
            out_list[ii] = dict()
            for i, j in enumerate(custom_keys):
                out_list[ii][j] = custom_data[i][ii]
        return out_list

    def _get_dynamictable_object(self, dataset_details, object_name, dt_name, default_colnames_dict=None,
                                 custom_attrs=None):
        """
                :param dataset_details: self.dataset_details
                :param object_name: name of hte object_name in the IBL datatype
                :param dt_name: table key name like 'time_series', can also be 'interval_series' in some cases
                :param custom_colmns: the custom set of attributes for which to create columns from
                {'Trials':
                    [
                        {
                          "name": "column1 name",
                          "data": "column data uri (string)",
                          "description": "col1 description"
                        },
                        {
                           "name": "column2 name",
                          "data": "column data uri (string)",
                          "description": "col2 description"
                        }
                    ]
                }
                """
        dataset_details[object_name], _ = self._attrnames_align(dataset_details[object_name], default_colnames_dict)
        if not default_colnames_dict:
            default_colnames = []
        else:
            default_colnames = list(default_colnames_dict.keys())
        custom_columns_datafilename, custom_columns_name, custom_columns_description = \
            self._unpack_dataset_details(dataset_details, object_name, custom_attrs)
        custom_columns_datafilename[:len(default_colnames)] = default_colnames
        in_list = self._get_dynamictable_array(
            name=custom_columns_name,
            data=custom_columns_datafilename,
            description=custom_columns_description)
        outdict = {dt_name: in_list}
        return outdict

    @property
    def eid_metadata(self):
        eid_metadata = [dict()]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            eid_metadata[val].update(dict(eid=self.eid_list))
        return eid_metadata

    @property
    def nwbfile_metadata(self):
        nwbfile_metadata_dict = self._initialize_container_dict('NWBFile')
        for val, Ceid in enumerate(self.eid_list):
            nwbfile_metadata_dict[val]['NWBFile']['session_start_time'] = self.eid_session_info[val]['start_time']
            nwbfile_metadata_dict[val]['NWBFile']['keywords'] = self.eid_session_info[val]['start_time']
            nwbfile_metadata_dict[val]['NWBFile']['experiment_description'] = self.eid_session_info[val]['narrative']
            nwbfile_metadata_dict[val]['NWBFile']['session_id'] = Ceid
            nwbfile_metadata_dict[val]['NWBFile']['experimenter'] = ','.join(self.eid_session_info[val]['users'])
            nwbfile_metadata_dict[val]['NWBFile']['identifier'] = Ceid
            nwbfile_metadata_dict[val]['NWBFile']['institution'] = \
                [i['institution'] for i in self.lab_table if i['name'] == [self.eid_session_info[val]['lab']][0]]
            nwbfile_metadata_dict[val]['NWBFile']['lab'] = self.eid_session_info[val]['lab']
            nwbfile_metadata_dict[val]['NWBFile']['session_description'] = self.eid_session_info[val]['task_protocol']
            nwbfile_metadata_dict[val]['NWBFile']['surgery'] = 'None'
            nwbfile_metadata_dict[val]['NWBFile']['notes'] = 'Procedures:' + ','.join(self.eid_session_info[val]['procedures']) \
                                                  + ', Project:' + self.eid_session_info[val]['project']

        return nwbfile_metadata_dict

    @property
    def subject_metadata(self):
        subject_metadata_dict = self._initialize_container_dict('Subject')
        for val, Ceid in enumerate(self.eid_list):
            if self.subject_table[val]:
                subject_metadata_dict[val]['Subject']['subject_id'] = self.subject_table[val]['id']
                subject_metadata_dict[val]['Subject']['description'] = self.subject_table[val]['description']
                subject_metadata_dict[val]['Subject']['genotype'] = ','.join(self.subject_table[val]['genotype'])
                subject_metadata_dict[val]['Subject']['sex'] = self.subject_table[val]['sex']
                subject_metadata_dict[val]['Subject']['species'] = self.subject_table[val]['species']
                subject_metadata_dict[val]['Subject']['weight'] = self.subject_table[val]['reference_weight']
                subject_metadata_dict[val]['Subject']['date_of_birth'] = self.subject_table[val]['birth_date']
        return subject_metadata_dict

    @property
    def surgery_metadata(self):  # currently not exposed by api
        surgery_metadata_dict = [dict()]*len(self.eid_list)
        return surgery_metadata_dict

    @property
    def behavior_metadata(self):
        behavior_metadata_dict = self._initialize_container_dict('Behavior')
        behavior_objects = ['wheel', 'wheelMoves', 'licks', 'lickPiezo', 'face', 'eye']
        current_behavior_objects = self._get_current_object_names(behavior_objects)
        for val, Ceid in enumerate(self.eid_list):
            for k, u in enumerate(current_behavior_objects[val]):
                if 'wheel' in u:
                    behavior_metadata_dict[val]['Behavior']['BehavioralTimeSeries'] = \
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')
                if 'wheelMoves' in self.dataset_details[val].keys():
                    behavior_metadata_dict[val]['Behavior']['BehavioralEpochs'] = \
                        self._get_timeseries_object(self.dataset_details[val], u, 'interval_series')
                if 'lickPiezo' in self.dataset_details[val].keys():
                    behavior_metadata_dict[val]['Behavior']['BehavioralTimeSeries']['time_series'].extend(
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')['time_series'])
                if 'licks' in self.dataset_details[val].keys():
                    behavior_metadata_dict[val]['Behavior']['BehavioralEvents'] = \
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')
                if 'face' in self.dataset_details[val].keys():
                    behavior_metadata_dict[val]['Behavior']['BehavioralTimeSeries']['time_series'].extend(
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')['time_series'])
                if 'eye' in self.dataset_details[val].keys():
                    behavior_metadata_dict[val]['Behavior']['PupilTracking'] = \
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')
        return behavior_metadata_dict

    @property
    def trials_metadata(self):
        trials_metadata_dict = self._initialize_container_dict()
        trials_objects = ['trials']
        current_trial_objects = self._get_current_object_names(trials_objects)
        for val, Ceid in enumerate(self.eid_list):
            for k, u in enumerate(current_trial_objects[val]):
                if 'trial' in u:
                    trials_metadata_dict[val] = self._get_dynamictable_object(self.dataset_details[val], 'trials',
                                                                              'Trial',
                                                                              default_colnames_dict=dict(
                                                                                  start_time='intervals',
                                                                                  stop_time='intervals'))
        return trials_metadata_dict

    @property
    def stimulus_metadata(self):
        stimulus_objects = ['sparseNoise', 'passiveBeeps', 'passiveValveClick', 'passiveVisual', 'passiveWhiteNoise']
        stimulus_metadata_dict = self._initialize_container_dict('Stimulus')
        current_stimulus_objects = self._get_current_object_names(stimulus_objects)
        for val, Ceid in enumerate(self.eid_list):
            for k, u in enumerate(current_stimulus_objects[val]):
                if 'sparseNoise' in u:
                    stimulus_metadata_dict[val]['Stimulus'] = \
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')
                if 'passiveBeeps' in u:
                    stimulus_metadata_dict[val]['Stimulus']['time_series'].extend(
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')['time_series'])
                if 'passiveValveClick' in u:
                    stimulus_metadata_dict[val]['Stimulus']['time_series'].extend(
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')['time_series'])
                if 'passiveVisual' in u:
                    stimulus_metadata_dict[val]['Stimulus']['time_series'].extend(
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')['time_series'])
                if 'passiveWhiteNoise' in u:
                    stimulus_metadata_dict[val]['Stimulus']['time_series'].extend(
                        self._get_timeseries_object(self.dataset_details[val], u, 'time_series')['time_series'])
        return stimulus_metadata_dict

    @property
    def device_metadata(self):
        device_objects = ['probes']
        device_metadata_dict = self._initialize_container_dict('Devices', default_value=[])
        current_device_objects = self._get_current_object_names(device_objects)
        for val, Ceid in enumerate(self.eid_list):
            for k, u in enumerate(current_device_objects[val]):
                for ii in range(2):
                    device_metadata_dict[val]['Devices'].extend(
                        self._get_dynamictable_array(name=[f'{u}{ii}'],
                                                     description=['NeuroPixels probe'])
                    )
        return device_metadata_dict

    @property
    def units_metadata(self):
        units_objects = ['clusters', 'spikes']
        units_metadata_dict = self._initialize_container_dict('Units')
        current_units_objects = self._get_current_object_names(units_objects)
        temp_dataset = self.dataset_details.copy()
        for val, Ceid in enumerate(self.eid_list):
            temp_dataset[val][current_units_objects[val][0]].extend(temp_dataset[val][current_units_objects[val][1]])
            temp_dataset_details = dict(clusters=temp_dataset[val]['clusters'])
            for k, u in enumerate(current_units_objects[val]):
                if 'clusters' in u:
                    units_metadata_dict[val] = \
                        self._get_dynamictable_object(self.dataset_details[val], 'clusters', 'Units')
                    # units_metadata_dict[val]['Units'].extend(
                        # self._get_dynamictable_array(name=['spike_times', 'electrode_groups', 'sampling_rate'],
                        #                              data=['None', 'None', 'None'],
                        #                              description=['times of spikes in the cluster',
                        #                                           'electrodes of this cluster,', 'None']
                        #                              ))
        return units_metadata_dict

    @property
    def electrodegroup_metadata(self):
        electrodes_group_metadata_dict = self._initialize_container_dict('ElectrodeGroups', default_value=[])
        for val, Ceid in enumerate(self.eid_list):
            for ii in range(2):
                electrodes_group_metadata_dict[val]['ElectrodeGroups'].extend(
                    self._get_dynamictable_array(name=[f'Probe{ii}'],
                                                 description=['NeuroPixels device'],
                                                 device=[self.device_metadata[val]['Devices'][ii]],
                                                 location=[''])
                )
        return electrodes_group_metadata_dict

    @property
    def electrodetable_metadata(self):
        electrodes_objects = ['channels']
        electrodes_table_metadata_dict = self._initialize_container_dict()
        current_electrodes_objects = self._get_current_object_names(electrodes_objects)
        for val, Ceid in enumerate(self.eid_list):
            for i in current_electrodes_objects[val]:
                electrodes_table_metadata_dict[val] = self._get_dynamictable_object(
                    self.dataset_details[val], 'channels', 'ElectrodeTable')
        return electrodes_table_metadata_dict

    @property
    def ecephys_metadata(self):
        ecephys_objects = ['spikes']
        ecephys_metadata_dict = self._initialize_container_dict('EventDetection')
        current_ecephys_objects = self._get_current_object_names(ecephys_objects)
        for val, Ceid in enumerate(self.eid_list):
            ecephys_metadata_dict[val]['EventDetection'] = \
                self._get_timeseries_object(self.dataset_details[val], 'spikes', 'SpikeEventSeries')
        return ecephys_metadata_dict

    @property
    def ophys_metadata(self):
        raise NotImplementedError

    @property
    def scratch_metadata(self):
        # this can be used to add further details about subject, lab,
        raise NotImplementedError

    def write_metadata(self,fileloc):
        metafile_dict = [dict()]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            metafile_dict[val] = {**self.eid_metadata[val],
                                  **self.nwbfile_metadata[val],
                                  **self.subject_metadata[val],
                                  **self.behavior_metadata[val],
                                  **self.trials_metadata[val],
                                  **self.stimulus_metadata[val],
                                  **self.device_metadata[val],
                                  **self.units_metadata[val],
                                  **self.electrodegroup_metadata[val],
                                  **self.electrodetable_metadata[val],
                                  'Ephys': {**self.ecephys_metadata[val]}}
        self.metafile_dict=metafile_dict
        with open(fileloc,'w') as f:
            json.dump(metafile_dict,f,indent=2)


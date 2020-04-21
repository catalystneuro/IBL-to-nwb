import re
from oneibl.one import ONE
from .schema import metafile as nwb_schema
from .schema import template_metafile as nwb_schema_template
from .schema import dataset_format_list
from .schema import dataset_details_list


class Alyx2NWBSchema:

    def __init__(self, eid=None, one_obj: ONE = None, **one_kwargs):
        self._one_obj = one_obj
        self.one_kwargs = one_kwargs
        self.schema_template = nwb_schema_template
        self.schema = nwb_schema
        if not one_obj:
            self.one_obj = ONE()
        elif not isinstance(one_obj, ONE):
            raise Exception('one_obj is not of ONE class')
        self.eid_list = self._get_eid_list()
        self.eid_session_info = self._retrieve_eid_endpoint()
        self.dataset_type_list = self._list_eid_metadata('dataset_type')
        self.users_list = self._list_eid_metadata('users')
        self.subjects_list = self._list_eid_metadata('subjects')
        self.labs_list = self._list_eid_metadata('labs')
        self.dataset_details = self._dataset_type_parse()
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
            list_type_returned = self.one_obj.list(e_id, list_type)
        return list_type_returned

    def _retrieve_eid_endpoint(self):
        eid_sess_info = [None]*len(self.eid_list)
        for val, ceid in enumerate(self.eid_list):
            eid_sess_info[val] = self.one_obj.alyx.rest('sessions/' + ceid, 'list')
        return eid_sess_info

    def _get_lab_table(self):
        self.lab_table = self.one_obj.alyx.rest('labs', 'list')

    def _get_subject_table(self):
        self.subject_table = self.one_obj.alyx.rest('subject/' + self.eid_session_info['subject'], 'list')

    def _dataset_type_parse(self):
        '''
        :return: list of dict. Each item as a dict with values as list of dict with keys: name and description
        -<dataset object name>: (eg. spikes, clusters etc)
            -name: objects attribute type (eg. times, intervals etc
             description: attributes description
            -name: objects attribute type (eg. times, intervals etc
             description: attributes description
             .
             .
             .
        '''
        dataset_type_list = [None]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            dataset_description_list = dict()
            for data_id in dataset_details_list:
                dataset_description_list[data_id['name']] = data_id['description']
            split_list_objects = [i.split('.')[0] for i in self.dataset_type_list[val]]
            split_list_attributes = [i.split('.')[-1] for i in self.dataset_type_list[val]]
            dataset_description = [dataset_description_list[i] for i in self.dataset_type_list[val]]
            # dataset_extension = [u['name'].split('.')[-1] for u in self.eid_session_info[val]['data_dataset_session_related']]
            split_list_objects_dict = dict()
            for obj in set(split_list_objects):
                split_list_objects_dict[obj] = []
            for att_idx, attrs in enumerate(split_list_attributes):
                append_dict = {'name': attrs,
                               'description': dataset_description[att_idx]}
                # 'extension': dataset_extension[att_idx] }
                split_list_objects_dict[split_list_objects[att_idx]].append([append_dict])
            dataset_type_list[val] = split_list_objects_dict
        return dataset_type_list

    def _unpack_dataset_details(self, dataset_details, object_name,custom_attrs=None, match_str=''):
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
        datafiles_names_all = [object_name + '_' + ii['name'] for ii in dataset_details[object_name] if not cond(ii['name'])]
        datafiles_desc_all = [ii['description'] for ii in dataset_details[object_name] if not cond(ii['name'])]
        if not custom_attrs:
            datafiles_inc = [i for i in datafiles_all if i in custom_attrs]
            datafiles_names_inc = [datafiles_names_all[j] for j, i in enumerate(datafiles_all) if i in custom_attrs]
            datafiles_desc_inc = [datafiles_desc_all[j] for j, i in enumerate(datafiles_all) if i in custom_attrs]
        else:
            datafiles_inc = datafiles_all
            datafiles_names_inc = datafiles_names_all
            datafiles_desc_inc = datafiles_desc_all      
        return datafiles_inc, datafiles_names_inc, datafiles_desc_inc

    def _initialize_container_dict(self, name):
        if name:
            return [{name: dict()}]*len(self.eid_list)
        else:
            return []*len(self.eid_list)

    def _get_current_object_names(self, obj_list):
        out_list = [[None]*len(obj_list)]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            for i in self.dataset_details[val]:
                for k in obj_list:
                    if k in i:
                        out_list[val][k] = i
                    else:
                        out_list[val][k] = ''
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
        matchstr='.+time.+|.+interval.+'
        timeattr_name=[i for i in dataset_details[object_name] if re.match(matchstr,i)]
        datafiles, datafiles_names, datafiles_desc = \
            self._unpack_dataset_details(dataset_details, object_name, custom_attrs, match_str=matchstr)
        datafiles_timedata, datafiles_time_name, datafiles_time_desc = \
            self._unpack_dataset_details(dataset_details, object_name, timeattr_name[0])
        if not datafiles:
            datafiles_names=datafiles_time_name
            datafiles_desc=datafiles_time_desc
        timeseries_dict = {ts_name: [None]*len(datafiles)}
        for i, j in enumerate(datafiles):
            timeseries_dict[ts_name][i] = {'name': datafiles_names[i],
                                           'description': datafiles_desc[i],
                                           'timestamps': datafiles_timedata[0],
                                           'data': datafiles[i]}
            timeseries_dict[ts_name][i].update(**kwargs)
        return timeseries_dict

    def _attrnames_align(self,attrs_list, custom_names):
        append_set=set(attrs_list).difference(set(custom_names.values()))
        out_list=[]
        if custom_names:
            for i in custom_names.values():
                idx=[ii for ii,k in enumerate(attrs_list) if k in i][0]
                out_list.extend([attrs_list[idx]])
            out_list.extend(list(append_set))
        else:
            out_list=attrs_list
        return out_list

    def _get_dynamictable_object(self, dataset_details, object_name, dt_name, default_colnames_dict=None, custom_attrs=None):
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
        dataset_details[object_name]=self._attrnames_align(dataset_details[object_name],default_colnames_dict)
        if not default_colnames_dict:
            default_colnames=[]
        else:
            default_colnames=list(default_colnames_dict.keys())
        custom_columns_datafilename, custom_columns_name, custom_columns_description=\
            self._unpack_dataset_details(dataset_details, object_name, custom_attrs)
        custom_columns_datafilename[:len(default_colnames)]=default_colnames
        outdict={dt_name:[dict(name='',description='',data='')]*len(dataset_details[object_name])}
        for i,j in enumerate(outdict):
            outdict[dt_name][i]['name']=custom_columns_name[i]
            outdict[dt_name][i]['description'] =custom_columns_description[i]
            outdict[dt_name][i]['data'] = custom_columns_datafilename[i]
        return outdict

    def set_eid_metadata(self):
        return dict(eid=self.eid_list)

    def set_nwbfile_metadata(self):
        nwbfile_metadata_dict = [dict()]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            nwbfile_metadata_dict[val]['session_start_time'] = self.eid_session_info[val]['start_time']
            nwbfile_metadata_dict[val]['keywords'] = self.eid_session_info[val]['start_time']
            nwbfile_metadata_dict[val]['experiment_description'] = self.eid_session_info[val]['narrative']
            nwbfile_metadata_dict[val]['session_id'] = Ceid
            nwbfile_metadata_dict[val]['experimenter'] = ','.join(self.eid_session_info[val]['users'])
            nwbfile_metadata_dict[val]['identifier'] = Ceid
            nwbfile_metadata_dict[val]['institution'] = \
                [i['institution'] for i in self.lab_table if i['name'] == [self.eid_session_info[val]['lab']][0]]
            nwbfile_metadata_dict[val]['lab'] = self.eid_session_info[val]['lab']
            nwbfile_metadata_dict[val]['session_description'] = self.eid_session_info[val]['task_protocol']
            nwbfile_metadata_dict[val]['surgery'] = 'None'
            nwbfile_metadata_dict[val]['notes'] = 'Procedures:' + ','.join(self.eid_session_info[val]['procedures']) \
                                                  + ', Project:' + self.eid_session_info[val]['project']

        return nwbfile_metadata_dict

    def set_subject_metadata(self):
        subject_metadata_dict = [dict()]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            subject_metadata_dict[val]['subject_id'] = self.subject_table['id']
            subject_metadata_dict[val]['description'] = self.subject_table['description']
            subject_metadata_dict[val]['genotype'] = ','.join(self.subject_table['genotype'])
            subject_metadata_dict[val]['sex'] = self.subject_table['sex']
            subject_metadata_dict[val]['species'] = self.subject_table['species']
            subject_metadata_dict[val]['weight'] = self.subject_table['weighings'][0]['weight']
            subject_metadata_dict[val]['date_of_birth'] = self.subject_table['birth_date']
        return subject_metadata_dict

    def set_surgery_metadata(self):  # currently not exposed by api
        surgery_metadata_dict = [dict()]*len(self.eid_list)
        return surgery_metadata_dict

    def set_behavior_metadata(self):
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

    def set_trials_data(self):
        trials_metadata_dict = self._initialize_container_dict()
        trials_objects = ['trials']
        current_trial_objects = self._get_current_object_names(trials_objects)
        trials_table_default_cols=[]
        for val, Ceid in enumerate(self.eid_list):
            for k, u in enumerate(current_trial_objects[val]):
                if 'trial' in u:
                    trials_metadata_dict[val] = self._get_dynamictable_object(self.dataset_details[val],'trial','Trial',
                                                  default_colnames_dict=dict(start_time='intervals',
                                                                             stop_time='intervals']))
        return trials_metadata_dict

    def set_stimulus_metadata(self):
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

    def set_device_metadata(self):
        device_objects = ['probes']
        device_metadata_dict = self._initialize_container_dict('Devices')
        current_device_objects = self._get_current_object_names(device_objects)
        for val, Ceid in enumerate(self.eid_list):
            for k, u in enumerate(current_device_objects[val]):
                if 'probes' in u:
                    temp=self._unpack_dataset_details(self.dataset_details[val],'probes')
                    device_metadata_dict[val]['Devices']['name']=temp[0]
        return device_metadata_dict

    def set_units_metadata(self):
        units_objcts = ['clusters', 'spikes']

    def set_electrodes_metadata(self):
        electrodes_objects = ['probes', 'channels']

    def set_ecephys_metadata(self):
        return ecephys_metadata_dict

    def set_ophys_metadata(self):
        return ophys_metadata_dict

    def set_scratch_metadata(self):
        # this can be used to add further details about subject, lab,
        pass

    def set_device_metadata(self):
        # currently unavailabl
        pass

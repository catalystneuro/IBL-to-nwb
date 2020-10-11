import re
import json, yaml
from oneibl.one import ONE, OneAbstract
from .schema import metafile as nwb_schema
import os
from datetime import datetime
import warnings
from copy import deepcopy
from pathlib import Path

class Alyx2NWBMetadata:
    # TODO: add docstrings

    def __init__(self, eid=None, one_obj=None, **one_search_kwargs):
        if one_obj is None:
            self.one_obj = ONE()
        elif not isinstance(one_obj, OneAbstract):
            raise Exception('one_obj is not of ONE class')
        else:
            self.one_obj = one_obj
        if eid is None:
            eid = self.one_obj.search(**one_search_kwargs)
            if len(eid) > 1:
                print(f'nos of EIDs found for your search query: {len(eid)}, '
                      f'generating metadata from the first')
                if input('continue? y/n') == 'y':
                    pass
                else:
                    exit()
            self.eid = eid[0]
        elif isinstance(eid,list):
            self.eid = eid[0]
        else:
            self.eid = eid
        self.one_search_kwargs = one_search_kwargs
        self.schema = nwb_schema
        self.dataset_description_list = self._get_dataset_details()
        self.eid_session_info = self._retrieve_eid_endpoint()
        self.dataset_type_list = self._list_eid_metadata('dataset_type')
        self.users_list = self._list_eid_metadata('users')
        self.subjects_list = self._list_eid_metadata('subjects')
        self.labs_list = self._list_eid_metadata('labs')
        self.dataset_details, self.dataset_simple = self._dataset_type_parse()
        self._get_lab_table()
        self._get_subject_table()

    def _get_datetime(self, dtstr, format='%Y-%m-%dT%X'):
        try:
            return datetime.strptime(dtstr,format)
        except ValueError:
            return self._get_datetime(dtstr.split('.')[0], format=format)

    def _get_dataset_details(self):
        """
        Retrieves all datasets in the alyx database currently.
        Retrieves a list of dicts with keys like id, name, created_by,description etc. Uses only name and description.
        Returns
        -------
        list
            List of dicts:
            {<dataset-name> : <dataset_description>
        """
        data_url_resp = self.one_obj.alyx.rest('dataset-types', 'list')
        out_dict = dict()
        for i in data_url_resp:
            out_dict.update({i['name']: i['description']})
        return out_dict

    def _list_eid_metadata(self, list_type):
        """
        Uses one's list method to get the types of <list_type> data from the given eid.
        Parameters
        ----------
        list_type: str
            one of strings from
            >>> ONE().search_terms()
        Returns
        -------
        list
        """
        return self.one_obj.list(self.eid, list_type)

    def _retrieve_eid_endpoint(self):
        """
        To get the current sessions url response. Contains all the session metadata as well as the current datasets etc.
        Returns
        -------
        list
            list of server responses.
        """
        return self.one_obj.alyx.rest('sessions/' + self.eid, 'list')

    def _get_lab_table(self):
        self.lab_table = self.one_obj.alyx.rest('labs', 'list')

    def _get_subject_table(self):
        self.subject_table = self.one_obj.alyx.rest('subjects/' + self.eid_session_info['subject'],'list')

    def _dataset_type_parse(self):
        """

        Returns
        -------
        list
            list of dicts:
            {<dataset object name>: (eg. spikes, clusters etc)
                [
                    {name: objects attribute type (eg. times, intervals etc
                    description: attributes description}
                    {name: objects attribute type (eg. times, intervals etc
                    description: attributes description}
                ]
            }
        """
        split_list_objects = [i.split('.')[0] for i in self.dataset_type_list]
        split_list_attributes = ['.'.join(i.split('.')[1:]) for i in self.dataset_type_list]
        dataset_description = [self.dataset_description_list[i] for i in self.dataset_type_list]
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
        dataset_type_list = split_list_objects_dict_details
        dataset_type_list_simple = split_list_objects_dict
        return dataset_type_list, dataset_type_list_simple

    @staticmethod
    def _unpack_dataset_details(dataset_details, object_name, custom_attrs=None, match_str=' '):
        """
        Unpacks the dataset_details into:
        Parameters
        ----------
        dataset_details: dict
            self.dataset_details
        object_name: str
            eg: spikes, clusters, ecephys
        custom_attrs: list
            attrs to unpack
        match_str: regex
            match string: attrs to exclude (like .times/.intervals etc)
        Returns
        -------
        datafiles: str
            ex: 'face.motionEnergy'
        datanames: str
            ex: 'motionEnergy'
        datadesc: str
            ex: <description string for motionEnergy>
        """
        cond = lambda x: re.match(match_str, x)
        datafiles_all = [object_name + '.' + ii['name'] for ii in dataset_details[object_name] if not cond(ii['name'])]
        datafiles_names_all = [ii['name'] for ii in dataset_details[object_name] if
                               not cond(ii['name'])]
        datafiles_desc_all = [ii['description'] for ii in dataset_details[object_name] if not cond(ii['name'])]
        if custom_attrs:
            datafiles_inc = []
            datafiles_names_inc = []
            datafiles_desc_inc = []
            for attrs in custom_attrs:
                datafiles_inc.extend([i for i in datafiles_all if i in object_name + '.' + attrs])
                datafiles_names_inc.extend([datafiles_names_all[j] for j, i in enumerate(datafiles_all) if
                                       i in object_name + '.' + attrs])
                datafiles_desc_inc.extend([datafiles_desc_all[j] for j, i in enumerate(datafiles_all) if
                                      i in object_name + '.' + attrs])
        else:
            datafiles_inc = datafiles_all
            datafiles_names_inc = datafiles_names_all
            datafiles_desc_inc = datafiles_desc_all
        return datafiles_inc, datafiles_names_inc, datafiles_desc_inc

    def _initialize_container_dict(self, name=None, default_value=None):
        if default_value is None:
            default_value = dict()
        if name:
            return dict({name: default_value.copy()})
        else:
            return None

    def _get_all_object_names(self):
        return sorted(list(set([i.split('.')[0] for i in self.dataset_type_list])))

    def _get_current_object_names(self, obj_list):
        loop_list=[]
        for j, k in enumerate(obj_list):
            loop_list.extend([i for i in self._get_all_object_names() if k == i])
        return loop_list

    def _get_timeseries_object(self, dataset_details, object_name, ts_name, custom_attrs=None, drop_attrs=None, **kwargs):
        """

        Parameters
        ----------
        dataset_details: dict
            self.dataset_details
        object_name: str
            name of hte object_name in the IBL datatype
        ts_name: str
            the key name for the timeseries list
        custom_attrs: list
            Attributes to consider
        drop_attrs: list
            Attributes to drop
        kwargs
            additional keys/values to add to the default timeseries. For derivatives of TimeSEries

        Returns
        -------
        dict()
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
        dataset_details[object_name],_ = self._drop_attrs(dataset_details[object_name].copy(), drop_attrs)
        datafiles, datafiles_names, datafiles_desc = \
            self._unpack_dataset_details(dataset_details.copy(), object_name, custom_attrs, match_str=matchstr)
        if timeattr_name:
            datafiles_timedata, datafiles_time_name, datafiles_time_desc = \
                self._unpack_dataset_details(dataset_details.copy(), object_name, timeattr_name)
        elif not kwargs:  #  if no timestamps info, then let this fields be data
            return {ts_name:[]}
        else:
            datafiles_timedata, datafiles_time_name, datafiles_time_desc = \
                datafiles, datafiles_names, datafiles_desc
        if not datafiles:
            if not kwargs:
                return {ts_name:[]}
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

    @staticmethod
    def _attrnames_align(attrs_dict, custom_names):
        """
        the attributes that receive the custom names are reordered to be first in the list
        Parameters. This assigns description:'no_description' to those that are not found. This will
        later be used(nwb_converter) as an identifier for non-existent data for the given eid.
        ----------
        attrs_dict:list
            list of dict(attr_name:'',attr_description:'')
        custom_names
            same as 'default_colnames_dict' in self._get_dynamictable_object
        Returns
        -------
        dict()
        """
        attrs_list = [i['name'] for i in attrs_dict]
        out_dict = dict()
        out_list = []
        list_id_func_exclude = \
            lambda val, comp_list, comp_bool: [i for i, j in enumerate(comp_list) if comp_bool & (j == val)]
        cleanup = lambda x: [i[0] for i in x if i]
        if custom_names:
            custom_names_list = [i for i in list(custom_names.values())]
            custom_names_dict = []
            for i in range(len(custom_names_list)):
                custom_names_dict.extend([{'name':custom_names_list[i],'description': 'no_description'}])
            attr_list_include_idx = cleanup([list_id_func_exclude(i, attrs_list, True) for i in custom_names_list])
            attr_list_exclude_idx = set(range(len(attrs_list))).difference(set(attr_list_include_idx))
            custom_names_list_include_idx = [i for i,j in enumerate(custom_names_list) if list_id_func_exclude(j, attrs_list, True)]
            for ii,jj in enumerate(custom_names_list_include_idx):
                custom_names_dict[custom_names_list_include_idx[ii]] = attrs_dict[attr_list_include_idx[ii]]
                custom_names_list[custom_names_list_include_idx[ii]] = attrs_list[attr_list_include_idx[ii]]
            extend_dict = [attrs_dict[i] for i in attr_list_exclude_idx]
            extend_list = [attrs_list[i] for i in attr_list_exclude_idx]
            custom_names_dict.extend(extend_dict)
            custom_names_list.extend(extend_list)
            return custom_names_dict, custom_names_list
        else:
            out_dict = attrs_dict
            out_list = attrs_list
            return out_dict, out_list

    @staticmethod
    def _drop_attrs(dataset_details, drop_attrs, default_colnames_dict=None):
        """
        Used to remove given attributes of the IBL dataset.
        Parameters
        ----------
        dataset_details: list
            self.dataset_details['clusters']
            [
                {
                    'name': 'amps',
                    'description': description
                },
                {
                    'name': 'channels',
                    'description': description
                }
            ]
        drop_attrs: list
            list of str: attribute names to drop of the self.dataset_details dict
        default_colnames_dict
        Returns
        -------
        dataset_details: list
            list without dictionaries with 'name' as in drop_attrs

        """
        # dataset_details_copy = dataset_details.copy()
        if drop_attrs is None:
            return dataset_details, default_colnames_dict
        elif not(default_colnames_dict==None):
            default_colnames_dict_copy = default_colnames_dict.copy()
            for i,j in default_colnames_dict_copy.items():
                if j in drop_attrs:
                    default_colnames_dict.pop(i)
        attrs_list = [i['name'] for i in dataset_details]
        dataset_details_return = [dataset_details[i] for i, j in enumerate(attrs_list) if j not in drop_attrs]
        # for i, j in enumerate(attrs_list):
        #     if j in drop_attrs:
        #         del dataset_details_copy[i]
        return dataset_details_return, default_colnames_dict

    @staticmethod
    def _get_dynamictable_array(**kwargs):
        """
        Helper to dynamictable object method
        Parameters
        ----------
        kwargs
            keys and values that define the dictionary,
            both keys and values are lists where each index would slice all the keys/values and create a dict out of that

        Returns
        -------
        list
            list of dictionaries each with the keys and values from kwargs

        """
        custom_keys = list(kwargs.keys())
        custom_data = list(kwargs.values())
        out_list = [None]*len(custom_data[0])
        for ii, jj in enumerate(custom_data[0]):
            out_list[ii] = dict().copy()
            for i, j in enumerate(custom_keys):
                out_list[ii][j] = custom_data[i][ii]
        return out_list

    def _get_dynamictable_object(self, dataset_details, object_name, dt_name, default_colnames_dict=None,
                                 custom_attrs=None,drop_attrs=None):
        """

        Parameters
        ----------
        dataset_details
            self.dataset_details for each eid
        object_name:str
            object from the IBL data types from which to create this table.
        dt_name:str
            custom name for the dynamic table. Its the key with the value being dynamictable_array
        default_colnames_dict:dict()
            keys are the custom names of the columns, corresponding values are the attributes which have to be renamed.
        custom_attrs:list
            list of attributes for the given IBL object in object_name to be considered, all others are ignored

        Returns
        -------
        outdict:dict()
            example output below:
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
        dataset_details[object_name], default_colnames_dict = self._drop_attrs(dataset_details[object_name].copy(),
                                                                drop_attrs, default_colnames_dict)
        dataset_details[object_name], _ = self._attrnames_align(dataset_details[object_name].copy(), default_colnames_dict)
        if not default_colnames_dict:
            default_colnames = []
        else:
            default_colnames = list(default_colnames_dict.keys())
        custom_columns_datafilename, custom_columns_name, custom_columns_description = \
            self._unpack_dataset_details(dataset_details.copy(), object_name, custom_attrs)
        custom_columns_name[:len(default_colnames)] = default_colnames
        in_list = self._get_dynamictable_array(
            name=custom_columns_name,
            data=custom_columns_datafilename,
            description=custom_columns_description)
        outdict = {dt_name: in_list}
        return outdict

    @property
    def eid_metadata(self):
        return dict(eid=self.eid)

    @property
    def probe_metadata(self):
        probes_metadata_dict = self._initialize_container_dict('Probes', default_value=[])
        probe_list = self.eid_session_info['probe_insertion']
        probe_fields = ['id', 'model', 'name', 'trajectory_estimate']
        input_dict = dict()
        for k in probe_fields:
            if k == 'trajectory_estimate':
                input_dict.update(
                    {k: [[str(l) for l in probe_list[i].get(k, ["None"])] for i in range(len(probe_list))]})
            else:
                input_dict.update({k: [probe_list[i].get(k, "None") for i in range(len(probe_list))]})
        probes_metadata_dict['Probes'].extend(
            self._get_dynamictable_array(**input_dict)
        )
        return probes_metadata_dict

    @property
    def nwbfile_metadata(self):
        nwbfile_metadata_dict = self._initialize_container_dict('NWBFile')
        nwbfile_metadata_dict['NWBFile']['session_start_time'] = self._get_datetime(self.eid_session_info['start_time'])
        nwbfile_metadata_dict['NWBFile']['keywords'] = [','.join(self.eid_session_info['users']),
                                                             self.eid_session_info['lab'], 'IBL']
        nwbfile_metadata_dict['NWBFile']['experiment_description'] = self.eid_session_info['project']
        nwbfile_metadata_dict['NWBFile']['session_id'] = self.eid
        nwbfile_metadata_dict['NWBFile']['experimenter'] = self.eid_session_info['users']
        nwbfile_metadata_dict['NWBFile']['identifier'] = self.eid
        nwbfile_metadata_dict['NWBFile']['institution'] = \
            [i['institution'] for i in self.lab_table if i['name'] == [self.eid_session_info['lab']][0]][0]
        nwbfile_metadata_dict['NWBFile']['lab'] = self.eid_session_info['lab']
        nwbfile_metadata_dict['NWBFile']['protocol'] = self.eid_session_info['task_protocol']
        nwbfile_metadata_dict['NWBFile']['surgery'] = 'None'
        nwbfile_metadata_dict['NWBFile']['notes'] = self.eid_session_info['narrative']
        nwbfile_metadata_dict['NWBFile']['session_description'] = ','.join(self.eid_session_info['procedures'])
        return nwbfile_metadata_dict

    @property
    def sessions_metadata(self):
        sessions_metadata_dict = self._initialize_container_dict('IBLSessionsData')
        custom_fields = ['location','project','type','number','end_time',
                         'parent_session','url','extended_qc','qc','json']
        sessions_metadata_dict['IBLSessionsData'] = {i: str(self.eid_session_info[i]) if i not in ['procedures','number']
                                                        else self.eid_session_info[i] for i in custom_fields}
        sessions_metadata_dict['IBLSessionsData']['wateradmin_session_related'] = \
            [str(i) for i in self.eid_session_info['wateradmin_session_related']]
        return sessions_metadata_dict

    @property
    def subject_metadata(self):
        subject_metadata_dict = self._initialize_container_dict('IBLSubject')
        sub_table_dict = deepcopy(self.subject_table)
        if sub_table_dict:
            subject_metadata_dict['IBLSubject']['age'] = str(sub_table_dict.pop('age_weeks'))+' weeks'
            subject_metadata_dict['IBLSubject']['subject_id'] = sub_table_dict.pop('id')
            subject_metadata_dict['IBLSubject']['description'] = sub_table_dict.pop('description')
            subject_metadata_dict['IBLSubject']['genotype'] = ','.join(sub_table_dict.pop('genotype'))
            subject_metadata_dict['IBLSubject']['sex'] = sub_table_dict.pop('sex')
            subject_metadata_dict['IBLSubject']['species'] = sub_table_dict.pop('species')
            subject_metadata_dict['IBLSubject']['weight'] = str(sub_table_dict.pop('reference_weight'))
            subject_metadata_dict['IBLSubject']['date_of_birth'] = self._get_datetime(sub_table_dict.pop('birth_date'),format='%Y-%m-%d')
            # del sub_table_dict['weighings']
            # del sub_table_dict['water_administrations']
            subject_metadata_dict['IBLSubject'].update(sub_table_dict)
            subject_metadata_dict['IBLSubject']['weighings'] = [str(i) for i in subject_metadata_dict['IBLSubject']['weighings']]
            subject_metadata_dict['IBLSubject']['water_administrations'] = [str(i) for i in subject_metadata_dict['IBLSubject']['water_administrations']]
        return subject_metadata_dict

    @property
    def surgery_metadata(self):  # currently not exposed by api
        return dict()

    @property
    def behavior_metadata(self):
        behavior_metadata_dict = self._initialize_container_dict('Behavior')
        behavior_objects = ['wheel', 'wheelMoves', 'licks', 'lickPiezo', 'face', 'eye', 'camera']
        current_behavior_objects = self._get_current_object_names(behavior_objects)
        for k, u in enumerate(current_behavior_objects):
            if 'wheel' == u:
                behavior_metadata_dict['Behavior']['BehavioralTimeSeries'] = \
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')
            if 'wheelMoves' in u:
                behavior_metadata_dict['Behavior']['BehavioralEpochs'] = \
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'interval_series')
            if 'lickPiezo' in u:
                behavior_metadata_dict['Behavior']['BehavioralTimeSeries']['time_series'].extend(
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')['time_series'])
            if 'licks' in u:
                behavior_metadata_dict['Behavior']['BehavioralEvents'] = \
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')
            if 'face' in u:
                behavior_metadata_dict['Behavior']['BehavioralTimeSeries']['time_series'].extend(
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')['time_series'])
            if 'eye' in u:
                behavior_metadata_dict['Behavior']['PupilTracking'] = \
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')
            if 'camera' in u:
                behavior_metadata_dict['Behavior']['Position'] = \
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'spatial_series', name='camera_dlc')
        return behavior_metadata_dict

    @property
    def trials_metadata(self):
        trials_metadata_dict = self._initialize_container_dict('Trials')
        trials_objects = ['trials']
        current_trial_objects = self._get_current_object_names(trials_objects)
        for k, u in enumerate(current_trial_objects):
            if 'trial' in u:
                trials_metadata_dict = self._get_dynamictable_object(self.dataset_details.copy(), 'trials',
                                                                          'Trials',
                                                                          default_colnames_dict=dict(
                                                                              start_time='intervals',
                                                                              stop_time='intervals'))
        return trials_metadata_dict

    @property
    def stimulus_metadata(self):
        stimulus_objects = ['sparseNoise', 'passiveBeeps', 'passiveValveClick', 'passiveVisual', 'passiveWhiteNoise']
        stimulus_metadata_dict = self._initialize_container_dict('Stimulus')
        current_stimulus_objects = self._get_current_object_names(stimulus_objects)
        for k, u in enumerate(current_stimulus_objects):
            if 'sparseNoise' in u:
                stimulus_metadata_dict['Stimulus'] = \
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')
            if 'passiveBeeps' in u:
                stimulus_metadata_dict['Stimulus']['time_series'].extend(
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')['time_series'])
            if 'passiveValveClick' in u:
                stimulus_metadata_dict['Stimulus']['time_series'].extend(
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')['time_series'])
            if 'passiveVisual' in u:
                stimulus_metadata_dict['Stimulus']['time_series'].extend(
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')['time_series'])
            if 'passiveWhiteNoise' in u:
                stimulus_metadata_dict['Stimulus']['time_series'].extend(
                    self._get_timeseries_object(self.dataset_details.copy(), u, 'time_series')['time_series'])
        return stimulus_metadata_dict

    @property
    def device_metadata(self):
        device_metadata_dict = self._initialize_container_dict('Device', default_value=[])
        device_metadata_dict['Device'].extend(
            self._get_dynamictable_array(name=['NeuroPixels probe'],
                                         description=['NeuroPixels probe'])
            )
        return device_metadata_dict

    @property
    def units_metadata(self):
        units_objects = ['clusters', 'spikes']
        metrics_columns = ['cluster_id', 'cluster_id.1', 'num_spikes', 'firing_rate', 'presence_ratio',
                           'presence_ratio_std', 'isi_viol', 'amplitude_cutoff', 'amplitude_std', 'epoch_name',
                           'ks2_contamination_pct', 'ks2_label']

        units_metadata_dict = self._initialize_container_dict('Units')
        current_units_objects = self._get_current_object_names(units_objects)
        for k, u in enumerate(current_units_objects):
            if 'clusters' in u:
                units_metadata_dict = \
                    self._get_dynamictable_object(self.dataset_details.copy(), 'clusters', 'Units',
                                                  default_colnames_dict=dict(location='brainAcronyms',
                                                                             id='metrics',
                                                                             waveform_mean='waveforms',
                                                                             electrodes='channels',
                                                                             electrode_group='probes',
                                                                             ),
                                                  drop_attrs=['uuids'])
                units_metadata_dict['Units'].extend(
                    self._get_dynamictable_array(name=['obs_intervals', 'spike_times'],
                                                 data=['trials.intervals', 'spikes.clusters,spikes.times'],
                                                 description=['time intervals of each cluster',
                                                              'spike times of cluster']
                                                 ))
                units_metadata_dict['Units'].extend(
                    self._get_dynamictable_array(name=metrics_columns,
                                                 data=['clusters.metrics']*len(metrics_columns),
                                                 description=['metrics_table columns data']*len(metrics_columns)
                                                     ))
        return units_metadata_dict

    @property
    def electrodegroup_metadata(self):
        electrodes_group_metadata_dict = self._initialize_container_dict('ElectrodeGroup', default_value=[])
        for ii in range(len(self.probe_metadata['Probes'])):
            try:
                location_str = self.probe_metadata['Probes'][ii]['trajectory_estimate'][0]['coordinate_system']
            except:
                location_str = 'None'
            electrodes_group_metadata_dict['ElectrodeGroup'].extend(
                self._get_dynamictable_array(name=[self.probe_metadata['Probes'][ii]['name']],
                                             description=['model {}'.format(self.probe_metadata['Probes'][ii]['model'])],
                                             device=[self.device_metadata['Device'][0]['name']],
                                             location=['Mouse CoordinateSystem:{}'.format(
                                                 location_str)])
                )
        return electrodes_group_metadata_dict

    @property
    def electrodetable_metadata(self):
        electrodes_objects = ['channels']
        electrodes_table_metadata_dict = self._initialize_container_dict('ElectrodeTable')
        current_electrodes_objects = self._get_current_object_names(electrodes_objects)
        for i in current_electrodes_objects:
            electrodes_table_metadata_dict = self._get_dynamictable_object(
                self.dataset_details.copy(), 'channels', 'ElectrodeTable',
                default_colnames_dict=dict(group='probes',
                                           x='localCoordinates',
                                           y='localCoordinates'))
        return electrodes_table_metadata_dict

    @property
    def ecephys_metadata(self):
        ecephys_objects = ['templates', '_iblqc_ephysTimeRms', '_iblqc_ephysSpectralDensity']
        container_object_names = ['SpikeEventSeries', 'ElectricalSeries', 'Spectrum']
        custom_attrs_objects = [['waveforms'],['rms'],['power']]
        ecephys_container = self._initialize_container_dict('Ecephys')
        kwargs = dict()
        for i,j,k in zip(ecephys_objects,container_object_names,custom_attrs_objects):
            current_ecephys_objects = self._get_current_object_names([i])
            if current_ecephys_objects:
                if j=='Spectrum':
                    kwargs = dict(name=i, power='_iblqc_ephysSpectralDensity.power',
                                  frequencies='_iblqc_ephysSpectralDensity.freqs',
                                  timestamps=None)
                ecephys_container['Ecephys'].update(self._get_timeseries_object(
                    self.dataset_details.copy(), i, j, custom_attrs=k, **kwargs))
            else:
                warnings.warn(f'could not find {i} data in eid {self.eid}')
        return ecephys_container

    @property
    def acquisition_metadata(self):
        acquisition_objects = ['ephysData','_iblrig_Camera','_iblmic_audioSpectrogram']
        container_name_objects = ['TimeSeries','ImageSeries','DecompositionSeries']
        custom_attrs_objects = [['raw.nidq','raw.ap','raw.lf'],['raw'], ['power']]
        acquisition_container = self._initialize_container_dict('Acquisition')
        current_acquisition_objects = self._get_current_object_names(acquisition_objects)
        # if current_acquisition_objects != acquisition_objects:
        #     return dict()
        kwargs = dict()
        for i, j, k in zip(current_acquisition_objects, container_name_objects, custom_attrs_objects):
            if j == 'DecompositionSeries':
                kwargs=dict(name=i,metric='power',bands='_iblmic_audioSpectrogram.frequencies')
            acquisition_container['Acquisition'].update(self._get_timeseries_object(
                self.dataset_details.copy(), i, j, custom_attrs=k, **kwargs))
        return acquisition_container

    @property
    def ophys_metadata(self):
        raise NotImplementedError

    @property
    def icephys_metadata(self):
        raise NotImplementedError

    @property
    def scratch_metadata(self):
        # this can be used to add further details about subject, lab,
        raise NotImplementedError

    @property
    def complete_metadata(self):
        metafile_dict = {**self.eid_metadata,
                         **self.probe_metadata,
                         **self.nwbfile_metadata,
                         **self.sessions_metadata,
                         **self.subject_metadata,
                         **self.behavior_metadata,
                         **self.trials_metadata,
                         **self.stimulus_metadata,
                         **self.units_metadata,
                         **self.electrodetable_metadata,
                         'Ecephys': {**self.ecephys_metadata,
                                     **self.device_metadata,
                                     **self.electrodegroup_metadata,
                                      },
                         'Ophys': dict(),
                         'Icephys': dict(),
                         **self.acquisition_metadata}
        return metafile_dict

    def write_metadata(self, fileloc, savetype='.json'):
        full_metadata = self.complete_metadata
        if Path(fileloc).suffix != savetype:
            raise ValueError(f'fileloc filetype should of of type {savetype}')
        if savetype=='.json':
            full_metadata['NWBFile']['session_start_time'] = str(full_metadata['NWBFile']['session_start_time'])
            full_metadata['IBLSubject']['date_of_birth'] = str(full_metadata['IBLSubject']['date_of_birth'])
            with open(fileloc, 'w') as f:
                json.dump(full_metadata, f, indent=2)
        elif savetype in ['.yaml', '.yml']:
            with open(fileloc, 'w') as f:
                yaml.dump(full_metadata, f, default_flow_style=False)
        print(f'data written in {fileloc}')

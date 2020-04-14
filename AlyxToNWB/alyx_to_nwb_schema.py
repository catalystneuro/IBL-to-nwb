
from oneibl.one import ONE
from .schema import metafile as nwb_schema
from .schema import template_metafile as nwb_schema_template
from .schema import dataset_format_list
from .schema import dataset_details_list

class Alyx2NWBSchema:

    def __init__(self, eid=None, one_obj: ONE = None, **one_kwargs):
        self._one_obj = one_obj
        self.one_kwargs = one_kwargs
        self.schema_template=nwb_schema_template
        self.schema=nwb_schema
        if not one_obj:
            self.one_obj = ONE()
        elif not isinstance(one_obj, ONE):
            raise Exception('one_obj is not of ONE class')
        self.eid_list=self._get_eid_list()
        self.eid_session_info = self._retrieve_eid_endpoint()
        self.dataset_type_list=self._list_eid_metadata('dataset_type')
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
            dataset_dict=self.eid_session_info[val]['data_dataset_session_related']
            list_type_returned[val]=[i['name'] for i in dataset_dict]
        return list_type_returned

    def _list_eid_metadata(self,list_type):
        list_type_returned=[None]*len(self.eid_list)
        for val, e_id in enumerate(self.eid_list):
            list_type_returned = self.one_obj.list(e_id, list_type)
        return list_type_returned

    def _retrieve_eid_endpoint(self):
        eid_sess_info=[None]*len(self.eid_list)
        for val, ceid in enumerate(self.eid_list):
            eid_sess_info[val]=self.one_obj.alyx.rest('sessions/'+ceid, 'list')
        return eid_sess_info

    def _get_lab_table(self):
        self.lab_table=self.one_obj.alyx.rest('labs', 'list')

    def _get_subject_table(self):
        self.subject_table= self.one_obj.alyx.rest('subject/'+ self.eid_session_info['subject'],'list')

    def _dataset_type_parse(self):
        '''
        :return: list of dict. Each item as a dict with values as list of dict with keys: name and description
        -<dataset object name>: (eg. spikes, clusters etc)
            name: objects attribute type (eg. times, intervals etc
            description: attributes description
            extension: dataset type(npy, csv)
        '''
        dataset_type_list=[None]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            dataset_description_list=dict()
            for data_id in dataset_details_list:
                dataset_description_list[data_id['name']]=data_id['description']
            split_list_objects=[i.split('.')[0] for i in self.dataset_type_list[val]]
            split_list_attributes = [i.split('.')[-1] for i in self.dataset_type_list[val]]
            dataset_description = [dataset_description_list[i] for i in self.dataset_type_list[val]]
            dataset_extension = [u['name'].split('.')[-1] for u in self.eid_session_info['data_dataset_session_related']]
            split_list_objects_dict=dict()
            for obj in set(split_list_objects):
                split_list_objects_dict[obj]=dict()
            for att_idx, attrs in enumerate(split_list_attributes):
                split_list_objects_dict[split_list_objects[att_idx]]={'name':attrs,
                                                                      'description':dataset_description[att_idx],
                                                                      'extension': dataset_extension[att_idx] }
            dataset_type_list[val]=split_list_objects_dict
        return dataset_type_list

    def set_eid_metadata(self):
        return dict(eid=self.eid_list)

    def set_nwbfile_metadata(self):
        nwbfile_metadata_dict=[dict()]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            nwbfile_metadata_dict[val]['session_start_time'] =self.eid_session_info['start_time']
            nwbfile_metadata_dict[val]['keywords'] = self.eid_session_info['start_time']
            nwbfile_metadata_dict[val]['experiment_description'] =self.eid_session_info['narrative']
            nwbfile_metadata_dict[val]['session_id'] =Ceid
            nwbfile_metadata_dict[val]['experimenter']=','.join(self.eid_session_info['users'])
            nwbfile_metadata_dict[val]['identifier'] =Ceid
            nwbfile_metadata_dict[val]['institution'] =\
                [i['institution'] for i in self.lab_table if i['name']==[self.eid_session_info['lab']][0]]
            nwbfile_metadata_dict[val]['lab'] =self.eid_session_info['lab']
            nwbfile_metadata_dict[val]['session_description'] =self.eid_session_info['task_protocol']
            nwbfile_metadata_dict[val]['surgery'] ='None'
            nwbfile_metadata_dict[val]['notes'] = 'Procedures:'+','.join(self.eid_session_info['procedures'])\
                                                    + ', Project:'+ self.eid_session_info['project']

        return nwbfile_metadata_dict

    def set_subject_metadata(self):
        subject_metadata_dict = [dict()]*len(self.eid_list)
        for val, Ceid in enumerate(self.eid_list):
            subject_metadata_dict[val]['subject_id']=self.subject_table['id']
            subject_metadata_dict[val]['description'] = self.subject_table['description']
            subject_metadata_dict[val]['genotype'] = ','.join(self.subject_table['genotype'])
            subject_metadata_dict[val]['sex'] = self.subject_table['sex']
            subject_metadata_dict[val]['species'] = self.subject_table['species']
            subject_metadata_dict[val]['weight'] = self.subject_table['weighings'][0]['weight']
            subject_metadata_dict[val]['date_of_birth'] = self.subject_table['birth_date']
        return subject_metadata_dict

    def set_surgery_metadata(self):#currently not exposed by api
        surgery_metadata_dict=[dict()]*len(self.eid_list)
        return surgery_metadata_dict

    def _unpack_dataset_details(self,dataset_key, dataset_val):
        outlist=[]
        for i in dataset_key:
            if i in dataset_val:
                out1=[j['name'] for j in dataset_val[i]]
                out2 = [k['description'] for k in dataset_val[i]]
            else:
                out1=[]
                out2=[]
            outlist.append([out1,out2])
         return outlist

    def set_behavior_metadata(self):
        behavior_metadata_dict = [dict()]*len(self.eid_list)
        behavior_objects = ['wheel', 'wheelMoves', 'licks', 'lickPiezo', 'face', 'eye']
        for val, Ceid in enumerate(self.eid_list):
            behavior_object_details=self._unpack_dataset_details(behavior_objects, self.dataset_details[val])
                for k in range(behavior_object_details):
                    if behavior_object_details[k][0]:
                        if 'time' in behavior_object_details[k][0]:
                            behavior_metadata_dict[val]['Behavior']['BehavioralTimeSeries']['name']= \
                                behavior_objects[k] + behavior_object_details[k][0]
                            behavior_metadata_dict[val]['Behavior']['BehavioralTimeSeries']['description'] = \
                                behavior_object_details[k][1]
                            behavior_metadata_dict[val]['Behavior']['BehavioralTimeSeries']['timestamps'] = \
                                behavior_object_details[k][1]

            self.dataset_details
        return behavior_metadata_dict

    def set_trials_data(self):
        trials_objects=['trials']
        pass

    def set_stimulus_metadata(self):
        stimulus_objects=['sparseNoise','passiveBeeps','passiveValveClick','passiveVisual','passiveWhiteNoise']

    def set_device_metadata(self):
        device_objects=['probes']

    def set_units_metadata(self):
        units_objcts=['clusters','spikes']

    def set_electrodes_metadata(self):
        electrodes_objects=['probes','channels']

    def set_ecephys_metadata(self):
        return ecephys_metadata_dict

    def set_ophys_metadata(self):
        return ophys_metadata_dict

    def set_scratch_metadata(self):
        # this can be used to add further details about subject, lab,
        pass

    def set_device_metadata(self):
        #currently unavailable
        pass

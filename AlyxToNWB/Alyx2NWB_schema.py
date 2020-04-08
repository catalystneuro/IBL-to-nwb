
from oneibl.one import ONE
from .schema import metafile as nwb_schema
from .schema import template_metafile as nwb_schema_template

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
        self.eid=self._get_eid_list()
        self.dataset_type_list=self._list_eid_metadata('dataset_type')
        self.users_list = self._list_eid_metadata('users')
        self.subjects_list = self._list_eid_metadata('subjects')
        self.labs_list = self._list_eid_metadata('labs')
        self.eid_session_info=self._retrieve_eid_endpoint()
        self._get_lab_table()
        self._get_subject_table()

    def _get_eid_list(self):
        if self.eid:
            if not isinstance(self.eid, list):
                self.eid = [self.eid]
        else:
            self.eid = self._one_obj.search(**self.one_kwargs)
        return self.eid

    def _list_eid_metadata(self,list_type):
        list_type_returned=[None]*len(self.eid)
        for val, e_id in enumerate(self.eid):
            list_type_returned = self.one_obj.list(e_id, list_type)
        return list_type_returned

    def _retrieve_eid_endpoint(self):
        eid_sess_info=[None]*len(self.eid)
        for val, ceid in enumerate(self.eid):
            eid_sess_info[val]=self.one_obj.alyx.rest('sessions/'+ceid, 'list')
        return eid_sess_info

    def _get_lab_table(self):
        self.lab_table=self.one_obj.alyx.rest('labs', 'list')

    def _get_subject_table(self):
        self.subject_table= self.one_obj.alyx.rest('subject/'+ self.eid_session_info['subject'],'list')

    def _dataset_type_parse(self):
        dataset_type_list=[None]*len(self.eid)
        for val, Ceid in enumerate(self.eid):
            split_list_objects=[i.split('.')[0] for i in self.dataset_type_list[val]]
            split_list_attributes = [i.split('.')[-1] for i in self.dataset_type_list[val]]
            split_list_objects_dict=dict()
            for obj in set(split_list_objects):
                split_list_objects_dict[obj]=[]
            for att_idx, attrs in enumerate(split_list_attributes):
                split_list_objects_dict[split_list_objects[att_idx]].append(attrs)
            dataset_type_list[val]=split_list_objects_dict
        return dataset_type_list

    def set_nwbfile_metadata(self):
        nwbfile_metadata_dict=[dict()]*len(self.eid)
        for val, Ceid in enumerate(self.eid):
            nwbfile_metadata_dict[val]['session_start_time'] =self.eid_session_info['start_time']
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

    def get_subject_metadata(self):
        subject_metadata_dict = [dict()]*len(self.eid)
        for val, Ceid in enumerate(self.eid):
            subject_metadata_dict[val]['subject_id']=self.subject_table['id']
            subject_metadata_dict[val]['description'] = self.subject_table['description']
            subject_metadata_dict[val]['genotype'] = ','.join(self.subject_table['genotype'])
            subject_metadata_dict[val]['sex'] = self.subject_table['sex']
            subject_metadata_dict[val]['species'] = self.subject_table['species']
            subject_metadata_dict[val]['weight'] = self.subject_table['weighings'][0]['weight']
            subject_metadata_dict[val]['date_of_birth'] = self.subject_table['birth_date']
        return subject_metadata_dict

    def get_surgery_metadata(self):#currently not exposed by api
        surgery_metadata_dict=[dict()]*len(self.eid)
        return surgery_metadata_dict

    def get_behavior_metadata(self):
        return behavior_metadata_dict

    def get_trials_data(self):

    def get_ecephys_metadata(self):
        return ecephys_metadata_dict

    def get_ophys_metadata(self):
        return ophys_metadata_dict

    def get_scratch_metadata(self):
        # this can be used to add further details about subject, lab,
        pass

    def get_device_metadata(self):
        #currently unavailable
        pass

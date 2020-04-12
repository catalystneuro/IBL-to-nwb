from nwbn_conversion_tools import NWBConverter
import os
import jsonschema
import IBL_to_NWB
from .schema import dataset_format_list

class Alyx2NWBConverter(NWBConverter):


    def __init__(self, nwbfile=None, nwb_schema=None, saveloc=None):
        if ~nwb_schema:
            raise Exception('nwb_schema not provided')
        elif jsonschema.validate(nwb_schema,IBL_to_NWB.metadata_schema):
            self.nwb_schema=nwb_schema


        if ~nwbfile:
            self.nwbfile=self.create_nwb_file(**nwb_schema['NWBFile'])

        if ~saveloc:
            Warning('saving in current working directory')
            self.saveloc=os.getcwd()

    def create_nwb_file(self):
        pass

    def create_processing_module(self):
        pass

    def add_processing(self):
        pass

    def create_subject(self):
        pass

    def add_subject(self):
        pass

    def create_behavior(self):
        pass

    def add_behavior(self):
        pass

    def _get_data(self,sub_schema):
        '''
        :param sub_schema: schema containing a data field with a dataset type to retrieve data from(npy, tsv etc)
        :return:
        '''
        # dataset_type_list_desc=[dataset_format_list[i]['description'] for i in dataset_format_list]
        dataset_type_list_ext = [dataset_format_list[i]['extension'] for i in dataset_format_list]
        dataset_type_list_loaderfun = [dataset_format_list[i]['python_loader_function'] for i in dataset_format_list]
        dataset_listid=dataset_type_list_ext.index(sub_schema['data'][-4::])
        dataset_loader_function=dataset_type_list_loaderfun[dataset_listid]
        return self.one.load(self.nwb_schema["eid"][0],dataset_types=[sub_schema['data']])
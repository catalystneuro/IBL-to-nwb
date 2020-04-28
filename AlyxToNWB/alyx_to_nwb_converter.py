import os
import json
import pandas as pd
import jsonschema
import IBL_to_NWB
from nwbn_conversion_tools import NWBConverter
from .schema import dataset_format_list
from oneibl.one import ONE
import pynwb.behavior
import pynwb.ecephys
import pynwb

class Alyx2NWBConverter(NWBConverter):

    def __init__(self, nwbfile=None, saveloc=None,
                 nwb_metadata: dict=None,
                 metadata_obj: Alyx2NWBSchema = None,
                 one_object: ONE = None):

        if not nwb_metadata & ~metadata_obj & ~one_object:
            raise Exception('provide a json schema + one_object or a Alyx2NEBSchema object as argument')

        if not nwb_metadata:
            if jsonschema.validate(nwb_metadata, IBL_to_NWB.metadata_schema):
                self.nwb_metadata = nwb_metadata

        if not metadata_obj:
            self.metadata_obj = metadata_obj
        else:
            self.metadata_obj = json.loads(nwb_metadata)

        if not one_object:
            self.one_object = one_object
        else:
            self.one_object = metadata_obj.one_obj

        if not saveloc:
            Warning('saving nwb file in current working directory')
            self.saveloc = os.getcwd()
        else:
            self.saveloc = saveloc

        self.eid = self.nwb_metadata["eid"][0]
        super(Alyx2NWBConverter, self).__init__(nwb_metadata, nwbfile)

    def create_processing_module(self):
        pass

    def add_processing(self):
        pass

    def create_electrodes_ecephys(self):
        pass

    def create_electrode_groups(self):
        pass

    def create_devices(self):
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
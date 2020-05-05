import os
import json
import pandas as pd
import numpy as np
from copy import deepcopy
from datetime import datetime
import jsonschema
from nwb_conversion_tools import NWBConverter
from oneibl.one import ONE
import pynwb.behavior
import pynwb.ecephys
import pynwb
from .alyx_to_nwb_metadata import Alyx2NWBMetadata
from .schema import metafile


class Alyx2NWBConverter(NWBConverter):

    def __init__(self, nwbfile=None, saveloc=None,
                 nwb_metadata_file=None,
                 metadata_obj: Alyx2NWBMetadata = None,
                 one_object=None):

        if not (nwb_metadata_file == None):
            if isinstance(nwb_metadata_file, dict):
                self.nwb_metadata = nwb_metadata_file
            elif isinstance(nwb_metadata_file, str):
                with open(nwb_metadata_file, 'r') as f:
                    self.nwb_metadata = json.load(f)
            # jsonschema.validate(nwb_metadata_file, metafile)
        elif not (metadata_obj == None):
            if len(metadata_obj.complete_metadata) > 1:
                num = int(input(f'{metadata_obj.complete_metadata}'
                                'eids found, input a number [0-no_eids] to make nwb from'))
                if num > len(metadata_obj.complete_metadata):
                    raise Exception('number entered greater than number of eids')
                self.nwb_metadata = metadata_obj.complete_metadata[num]
            else:
                self.nwb_metadata = metadata_obj.complete_metadata[0]
        else:
            raise Exception('required one of argument: nwb_metadata_file OR metadata_obj')
        if not (one_object == None):
            self.one_object = one_object
        elif not (metadata_obj == None):
            self.one_object = metadata_obj.one_obj
        else:
            Warning('creating a ONE object and continuing')
            self.one_object = ONE()
        if not (saveloc == None):
            Warning('saving nwb file in current working directory')
            self.saveloc = os.getcwd()
        else:
            self.saveloc = saveloc

        self.eid = self.nwb_metadata["eid"][0]
        super(Alyx2NWBConverter, self).__init__(nwb_metadata, nwbfile)

    def create_stimulus(self):
        stimulus_list = self._get_data(self.nwb_metadata['Stimulus']['time_series'])
        for i in stimulus_list:
            self.nwbfile.add_stimulus(pynwb.TimeSeries(**i))  # TODO: donvert timeseries data to starting_time and rate

    def create_units(self):
        unit_table_list = self._get_data(self.nwb_metadata['Units'])
        for j in range(len(unit_table_list[0]['data'])):
            self.nwbfile.add_unit(id=j)
        for i in unit_table_list:
            self.nwbfile.add_unit_column(name=i['name'],
                                         description=i['description'],
                                         data=i['data'])

    def create_electrodes_ecephys(self):
        electrode_table_list = self._get_data(self.nwb_metadata['ElectrodeTable'])
        for j in range(len(electrode_table_list[0]['data'])):
            self.nwbfile.add_electrode(x=float('NaN'),
                                       y=float('NaN'),
                                       z=float('NaN'),
                                       imp=float('NaN'),
                                       location=f'location{j}',  # TODO: location needs to be found from ibl datatype
                                       group=f'group{j}',
                                       filtering='none'
                                       )
        for i in electrode_table_list:
            self.nwbfile.add_electrode_column(name=i['name'],
                                              description=i['description'],
                                              data=i['data'])

    def create_timeseries_ecephys(self):
        super(Alyx2NWBConverter, self).check_module('Ecephys')
        spikeeventseries_table_list = self._get_data(self.nwb_metadata['Ecephys']['EventDetection']['SpikeEventSeries'])
        for i in spikeeventseries_table_list:
            self.nwbfile.processing['Ecephys'].add(
                pynwb.ecephys.EventDetection(
                    detection_method=i['description'],
                    source_electricalseries=pynwb.ecephys.SpikeEventSeries(**i)
                )  # TODO: add method to find the electrodes using spikes.channels datatype
            )

    def create_behavior(self):
        super(Alyx2NWBConverter, self).check_module('Behavior')
        for i in self.nwbfile['Behavior']:
            if not i == 'Position':
                time_series_func = pynwb.TimeSeries
            else:
                time_series_func = pynwb.behavior.SpatialSeries

            time_series_list_details = self._get_data(self.nwbfile['Behavior'][i]['time_series'])
            time_series_list_obj = [time_series_func(**i) for i in time_series_list_details]
            func = getattr(pynwb.behavior, i)
            self.nwbfile.processing['Behavior'].add(func(time_series=time_series_list_obj))

    def create_trials(self):
        trial_df = self._table_to_df(self.nwb_metadata['Trials'])
        super(Alyx2NWBConverter, self).create_trials_from_df(trial_df)

    def add_trial_columns(self, df):
        super(Alyx2NWBConverter, self).add_trials_from_df(df)

    def add_trial_row(self, df):
        super(Alyx2NWBConverter, self).add_trials_from_df(df)

    def _table_to_df(self, table_metadata):
        """
        :param table_metadata: array containing dictionaries with name, data and description for the column
        :return: df_out: data frame conversion
        """
        data_dict = dict()
        _ = [data_dict.update({i['name']: self.one_object.load(self.eid, dataset_types=[i['data']])}) \
             for i in table_metadata]
        df_out = pd.DataFrame(data=data_dict)
        return df_out

    def _get_data(self, sub_metadata):
        """
        :param sub_metadata: metadata dict containing a data field with a dataset type to retrieve data from(npy, tsv etc)
        :return: out_dict: dictionary with actual data loaded in the data field
        """
        out_dict = sub_metadata
        if isinstance(sub_metadata, list):
            for i in sub_metadata:
                out_dict[i]['data'] = self.one_object.load(self.eid, dataset_types=[sub_metadata['data']])
                if out_dict[i].get('timestamps'):
                    out_dict[i]['timestamps'] = self.one_object.load(self.eid,
                                                                     dataset_types=[sub_metadata['timestamps']])
        else:
            out_dict['data'] = self.one_object.load(self.eid, dataset_types=[sub_metadata['data']])
            if out_dict.get('timestamps'):
                out_dict['timestamps'] = self.one_object.load(self.eid, dataset_types=[sub_metadata['timestamps']])

        return out_dict

    def write_nwb(self):
        super(Alyx2NWBConverter, self).save(self.saveloc)

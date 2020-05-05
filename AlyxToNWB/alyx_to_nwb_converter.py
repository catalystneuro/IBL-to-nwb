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
        self.eid = self.nwb_metadata["eid"]
        self.nwb_metadata['NWBFile']['session_start_time'] = \
            datetime.strptime(self.nwb_metadata['NWBFile']['session_start_time'], '%Y-%m-%dT%X')
        self.nwb_metadata['Subject']['date_of_birth'] = \
            datetime.strptime(self.nwb_metadata['Subject']['date_of_birth'], '%Y-%m-%d')
        super(Alyx2NWBConverter, self).__init__(self.nwb_metadata, nwbfile)
        self._loaded_datasets = dict()
        self.unit_table_length = None

    def create_stimulus(self):
        stimulus_list = self._get_data(self.nwb_metadata['Stimulus'].get('time_series'))
        for i in stimulus_list:
            self.nwbfile.add_stimulus(pynwb.TimeSeries(**i))  # TODO: donvert timeseries data to starting_time and rate

    def create_units(self):
        unit_table_list = self._get_data(self.nwb_metadata['Units'])
        default_args = ['id', 'waveform_mean','electrodes','electrode_group','spike_times','obs_intervals']
        default_ids = self._get_default_column_ids(default_args, [i['name'] for i in unit_table_list])
        non_default_ids = list(set(range(len(unit_table_list))).difference(set(default_ids)))
        default_dict=dict()
        [default_dict.update({unit_table_list[i]['name']:unit_table_list[i]['data']}) for i in default_ids]
        for j in range(len(unit_table_list[0]['data'])):
            add_dict=dict().copy()
            for i in default_dict.keys():
                if i == 'electrodes':
                    add_dict.update({i: [default_dict[i][j]]})
                elif i == 'obs_intervals':
                    add_dict.update({i: default_dict[i]})
                elif i == 'electrode_group':
                    self.create_electrode_groups(self.nwb_metadata['Ecephys'])
                    add_dict.update({i:self.nwbfile.electrode_groups[f'Probe{default_dict[i][j]}']})
                else:
                    add_dict.update({i: default_dict[i][j]})
            self.nwbfile.add_unit(**add_dict)

        for i in non_default_ids:
            self.nwbfile.add_unit_column(name=unit_table_list[i]['name'],
                                         description=unit_table_list[i]['description'],
                                         data=unit_table_list[i]['data'])

    def create_electrode_table_ecephys(self):
        self.create_electrode_groups(self.nwb_metadata['Ecephys'])
        electrode_table_list = self._get_data(self.nwb_metadata['ElectrodeTable'])
        default_args = ['group']
        default_ids = self._get_default_column_ids(default_args, [i['name'] for i in electrode_table_list])
        for j in range(len(electrode_table_list[0]['data'])):
            if default_ids:
                group_data = self.nwbfile.electrode_groups['Probe{}'.format(electrode_table_list[default_ids[0]]['data'][j])]
            else:# else fill with probe zero data.
                group_data = self.nwbfile.electrode_groups[f'Probe{0}']
            self.nwbfile.add_electrode(x=float('NaN'),
                                       y=float('NaN'),
                                       z=float('NaN'),
                                       imp=float('NaN'),
                                       location=f'location{j}',
                                       group=group_data,
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
            if not (i == 'Position'):
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

    def _resize_data(self, data, max_size):
        if max_size is None:
            return data
        ls_out=[[None]]*max_size
        for i in data:
            ls_out[i[0]]=i[1]
        return ls_out

    def _get_default_column_ids(self,default_namelist,namelist):
        out_idx = []
        for j,i in enumerate(namelist):
            if i in default_namelist:
                out_idx.extend([j])
        return out_idx

    def _table_to_df(self, table_metadata):
        """
        :param table_metadata: array containing dictionaries with name, data and description for the column
        :return: df_out: data frame conversion
        """
        data_dict = dict()
        for i in table_metadata:
            if i['name'] in 'start_time':
                data_dict.update({i['name']: self.one_object.load(self.eid, dataset_types=[i['data']])[0][:, 0]})
            elif i['name'] in 'stop_time':
                data_dict.update({i['name']: self.one_object.load(self.eid, dataset_types=[i['data']])[0][:, 1]})
            else:
                data_dict.update({i['name']: self.one_object.load(self.eid, dataset_types=[i['data']])[0]})
        df_out = pd.DataFrame(data_dict)
        return df_out

    def _get_multiple_data(self, datastring, max_len=None):
        """
        This method is current specific to units table to retrieve spike times for a given cluster
        Parameters
        ----------
        datastring: str
            csv of datasets
        Returns
        -------
        numpy array
            with the spike time data
        """
        # TODO: there will be two max_len for each probe: from cluster.channels length: 713, 331 clusters for probe 1 and probe 2
        spike_clusters, spike_times = datastring.split(',')
        spike_cluster_data = self.one_object.load(self.eid, dataset_types=[spike_clusters])[0].tolist()
        spike_times_data = self.one_object.load(self.eid, dataset_types=[spike_times])[0].tolist()
        if not ((spike_cluster_data is None) | (spike_cluster_data is None)):
            df = pd.DataFrame({'sp_cluster': spike_cluster_data, 'sp_times': spike_times_data})
            df_group = df.groupby(['sp_cluster'])['sp_times'].apply(list).reset_index(name='sp_times_group')
            return self._resize_data(df_group.values,max_len) # TODO: put zeros where the group by does not yeield any output
        else:
            return None

    def _load(self, dataset_to_load, dataset_key):
        if dataset_to_load not in self._loaded_datasets.keys():
            if len(dataset_to_load.split(',')) == 1:
                load_data = self.one_object.load(self.eid, dataset_types=[dataset_to_load])[0]
                if isinstance(load_data,pd.DataFrame):
                    # assuming all columns exist as colnames for the table in the json file:
                    self._loaded_datasets.update({dataset_to_load:load_data[dataset_key].to_list()})
                    return load_data[dataset_key].to_list()
                elif load_data is None:
                    return None #TODO: length will be 2 for all datasets. except for trials table.
                elif len(load_data)==2:# will do in case of spikes.* Dim 2 is for teh two probes.
                    return load_data
                else:
                    if self.unit_table_length is None:
                        self.unit_table_length = len(load_data)
                return load_data.tolist()
            else:
                load_data = self._get_multiple_data(dataset_to_load, self.unit_table_length)
                self._loaded_datasets.update({dataset_to_load:load_data})
            return load_data
        else:
            if isinstance(self._loaded_datasets[dataset_to_load], pd.DataFrame):
                return self._loaded_datasets[dataset_to_load][dataset_key]
            elif self._loaded_datasets[dataset_to_load] is None:
                return None
            else:
                return self._loaded_datasets[dataset_to_load]

    def _get_data(self, sub_metadata):# TODO: add an argument for no_loops: trials is 1 but for units (clusters) its 2 since there ae two probes data..
        """
        :param sub_metadata: metadata dict containing a data field with a dataset type to retrieve data from(npy, tsv etc)
        :return: out_dict: dictionary with actual data loaded in the data field
        """

        include_idx = []
        out_dict_trim = []
        if isinstance(sub_metadata, list):

            # unit_table_length = None
            out_dict = deepcopy(sub_metadata)
            print('a')
        elif isinstance(sub_metadata,dict):
            out_dict = deepcopy(list(sub_metadata))
        else:
            print('out')
            return []
            # cluster_df = None
        for i, j in enumerate(out_dict):  # TODO: verify that the size two array that many return corresponds to the two probes.
            # if not j.get('description') == 'no_description':  # when there is no data for the given eid
            # include_idx.extend([i])
            if out_dict[i].get('timestamps'):
                out_dict[i]['timestamps'] = self._load(j['timestamps'],j['name'])
            if j['name'] == 'id':# valid in case of units table.
                out_dict[i]['data'] = self._load(j['data'], 'cluster_id')
            else:
                out_dict[i]['data'] = self._load(j['data'], j['name'])
            if out_dict[i]['data'] is not None:
                include_idx.extend([i])

                # if not (j.get('data') == 'clusters.metrics'):
                #     if len(j.get('data').split(',')) == 1:
                #         data0 = self.one_object.load(self.eid, dataset_types=[j['data']])[0]
                #         if isinstance(data0,pd.DataFrame):
                #             out_dict[i]['data'] = data0.to_numpy().tolist()
                #         else:
                #             out_dict[i]['data'] = data0.tolist()
                #         if out_dict[i].get('timestamps'):
                #             out_dict[i]['timestamps'] = \
                #             self.one_object.load(self.eid, dataset_types=[j['timestamps']])[0].tolist()
                #         if unit_table_length is None:
                #             unit_table_length = len(out_dict[i]['data'])
                #     else:  # this part of code is exclusive to units table for spikes times:
                #         temp = self._get_multiple_data(j.get('data'), unit_table_length)
                #         if not (temp is None):
                #             out_dict[i]['data'] = temp
                #         else:  # if either of the data was not found, (returned None) then exclude that index
                #             include_idx = include_idx[:-1]
                # else:
                #     if cluster_df is None:  # to load only once
                #         cluster_df = self.one_object.load(self.eid, dataset_types=[j['data']])[0]
                #     if j['name'] == 'id':
                #         out_dict[i]['data'] = cluster_df['cluster_id'].to_list()
                #     else:
                #         out_dict[i]['data'] = cluster_df[j['name']].to_list()

        out_dict_trim.extend([out_dict[j] for j in include_idx])
        return out_dict_trim
        # elif not (sub_metadata == None):
        #     out_dict = deepcopy(sub_metadata)
        #     if sub_metadata:  # if it is not an empty dict
        #         out_dict['data'] = self._load(j['data'])
        #         out_dict['data'] = self.one_object.load(self.eid, dataset_types=[sub_metadata['data']])[0].tolist()
        #         if out_dict.get('timestamps'):
        #             out_dict['timestamps'] = self.one_object.load(self.eid, dataset_types=[sub_metadata['timestamps']])[
        #                 0].tolist()
        #         return out_dict
        #     else:
        #         return []
        # elif (sub_metadata == None):
        #     return []

    def write_nwb(self):
        super(Alyx2NWBConverter, self).save(self.saveloc)

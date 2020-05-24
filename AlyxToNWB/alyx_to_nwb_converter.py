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
        if saveloc is None:
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
        self.electrode_table_length = None
        self.electrode_table_exist = False

    def create_stimulus(self):
        stimulus_list = self._get_data(self.nwb_metadata['Stimulus'].get('time_series'))
        for i in stimulus_list:
            self.nwbfile.add_stimulus(pynwb.TimeSeries(**i))  # TODO: donvert timeseries data to starting_time and rate

    def create_units(self):
        unit_table_list = self._get_data(self.nwb_metadata['Units'], probes=2)
        # no required arguments for units table. Below are default columns in the table.
        default_args = ['id', 'waveform_mean','electrodes','electrode_group','spike_times','obs_intervals']
        default_ids = self._get_default_column_ids(default_args, [i['name'] for i in unit_table_list])
        non_default_ids = list(set(range(len(unit_table_list))).difference(set(default_ids)))
        default_dict=dict()
        [default_dict.update({unit_table_list[i]['name']:unit_table_list[i]['data']}) for i in default_ids]
        for j in range(len(unit_table_list[0]['data'])):
            add_dict=dict()
            for i in default_dict.keys():
                if i == 'electrodes':
                    add_dict.update({i: [default_dict[i][j]]})
                elif i == 'obs_intervals':
                    add_dict.update({i: default_dict[i]})
                elif i == 'electrode_group':
                    self.create_electrode_groups(self.nwb_metadata['Ecephys'])
                    add_dict.update({i:self.nwbfile.electrode_groups[f'Probe{default_dict[i][j]}']})
                elif i == 'id':
                    if j >= self.unit_table_length[0]:
                        add_dict.update({i: default_dict[i][j]+self.unit_table_length[0]})
                    else:
                        add_dict.update({i: default_dict[i][j]})
                elif i == 'waveform_mean':
                    add_dict.update({i: np.mean(default_dict[i][j],axis=1)})# finding the mean along all the channels of the sluter
            self.nwbfile.add_unit(**add_dict)

        for i in non_default_ids:
            if isinstance(unit_table_list[i]['data'],object):
                unit_table_list[i]['data']=unit_table_list[i]['data'].tolist()# convert string numpy
            self.nwbfile.add_unit_column(name=unit_table_list[i]['name'],
                                         description=unit_table_list[i]['description'],
                                         data=unit_table_list[i]['data'])

    def create_electrode_table_ecephys(self):
        if self.electrode_table_exist:
            pass
        self.create_electrode_groups(self.nwb_metadata['Ecephys'])
        electrode_table_list = self._get_data(self.nwb_metadata['ElectrodeTable'], probes=2)
        # electrode table has required arguments:
        required_args = ['group', 'x', 'y']
        default_ids = self._get_default_column_ids(required_args, [i['name'] for i in electrode_table_list])
        non_default_ids = list(set(range(len(electrode_table_list))).difference(set(default_ids)))
        default_dict = dict()
        [default_dict.update({electrode_table_list[i]['name']: electrode_table_list[i]['data']}) for i in default_ids]
        if 'group' in default_dict.keys():
            group_labels = default_dict['group']
        else:  # else fill with probe zero data.
            group_labels = np.concatenate([np.zeros(self.electrode_table_length[0],dtype=int),
                                           np.ones(self.electrode_table_length[1],dtype=int)])
        for j in range(len(electrode_table_list[0]['data'])):
            if 'x' in default_dict.keys():
                x = default_dict['x'][j][0]
                y = default_dict['y'][j][1]
            else:
                x = float('NaN')
                y = float('NaN')
            group_data = self.nwbfile.electrode_groups[
                    'Probe{}'.format(group_labels[j])]
            self.nwbfile.add_electrode(x=x,
                                       y=y,
                                       z=float('NaN'),
                                       imp=float('NaN'),
                                       location='None',
                                       group=group_data,
                                       filtering='none'
                                       )
        for i in non_default_ids:
            self.nwbfile.add_electrode_column(name=electrode_table_list[i]['name'],
                                              description=electrode_table_list[i]['description'],
                                              data=electrode_table_list[i]['data'])
        self.electrode_table_exist = True

    def create_timeseries_ecephys(self):
        if not self.electrode_table_exist:
            self.create_electrode_table_ecephys()
        super(Alyx2NWBConverter, self).check_module('Ecephys')
        spikeeventseries_table_list = self._get_data(self.nwb_metadata['Ecephys']['EventDetection']['SpikeEventSeries'],
                                                     probes=2)
        for i in spikeeventseries_table_list:
            for j in range(2):
                self.nwbfile.processing['Ecephys'].add(
                    pynwb.ecephys.SpikeEventSeries(name=i['name']+f'Probe{j}',
                                                   description=i['description'],
                                                   timestamps=i['timestamps'][j],
                                                   data=i['data'][j],
                                                   electrodes=self.nwbfile.create_electrode_table_region(
                                                       description=f'Probe{j}',
                                                       region=list(range(self.electrode_table_length[j])))
                                                   )
            )

    def create_behavior(self):
        super(Alyx2NWBConverter, self).check_module('Behavior')
        for i in self.nwb_metadata['Behavior']:
            if not (i == 'Position'):
                time_series_func = pynwb.TimeSeries
            else:
                time_series_func = pynwb.behavior.SpatialSeries

            time_series_list_details = self._get_data(self.nwb_metadata['Behavior'][i]['time_series'])
            time_series_list_obj = [time_series_func(**i) for i in time_series_list_details]
            func = getattr(pynwb.behavior, i)
            self.nwbfile.processing['Behavior'].add(func(time_series=time_series_list_obj))

    def create_trials(self):
        trial_df = self._table_to_df(self.nwb_metadata['Trials'])
        super(Alyx2NWBConverter, self).create_trials_from_df(trial_df)

    def add_trial_columns(self, df):
        super(Alyx2NWBConverter, self).add_trials_columns_from_df(df)

    def add_trial(self, df):
        super(Alyx2NWBConverter, self).add_trials_from_df(df)

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

    def _get_multiple_data(self, datastring, probes):
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
        spike_clusters, spike_times = datastring.split(',')
        spike_cluster_data = self.one_object.load(self.eid, dataset_types=[spike_clusters])
        spike_times_data = self.one_object.load(self.eid, dataset_types=[spike_times])
        if not ((spike_cluster_data is None) | (spike_cluster_data is None)):# if bot hdata are found only then
            ls_merged = []
            for i in range(probes):
                df = pd.DataFrame({'sp_cluster': spike_cluster_data[i], 'sp_times': spike_times_data[i]})
                data = df.groupby(['sp_cluster'])['sp_times'].apply(np.array).reset_index(name='sp_times_group')
                if self.unit_table_length is None:
                    return data
                ls_grouped = [[None]]*self.unit_table_length[i]
                for index,sp_list in data.values:
                    ls_grouped[index] = sp_list
                ls_merged.extend(ls_grouped)
            return ls_merged

    def _load(self, dataset_to_load, dataset_key, probes):
        def _load_return(loaded_dataset_):
            if loaded_dataset_[0] is None:  # dataset not found in the database
                return None
            if self.unit_table_length is None and 'cluster' in dataset_to_load:  # capture total number of clusters for each probe, used in spikes.times
                self.unit_table_length = [loaded_dataset_[i].shape[0] for i in range(probes)]
            if self.electrode_table_length is None and 'channel' in dataset_to_load:  # capture total number of clusters for each probe, used in spikes.times
                self.electrode_table_length = [loaded_dataset_[i].shape[0] for i in range(probes)]
            if isinstance(loaded_dataset_[0],pd.DataFrame):  # assuming all columns exist as colnames for the table in the json file:
                loaded_dataset_ = [loaded_dataset_[i][dataset_key].to_numpy() for i in range(probes)]
            if 'spikes' in dataset_to_load:#in case of spikes.<attr> datatype
                return loaded_dataset_# when spikes.data, dont combine
            out_data = np.concatenate(loaded_dataset_)
            return out_data
        
        if dataset_to_load not in self._loaded_datasets.keys():
            if len(dataset_to_load.split(',')) == 1:
                loaded_dataset = self.one_object.load(self.eid, dataset_types=[dataset_to_load])[0:probes]
                self._loaded_datasets.update({dataset_to_load: loaded_dataset})
                return _load_return(loaded_dataset)
            else:# special case  when multiple datasets are involved
                loaded_dataset = self._get_multiple_data(dataset_to_load, probes)
                self._loaded_datasets.update({dataset_to_load:loaded_dataset})
                return loaded_dataset
        else:
            loaded_dataset = self._loaded_datasets[dataset_to_load]
            if len(dataset_to_load.split(',')) == 1:
                return _load_return(loaded_dataset)
            else:
                return loaded_dataset

    def _get_data(self, sub_metadata, probes=1):
        """
        :param sub_metadata: metadata dict containing a data field with a dataset type to retrieve data from(npy, tsv etc)
        :return: out_dict: dictionary with actual data loaded in the data field
        """
        include_idx = []
        out_dict_trim = []
        if isinstance(sub_metadata, list):
            out_dict = deepcopy(sub_metadata)
            print('a')
        elif isinstance(sub_metadata,dict):
            out_dict = deepcopy(list(sub_metadata))
        else:
            print('out')
            return []
        for i, j in enumerate(out_dict):
            if out_dict[i].get('timestamps'):
                out_dict[i]['timestamps'] = self._load(j['timestamps'],j['name'], probes)
            if j['name'] == 'id':# valid in case of units table.
                out_dict[i]['data'] = self._load(j['data'], 'cluster_id', probes)
            else:
                out_dict[i]['data'] = self._load(j['data'], j['name'], probes)
            if out_dict[i]['data'] is not None:
                include_idx.extend([i])
        out_dict_trim.extend([out_dict[j] for j in include_idx])
        return out_dict_trim

    def write_nwb(self):
        super(Alyx2NWBConverter, self).save(self.saveloc)

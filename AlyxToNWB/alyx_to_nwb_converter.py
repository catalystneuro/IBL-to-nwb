import json
import os
import warnings
from copy import deepcopy
from datetime import datetime

import numpy as np
import pandas as pd
import pynwb
import pynwb.behavior
import pynwb.ecephys
from hdmf.backends.hdf5.h5_utils import H5DataIO
from hdmf.common.table import DynamicTable
from hdmf.data_utils import DataChunkIterator
from lazy_ops import DatasetView
from ndx_ibl_metadata import IblSessionData, IblProbes, IblSubject
from ndx_spectrum import Spectrum
from nwb_conversion_tools import NWBConverter
from oneibl.one import ONE
from pynwb import TimeSeries
from tqdm import tqdm

from .alyx_to_nwb_metadata import Alyx2NWBMetadata


def iter_datasetvieww(datasetview_obj):
    """
    Generator to return a row of the array each time it is called.
    This will be wrapped with a DataChunkIterator class.

    Parameters
    ----------
    datasetview_obj: DatasetView
        2-D array to iteratively write to nwb.
    """

    for i in range(datasetview_obj.shape[0]//700):
        curr_data = np.squeeze(datasetview_obj[i:i+1])
        yield curr_data


class Alyx2NWBConverter(NWBConverter):

    def __init__(self, nwbfile=None, saveloc=None,
                 nwb_metadata_file=None,
                 metadata_obj: Alyx2NWBMetadata = None,
                 one_object=None, save_raw=False, save_camera_raw=False):
        """

        Parameters
        ----------
        nwbfile
        saveloc
        nwb_metadata_file
        metadata_obj
        one_object
        save_raw
        save_camera_raw
        """

        if nwb_metadata_file is not None:
            if isinstance(nwb_metadata_file, dict):
                self.nwb_metadata = nwb_metadata_file
            elif isinstance(nwb_metadata_file, str):
                with open(nwb_metadata_file, 'r') as f:
                    self.nwb_metadata = json.load(f)
            # jsonschema.validate(nwb_metadata_file, metafile)
        elif metadata_obj is not None:
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
        if one_object is not None:
            self.one_object = one_object
        elif metadata_obj is not None:
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
        if not isinstance(self.nwb_metadata['NWBFile']['session_start_time'],datetime):
            self.nwb_metadata['NWBFile']['session_start_time'] = \
                datetime.strptime(self.nwb_metadata['NWBFile']['session_start_time'],'%Y-%m-%d %X')
            self.nwb_metadata['IBLSubject']['date_of_birth'] = \
                datetime.strptime(self.nwb_metadata['IBLSubject']['date_of_birth'], '%Y-%m-%d %X')
        super(Alyx2NWBConverter, self).__init__(self.nwb_metadata, nwbfile)
        self._loaded_datasets = dict()
        self.no_probes = len(self.nwb_metadata['Probes'])
        self.electrode_table_exist = False
        self.save_raw = save_raw
        self.save_camera_raw = save_camera_raw
        self._data_attrs_dump = dict()

    def create_stimulus(self):
        stimulus_list = self._get_data(self.nwb_metadata['Stimulus'].get('time_series'))
        for i in stimulus_list:
            self.nwbfile.add_stimulus(pynwb.TimeSeries(**i))  # TODO: convert timeseries data to starting_time and rate

    def create_units(self):
        if not self.electrode_table_exist:
            self.create_electrode_table_ecephys()
        unit_table_list = self._get_data(self.nwb_metadata['Units'], probes=self.no_probes)
        # no required arguments for units table. Below are default columns in the table.
        default_args = ['id', 'waveform_mean', 'electrodes', 'electrode_group', 'spike_times', 'obs_intervals']
        default_ids = self._get_default_column_ids(default_args, [i['name'] for i in unit_table_list])
        if len(default_ids)!=len(default_args):
            warnings.warn(f'could not find all of {default_args} clusters')
            # return None
        non_default_ids = list(set(range(len(unit_table_list))).difference(set(default_ids)))
        default_dict = dict()
        [default_dict.update({unit_table_list[i]['name']:unit_table_list[i]['data']}) for i in default_ids]
        for j in range(len(unit_table_list[0]['data'])):
            add_dict = dict()
            for i in default_dict.keys():
                if i == 'electrodes':
                    add_dict.update({i: [default_dict[i][j]]})
                if i == 'spike_times':
                    add_dict.update({i: default_dict[i][j]})
                elif i == 'obs_intervals':  # common across all clusters
                    add_dict.update({i: default_dict[i]})
                elif i == 'electrode_group':
                    add_dict.update({i: self.nwbfile.electrode_groups[self.nwb_metadata['Probes'][default_dict[i][
                        j]]['name']]})
                elif i == 'id':
                    if j >= self._data_attrs_dump['unit_table_length'][0]:
                        add_dict.update({i: default_dict[i][j]+self._data_attrs_dump['unit_table_length'][0]})
                    else:
                        add_dict.update({i: default_dict[i][j]})
                elif i == 'waveform_mean':
                    add_dict.update({i: np.mean(default_dict[i][j], axis=1)})  # finding the mean along all the
                    # channels of the sluter
            self.nwbfile.add_unit(**add_dict)

        for i in non_default_ids:
            if isinstance(unit_table_list[i]['data'], object):
                unit_table_list[i]['data'] = unit_table_list[i]['data'].tolist()  # convert string numpy
            self.nwbfile.add_unit_column(name=unit_table_list[i]['name'],
                                         description=unit_table_list[i]['description'],
                                         data=unit_table_list[i]['data'])

    def create_electrode_table_ecephys(self):
        if self.electrode_table_exist:
            pass
        electrode_table_list = self._get_data(self.nwb_metadata['ElectrodeTable'], probes=self.no_probes)
        # electrode table has required arguments:
        required_args = ['group', 'x', 'y']
        default_ids = self._get_default_column_ids(required_args, [i['name'] for i in electrode_table_list])
        non_default_ids = list(set(range(len(electrode_table_list))).difference(set(default_ids)))
        default_dict = dict()
        [default_dict.update({electrode_table_list[i]['name']: electrode_table_list[i]['data']}) for i in default_ids]
        if 'group' in default_dict.keys():
            group_labels = default_dict['group']
        else:  # else fill with probe zero data.
            group_labels = np.concatenate([np.ones(self._data_attrs_dump['electrode_table_length'][i],dtype=int)*i for i in range(self.no_probes)])
        for j in range(len(electrode_table_list[0]['data'])):
            if 'x' in default_dict.keys():
                x = default_dict['x'][j][0]
                y = default_dict['y'][j][1]
            else:
                x = float('NaN')
                y = float('NaN')
            group_data = self.nwbfile.electrode_groups[self.nwb_metadata['Probes'][group_labels[j]]['name']]
            self.nwbfile.add_electrode(x=x,
                                       y=y,
                                       z=float('NaN'),
                                       imp=float('NaN'),
                                       location='unknown',
                                       group=group_data,
                                       filtering='unknown'
                                       )
        for i in non_default_ids:
            self.nwbfile.add_electrode_column(name=electrode_table_list[i]['name'],
                                              description=electrode_table_list[i]['description'],
                                              data=electrode_table_list[i]['data'])
        # create probes specific DynamicTableRegion:
        self.probe_dt_region = [self.nwbfile.create_electrode_table_region(
            name=probe['name'],
            region=list(range(self._data_attrs_dump['electrode_table_length'][i])),
            description=probe['name'])
            for i, probe in enumerate(self.nwb_metadata['Probes'])]

        self.probe_dt_region_all = self.nwbfile.create_electrode_table_region(
            name='AllProbes',
            region=list(range(sum(self._data_attrs_dump['electrode_table_length']))),
            description='AllProbes')
        self.electrode_table_exist = True

    def create_timeseries_ecephys(self):
        if not self.electrode_table_exist:
            self.create_electrode_table_ecephys()
        if 'ecephys' not in self.nwbfile.processing:
            mod = self.nwbfile.create_processing_module('ecephys', 'Processed electrophysiology data')
        else:
            mod = self.nwbfile.get_processing_module('ecephys')
        for func, argmts in self.nwb_metadata['Ecephys']['Ecephys'].items():
            data_retrieve = self._get_data(argmts, probes=self.no_probes)
            for no, i in enumerate(data_retrieve):
                if 'ElectricalSeries' in func:
                    timestamps_names = self._data_attrs_dump['_iblqc_ephysTimeRms.timestamps']
                    data_names = self._data_attrs_dump['_iblqc_ephysTimeRms.rms']
                    for data_idx, data in enumerate(i['data']):
                        mod.add(TimeSeries(name=data_names[data_idx],
                                           description=i['description'],
                                           timestamps=i['timestamps'][timestamps_names.index(data_names[data_idx])],
                                           data=data))
                elif 'Spectrum' in func:
                    if argmts[no]['data'] in '_iblqc_ephysSpectralDensity.power':
                        freqs_names = self._data_attrs_dump['_iblqc_ephysSpectralDensity.freqs']
                        data_names = self._data_attrs_dump['_iblqc_ephysSpectralDensity.power']
                        for data_idx, data in enumerate(i['data']):
                            mod.add(Spectrum(name=data_names[data_idx],
                                             frequencies=i['frequencies'][freqs_names.index(data_names[data_idx])],
                                             power=data))
                elif 'SpikeEventSeries' in func:
                    i.update(dict(electrodes=self.probe_dt_region_all))
                    mod.add(pynwb.ecephys.SpikeEventSeries(**i))

    def create_behavior(self):
        behavior_mod = super(Alyx2NWBConverter, self).check_module('behavior')
        for key in self.nwb_metadata['Behavior']:
            if key == 'Position':
                position_cont = pynwb.behavior.Position()
                time_series_list_details = self._get_data(self.nwb_metadata['Behavior'][key]['spatial_series'])
                if not time_series_list_details:
                    break
                # rate_list = [150.0,60.0,60.0] # based on the google doc for _iblrig_body/left/rightCamera.raw,
                dataname_list = self._data_attrs_dump['camera.dlc']
                data_list = time_series_list_details[0]['data']
                timestamps_list = time_series_list_details[0]['timestamps']
                for dataname, data, timestamps in zip(dataname_list, data_list, timestamps_list):
                    colnames = data.columns
                    data_np = data.to_numpy()
                    x_column_ids = [n for n, k in enumerate(colnames) if 'x' in k]
                    for x_column_id in x_column_ids:
                        data_loop = data_np[:, x_column_id:x_column_id+2]
                        position_cont.create_spatial_series(name=dataname + colnames[x_column_id][:-2], data=data_loop,
                                                            reference_frame='none', timestamps=timestamps, conversion=1e3)
                behavior_mod.add(position_cont)
            elif key == 'BehavioralEpochs':
                time_series_func = pynwb.misc.IntervalSeries
                time_series_list_details = self._get_data(self.nwb_metadata['Behavior'][i]['interval_series'])
                for k in time_series_list_details:
                    k['timestamps'] = k['timestamps'].flatten()
                    k['data'] = np.vstack((k['data'], -1 * np.ones(k['data'].shape, dtype=float))).flatten()
                time_series_list_obj = [time_series_func(**i) for i in time_series_list_details]
                func = getattr(pynwb.behavior, key)
                behavior_mod.add(func(interval_series=time_series_list_obj))
            else:
                time_series_func = pynwb.TimeSeries
                time_series_list_details = self._get_data(self.nwb_metadata['Behavior'][key]['time_series'])
                time_series_list_obj = [time_series_func(**i) for i in time_series_list_details]
                func = getattr(pynwb.behavior, key)
                behavior_mod.add(func(time_series=time_series_list_obj))

    def create_acquisition(self):
        """
        Acquisition data like audiospectrogram(raw beh data), nidq(raw ephys data), raw camera data.
        These are independent of probe type.
        """
        if not self.electrode_table_exist:
            self.create_electrode_table_ecephys()
        for func, argmts in self.nwb_metadata['Acquisition'].items():
            data_retrieve = self._get_data(argmts, probes=self.no_probes)
            nwbfunc = eval(func)
            for i in data_retrieve:
                if func == 'ImageSeries':
                    for types, times in zip(i['data'], i['timestamps']):
                        customargs = dict(name=os.path.basename(str(types)),
                                          external_file=[str(types)],
                                          format='external',
                                          timestamps=times)
                        self.nwbfile.add_acquisition(nwbfunc(**customargs))
                elif func == 'DecompositionSeries':
                    i['bands'] = np.squeeze(i['bands'])
                    freqs = DynamicTable('frequencies', 'spectogram frequencies', id=np.arange(i['bands'].shape[0]))
                    freqs.add_column('bands', 'frequency value', data=i['bands'])
                    i.update(dict(bands=freqs))
                    temp = i['data'][:, :, np.newaxis]
                    i['data'] = np.moveaxis(temp, [0, 1, 2], [0, 2, 1])
                    ts = i.pop('timestamps')
                    starting_time = ts[0][0] if isinstance(ts[0], np.ndarray) else ts[0]
                    i.update(dict(starting_time=np.float64(starting_time),
                                  rate=1/np.mean(np.diff(ts.squeeze())),
                                  unit='sec'))
                    self.nwbfile.add_acquisition(nwbfunc(**i))
                else:
                    if i['name'] in ('raw.lf', 'raw.ap'):
                        for j in range(self.no_probes):
                            self.nwbfile.add_acquisition(
                                TimeSeries(
                                    name=i['name'] + '_' + self.nwb_metadata['Probes'][j]['name'],
                                    starting_time=i['timestamps'][j][0, 1],
                                    rate=i['data'][j].fs,
                                    data=H5DataIO(DataChunkIterator(iter_datasetvieww(i['data'][j])),
                                                  compression=True)))
                    elif i['name'] in ['raw.nidq']:
                        self.nwbfile.add_acquisition(nwbfunc(**i))

    def create_probes(self):
        """
        Fills in all the probes metadata into the custom NeuroPixels extension.
        """
        for i in self.nwb_metadata['Probes']:
            self.nwbfile.add_device(IblProbes(**i))

    def create_iblsubject(self):
        """
        Populates the custom subject extension for IBL mice daata
        """
        self.nwbfile.subject = IblSubject(**self.nwb_metadata['IBLSubject'])

    def create_lab_meta_data(self):
        """
        Populates the custom lab_meta_data extension for IBL sessions data
        """
        self.nwbfile.add_lab_meta_data(IblSessionData(**self.nwb_metadata['IBLSessionsData']))

    def create_trials(self):
        trial_df = self._table_to_df(self.nwb_metadata['Trials'])
        for trial_dict in self.nwb_metadata['Trials']:
            if trial_dict['name'] not in ('start_time', 'stop_time'):
                self.nwbfile.add_trial_column(
                    name=trial_dict['name'],
                    description=trial_dict['description'])
        for index, row in trial_df.iterrows():
            self.nwbfile.add_trial(**dict(row))

    def _get_default_column_ids(self, default_namelist, namelist):
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
            if i['name'] == 'start_time':
                data_dict.update(start_time=self.one_object.load(self.eid, dataset_types=[i['data']])[0][:, 0])
            elif i['name'] == 'stop_time':
                data_dict.update(stop_time=self.one_object.load(self.eid, dataset_types=[i['data']])[0][:, 1])
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
            comma separated dataset names ex: "spike.times,spikes.clusters"
        probes: int
            number of probes for the eid (self.no_probes)
        Returns
        -------
        ls_merged: [list, None]
            list of length number of probes. Each element is a list > each element is an array of cluster's spike times
        """
        spike_clusters, spike_times = datastring.split(',')
        if spike_clusters not in self._loaded_datasets.keys():
            spike_cluster_data = self.one_object.load(self.eid, dataset_types=[spike_clusters])
            self._loaded_datasets.update({spike_clusters: spike_cluster_data})
        else:
            spike_cluster_data = self._loaded_datasets[spike_clusters]
        if spike_times not in self._loaded_datasets.keys():
            spike_times_data = self.one_object.load(self.eid, dataset_types=[spike_times])
            self._loaded_datasets.update({spike_times: spike_times_data})
        else:
            spike_times_data = self._loaded_datasets[spike_times]
        if not (spike_cluster_data is None) | (spike_cluster_data is None):  # if bot hdata are found only then
            ls_merged = []
            for i in range(probes):
                df = pd.DataFrame({'sp_cluster': spike_cluster_data[i], 'sp_times': spike_times_data[i]})
                data = df.groupby(['sp_cluster'])['sp_times'].apply(np.array).reset_index(name='sp_times_group')
                if not self._data_attrs_dump.get('unit_table_length'):  # if unit table length is not known,
                    # ignore spike times
                    return
                ls_grouped = [[np.nan]]*self._data_attrs_dump['unit_table_length'][i]  # default spiking time for
                # clusters with no time
                for index, sp_list in data.values:
                    ls_grouped[index] = sp_list
                ls_merged.extend(ls_grouped)
            return ls_merged

    def _load(self, dataset_to_load, dataset_key, probes):
        def _load_as_array(loaded_dataset_):
            """
            Takes variable data formats: .csv, .npy, .bin, .meta, .json and converts them to ndarray.
            Parameters
            ----------
            loaded_dataset_: [SessionDataInfo]
            Returns
            -------
            out_data: [ndarray, list]
            """
            if len(loaded_dataset_.data) == 0 or loaded_dataset_.data[0] is None:  # dataset not found in the database
                return None
            datatype = [i.suffix for i in loaded_dataset_.local_path]
            dataloc = [i for i in loaded_dataset_.local_path]

            if datatype[-1] in ['.csv', '.npy']:  # csv is for clusters metrics
                # if a windows path is returned despite a npy file:
                path_ids = [j for j, i in enumerate(loaded_dataset_.data) if 'WindowsPath' in [type(i)]]
                if path_ids:
                    temp = [np.load(str(loaded_dataset_.data[pt])) for pt in path_ids]
                    loaded_dataset_ = temp
                else:
                    loaded_dataset_ = loaded_dataset_.data

                if dataset_to_load.split('.')[0] in ['_iblqc_ephysSpectralDensity', '_iblqc_ephysTimeRms', 'ephysData']:
                    self._data_attrs_dump[dataset_to_load] = [i.name.split('.')[0] + '_' + i.parent.name for i in dataloc]
                    return loaded_dataset_
                if dataset_to_load.split('.')[0] in ['camera']:  # TODO: unexpected: camera.dlc is not 3d but a list
                    # correcting order of json vs npy files and names loop:
                    datanames = [i.name for i in dataloc]
                    func = lambda x: (x.split('.')[-1], x.split('.')[0])  # json>npy, and sort the names also
                    datanames_sorted = sorted(datanames, key=func)
                    if not self._data_attrs_dump.get(dataset_to_load):
                        self._data_attrs_dump[dataset_to_load] = [i.split('.')[0] for i in datanames_sorted[:int(len(datanames_sorted))]]
                    loaded_dataset_sorted = [loaded_dataset_[datanames.index(i)] for i in datanames_sorted]
                    if 'time' in dataset_to_load.split('.')[-1]:
                        return loaded_dataset_sorted
                    df_out = []
                    filetype_change_id = int(len(loaded_dataset_sorted)/2)
                    for no, fields in enumerate(loaded_dataset_sorted[:filetype_change_id]):
                        df = pd.DataFrame(data=loaded_dataset_sorted[no+3], columns=loaded_dataset_sorted[no][
                            'columns'])
                        df_out.append(df)
                    return df_out
                if 'audioSpectrogram.times' in dataset_to_load:  # TODO: unexpected: this dataset is a list in come
                    # cases
                    return loaded_dataset_[0] if isinstance(loaded_dataset_, list) else loaded_dataset_
                if not self._data_attrs_dump.get('unit_table_length') and 'cluster' in dataset_to_load:  # capture total number of clusters for each probe, used in spikes.times
                    self._data_attrs_dump['unit_table_length'] = [loaded_dataset_[i].shape[0] for i in range(probes)]
                if not self._data_attrs_dump.get('electrode_table_length') and 'channel' in dataset_to_load:  # capture total number of clusters for each probe, used in spikes.times
                    self._data_attrs_dump['electrode_table_length'] = [loaded_dataset_[i].shape[0] for i in range(probes)]
                if isinstance(loaded_dataset_[0], pd.DataFrame):  # file is loaded as dataframe when of type .csv
                    if dataset_to_load in loaded_dataset_[0].columns.values:
                        loaded_dataset_ = [loaded_dataset_[i][dataset_key].to_numpy() for i in range(probes)]
                    else:
                        return None
                return np.concatenate(loaded_dataset_)

            elif datatype[0] in ['.cbin'] and self.save_raw:
                from ibllib.io import spikeglx
                for j, i in enumerate(loaded_dataset_.local_path):
                    try:
                        loaded_dataset_.data[j] = spikeglx.Reader(i)
                    except:
                        return
                return loaded_dataset_.data
            elif datatype[0] == '.mp4' and self.save_camera_raw:
                return [str(i) for i in loaded_dataset_.data]
            elif datatype[0] == '.ssv' and self.save_camera_raw:  # when camera timestamps
                print('converting camera timestamps..')
                if isinstance(self.nwb_metadata['NWBFile']['session_start_time'], datetime):
                    dt_start = self.nwb_metadata['NWBFile']['session_start_time']
                else:
                    dt_start = datetime.strptime(self.nwb_metadata['NWBFile']['session_start_time'], '%Y-%m-%d %X')
                dt_func = lambda x: ((datetime.strptime('-'.join(x.split('-')[:-1])[:-1], '%Y-%m-%dT%H:%M:%S.%f')) -
                                     dt_start).total_seconds()
                dt_list = [dt.iloc[:, 0].apply(dt_func).to_numpy() for dt in loaded_dataset_.data]  # find difference
                # in seconds from session start
                print('done')
                return dt_list
            elif datatype[0] == '.pqt':
                datanames = [i.name for i in dataloc]
                func = lambda x: (x.split('.')[-1], x.split('.')[0])  # json>npy, and sort the names also
                datanames_sorted = sorted(datanames, key=func)
                if not self._data_attrs_dump.get(dataset_to_load):
                    self._data_attrs_dump[dataset_to_load] = [i.split('.')[0] for i in datanames_sorted]
                return [loaded_dataset_.data[datanames.index(i)] for i in datanames_sorted]
            else:
                return

        if not type(dataset_to_load) is str:  # prevents errors when loading metafile json
            return
        if dataset_to_load.split('.')[0] == 'ephysData' and not self.save_raw:
            return
        if dataset_to_load.split('.')[0] == '_iblrig_Camera' and not self.save_camera_raw:
            return
        if dataset_to_load not in self._loaded_datasets.keys():
            if len(dataset_to_load.split(',')) == 1:
                if 'ephysData.raw' in dataset_to_load and not 'ephysData.raw.meta' in self._loaded_datasets:
                    meta = self.one_object.load(self.eid, dataset_types=['ephysData.raw.meta'])
                    ch = self.one_object.load(self.eid, dataset_types=['ephysData.raw.ch'])
                    self._loaded_datasets.update({'ephysData.raw.meta': meta, 'ephysData.raw.ch': ch})
                loaded_dataset = self.one_object.load(self.eid, dataset_types=[dataset_to_load], dclass_output=True)
                self._loaded_datasets.update({dataset_to_load: loaded_dataset})
                return _load_as_array(loaded_dataset)
            else:  # special case  when multiple datasets are involved
                loaded_dataset = self._get_multiple_data(dataset_to_load, probes)
                if loaded_dataset is not None:
                    self._loaded_datasets.update({dataset_to_load:loaded_dataset})
                return loaded_dataset
        else:
            loaded_dataset = self._loaded_datasets[dataset_to_load]
            if len(dataset_to_load.split(',')) == 1:
                return _load_as_array(loaded_dataset)
            else:
                return loaded_dataset

    def _get_data(self, sub_metadata, probes=1):
        """
        :param sub_metadata: metadata dict containing a data field with a dataset type to retrieve data from(npy, tsv etc)
        :return: out_dict: dictionary with actual data loaded in the data field
        """
        include_idx = []
        out_dict_trim = []
        alt_datatypes = ['bands', 'power', 'frequencies', 'timestamps']
        if isinstance(sub_metadata, list):
            out_dict = deepcopy(sub_metadata)
        elif isinstance(sub_metadata, dict):
            out_dict = deepcopy(list(sub_metadata))
        else:
            return []
        for i, j in enumerate(out_dict):
            for alt_names in alt_datatypes:
                if j.get(alt_names):  # in case of Decomposotion series, Spectrum
                    j[alt_names] = self._load(j[alt_names], j['name'], probes)
            if j['name'] == 'id':  # valid in case of units table.
                j['data'] = self._load(j['data'], 'cluster_id', probes)
            else:
                out_dict[i]['data'] = self._load(j['data'], j['name'], probes)
            if out_dict[i]['data'] is not None:
                include_idx.extend([i])
        out_dict_trim.extend([out_dict[j0] for j0 in include_idx])
        return out_dict_trim

    def run_conversion(self):
        execute_list = [self.create_stimulus,
                        self.create_trials,
                        self.create_electrode_table_ecephys,
                        self.create_timeseries_ecephys,
                        self.create_units,
                        self.create_behavior,
                        self.create_probes,
                        self.create_iblsubject,
                        self.create_lab_meta_data,
                        self.create_acquisition]
        t = tqdm(execute_list)
        for i in t:
            t.set_postfix(current=f'creating nwb ' + i.__name__.split('_')[-1])
            i()
        print('done converting')

    def write_nwb(self):
        super(Alyx2NWBConverter, self).save(self.saveloc)

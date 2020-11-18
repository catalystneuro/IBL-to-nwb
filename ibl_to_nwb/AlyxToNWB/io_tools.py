from datetime import datetime
from pathlib import PurePath

import numpy as np
import pandas as pd
from tzlocal import get_localzone
from ibllib.io import spikeglx
from oneibl.one import OneAbstract, SessionDataInfo


def _iter_datasetview(reader: spikeglx.Reader, channel_ids=None):
    """
    Generator to return a row of the array each time it is called.
    This will be wrapped with a DataChunkIterator class.

    Parameters
    ----------
    reader: spikeglx.Reader
        to retrieve raw int16 traces using ._raw attribute
    channel_ids: np.array of ints, optional
        channel numbers to store
    """
    for i in range(reader.shape[0]):
        yield reader._raw[i][channel_ids].squeeze()
    return


def _get_default_column_ids(default_namelist, namelist):
    out_idx = []
    for j, i in enumerate(namelist):
        if i in default_namelist:
            out_idx.extend([j])
    return out_idx


class _OneData:

    def __init__(self, one_object: OneAbstract, eid: str, no_probes: int, nwb_metadata: dict, save_raw=False, save_camera_raw=False):
        self.one_object = one_object
        self.eid = eid
        self.no_probes = no_probes
        self.save_raw = save_raw
        self.save_camera_raw = save_camera_raw
        self.loaded_datasets = dict()
        self.data_attrs_dump = dict()
        self.nwb_metadata = nwb_metadata

    def download_dataset(self, dataset_to_load: str, dataset_key: str):
        if not isinstance(dataset_to_load, str):  # prevents errors when loading metafile json
            return
        if dataset_to_load.split('.')[0] == 'ephysData' and not self.save_raw:
            return
        if 'Camera.raw' in dataset_to_load:
            sess_info=self.one_object.alyx.rest('sessions/' + self.eid, 'list')
            camraw = [i for i in sess_info['data_dataset_session_related'] if 'Camera.raw' in i['name']]
            if not self.save_camera_raw and len(camraw)==1:
                self.loaded_datasets.update({dataset_to_load: camraw[0]['data_url']})
                return [camraw[0]['data_url']]
            else:
                return
        if dataset_to_load not in self.loaded_datasets:
            if len(dataset_to_load.split(',')) == 1:
                if 'ephysData.raw' in dataset_to_load and not 'ephysData.raw.meta' in self.loaded_datasets:
                    meta = self.one_object.load(self.eid, dataset_types=['ephysData.raw.meta'])
                    ch = self.one_object.load(self.eid, dataset_types=['ephysData.raw.ch'])
                    self.loaded_datasets.update({'ephysData.raw.meta': meta, 'ephysData.raw.ch': ch})
                loaded_dataset = self.one_object.load(self.eid, dataset_types=[dataset_to_load], dclass_output=True)
                self.loaded_datasets.update({dataset_to_load: loaded_dataset})
                return self._load_as_array(dataset_to_load, dataset_key, loaded_dataset)
            else:  # special case  when multiple datasets are involved
                loaded_dataset = self._get_multiple_data(dataset_to_load)
                if loaded_dataset is not None:
                    self.loaded_datasets.update({dataset_to_load: loaded_dataset})
                return loaded_dataset
        else:
            loaded_dataset = self.loaded_datasets[dataset_to_load]
            if len(dataset_to_load.split(',')) == 1:
                return self._load_as_array(dataset_to_load, dataset_key, loaded_dataset)
            else:
                return loaded_dataset

    def _get_multiple_data(self, datastring):
        """
        This method is current specific to units table to retrieve spike times for a given cluster
        Parameters
        ----------
        datastring: str
            comma separated dataset names ex: "spike.times,spikes.clusters"
        Returns
        -------
        ls_merged: [list, None]
            list of length number of probes. Each element is a list > each element is an array of cluster's spike times
        """
        spike_clusters, spike_times = datastring.split(',')
        if spike_clusters not in self.loaded_datasets:
            spike_cluster_data = self.one_object.load(self.eid, dataset_types=[spike_clusters])
            self.loaded_datasets.update({spike_clusters: spike_cluster_data})
        else:
            spike_cluster_data = self.loaded_datasets[spike_clusters]
        if spike_times not in self.loaded_datasets:
            spike_times_data = self.one_object.load(self.eid, dataset_types=[spike_times])
            self.loaded_datasets.update({spike_times: spike_times_data})
        else:
            spike_times_data = self.loaded_datasets[spike_times]
        if not ((spike_cluster_data is None) | (spike_cluster_data is None)):  # if bot hdata are found only then
            ls_merged = []
            if not self.data_attrs_dump.get(
                    'unit_table_length'):  # if unit table length is not known, ignore spike times
                return None
            if np.abs(np.max(spike_cluster_data[0]) - self.data_attrs_dump['unit_table_length'][0]) > 20:
                i_loop = np.arange(self.no_probes - 1, -1, -1)
            else:
                i_loop = np.arange(self.no_probes)
            for j, i in enumerate(i_loop):
                df = pd.DataFrame({'sp_cluster': spike_cluster_data[i], 'sp_times': spike_times_data[i]})
                data = df.groupby(['sp_cluster'])['sp_times'].apply(np.array).reset_index(name='sp_times_group')
                ls_grouped = [[np.nan]]*self.data_attrs_dump['unit_table_length'][
                    j]  # default spiking time for clusters with no time
                for index, sp_list in data.values:
                    ls_grouped[index] = sp_list
                ls_merged.extend(ls_grouped)
            return ls_merged

    def _load_as_array(self, dataset_to_load: str, dataset_key: str, loaded_dataset_: SessionDataInfo):
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
            path_ids = [j for j, i in enumerate(loaded_dataset_.data) if isinstance(i, PurePath)]
            if path_ids:
                temp = [np.load(str(loaded_dataset_.data[pt])) for pt in path_ids]
                loaded_dataset_ = temp
            else:
                loaded_dataset_ = loaded_dataset_.data

            if dataset_to_load.split('.')[0] in ['_iblqc_ephysSpectralDensity', '_iblqc_ephysTimeRms', 'ephysData']:
                self.data_attrs_dump[dataset_to_load] = [i.name.split('.')[0] + '_' + i.parent.name for i in
                                                         dataloc]
                return loaded_dataset_
            if dataset_to_load.split('.')[0] in ['camera']:
                # correcting order of json vs npy files and names loop:
                datanames = [i.name for i in dataloc]
                func = lambda x: (x.split('.')[-1], x.split('.')[0])  # json>npy, and sort the names also
                datanames_sorted = sorted(datanames, key=func)
                if not self.data_attrs_dump.get(dataset_to_load):
                    self.data_attrs_dump[dataset_to_load] = [i.split('.')[0] for i in
                                                             datanames_sorted[:int(len(datanames_sorted))]]
                loaded_dataset_sorted = [loaded_dataset_[datanames.index(i)] for i in datanames_sorted]
                if 'time' in dataset_to_load.split('.')[-1]:
                    return loaded_dataset_sorted
                df_out = []
                filetype_change_id = int(len(loaded_dataset_sorted)/2)
                for no, fields in enumerate(loaded_dataset_sorted[:filetype_change_id]):
                    df = pd.DataFrame(data=loaded_dataset_sorted[no + 3],
                                      columns=loaded_dataset_sorted[no]['columns'])
                    df_out.append(df)
                return df_out
            if 'audioSpectrogram.times' in dataset_to_load:
                return loaded_dataset_[0] if isinstance(loaded_dataset_, list) else loaded_dataset_
            if not self.data_attrs_dump.get(
                    'unit_table_length') and 'cluster' in dataset_to_load:  # capture total number of clusters for each probe, used in spikes.times
                self.data_attrs_dump['unit_table_length'] = [loaded_dataset_[i].shape[0] for i in
                                                             range(self.no_probes)]
            if not self.data_attrs_dump.get(
                    'electrode_table_length') and 'channel' in dataset_to_load:  # capture total number of clusters for each probe, used in spikes.times
                self.data_attrs_dump['electrode_table_length'] = [loaded_dataset_[i].shape[0] for i in
                                                                  range(self.no_probes)]
            if isinstance(loaded_dataset_[0], pd.DataFrame):  # file is loaded as dataframe when of type .csv
                if dataset_key in loaded_dataset_[0].columns.values:
                    loaded_dataset_ = [loaded_dataset_[i][dataset_key].to_numpy() for i in range(self.no_probes)]
                else:
                    return None
            return np.concatenate(loaded_dataset_)

        elif datatype[0] in ['.cbin'] and self.save_raw:
            from ibllib.io import spikeglx
            for j, i in enumerate(loaded_dataset_.local_path):
                try:
                    loaded_dataset_.data[j] = spikeglx.Reader(i)
                except:
                    return None
            return loaded_dataset_.data
        elif datatype[0] in ['.mp4'] and self.save_camera_raw:
            return [str(i) for i in loaded_dataset_.data]
        elif datatype[0] in ['.ssv']:  # when camera timestamps
            if loaded_dataset_.data[0].shape[0]==0:
                return
            print('converting camera timestamps..')
            if isinstance(self.nwb_metadata['NWBFile']['session_start_time'], datetime):
                dt_start = self.nwb_metadata['NWBFile']['session_start_time']
            else:
                dt_start = datetime.strptime(self.nwb_metadata['NWBFile']['session_start_time'],
                                             '%Y-%m-%d %X').replace(tzinfo=get_localzone())
            dt_start = dt_start.replace(tzinfo=None)
            dt_func = lambda x: ((datetime.strptime(x[:26],
                                                    '%Y-%m-%dT%H:%M:%S.%f')) - dt_start).total_seconds()
            #find col with datetime obj:
            col_no = [no for no, i in enumerate(loaded_dataset_.data[0].iloc[1,:]) if isinstance(i,str)][0]
            # add columnname:
            data_dt_list = []
            for i in loaded_dataset_.data:
                col_series = pd.concat([pd.Series([i.columns[col_no]]),i.iloc[:,col_no]])
                data_dt_list.append(col_series.apply(dt_func).to_numpy())
            # dt_list = [dt.iloc[:].apply(dt_func).to_numpy() for dt in data_dt_list]  # find difference in seconds from session start
            print('done')
            return data_dt_list
        elif datatype[0] == '.pqt':
            datanames = [i.name for i in dataloc]
            func = lambda x: (x.split('.')[-1], x.split('.')[0])  # json>npy, and sort the names also
            datanames_sorted = sorted(datanames, key=func)
            if not self.data_attrs_dump.get(dataset_to_load):
                self.data_attrs_dump[dataset_to_load] = [i.split('.')[0] for i in datanames_sorted]
            return [loaded_dataset_.data[datanames.index(i)] for i in datanames_sorted]
        else:
            return None

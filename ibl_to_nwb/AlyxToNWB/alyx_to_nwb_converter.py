import json
import os
import warnings
from copy import deepcopy
from datetime import datetime
import uuid
import numpy as np
import pandas as pd
from pynwb import NWBFile, NWBHDF5IO
from pynwb.ecephys import ElectricalSeries
from pynwb.misc import DecompositionSeries
from pynwb import TimeSeries
from pynwb.image import ImageSeries
import pynwb.behavior
import pynwb.ecephys
from hdmf.backends.hdf5.h5_utils import H5DataIO
from hdmf.common.table import DynamicTable
from hdmf.data_utils import DataChunkIterator
from lazy_ops import DatasetView
from ndx_ibl_metadata import IblSessionData, IblProbes, IblSubject
from ndx_spectrum import Spectrum
from oneibl.one import ONE
from pynwb import TimeSeries
from tqdm import tqdm
from tzlocal import get_localzone

from .alyx_to_nwb_metadata import Alyx2NWBMetadata
from .io_tools import iter_datasetview, OneData, get_default_column_ids


class Alyx2NWBConverter:

    def __init__(self, saveloc=None,
                 nwb_metadata_file=None,
                 metadata_obj: Alyx2NWBMetadata = None,
                 one_object=None, save_raw=False, save_camera_raw=False,
                 complevel=4, shuffle=False):
        """
        Retrieve all Alyx session, subject metadata, raw data for eid using the one apis load method
        Map that to nwb supported datatypes and create an nwb file.
        Parameters
        ----------
        saveloc: str
            save location of nwbfile
        nwb_metadata_file: [dict, str]
            output of Alyx2NWBMetadata as a dict/json location str
        metadata_obj: Alyx2NWBMetadata
        one_object: ONE()
        save_raw: bool
            will load and save large raw files: ecephys.raw.ap/lf.cbin to nwb
        save_camera_raw: bool
            will load and save mice camera movie .mp4: _iblrig_Camera.raw
        complevel: int
            level of compression to apply to raw datasets
            (0-9)>(low,high). https://docs.h5py.org/en/latest/high/dataset.html
        shuffle: bool
            Enable shuffle I/O filter. http://docs.h5py.org/en/latest/high/dataset.html#dataset-shuffle
        """

        self.complevel = complevel
        self.shuffle = shuffle
        if nwb_metadata_file is not None:
            if isinstance(nwb_metadata_file, dict):
                self.nwb_metadata = nwb_metadata_file
            elif isinstance(nwb_metadata_file, str):
                with open(nwb_metadata_file, 'r') as f:
                    self.nwb_metadata = json.load(f)
        elif metadata_obj is not None:
            self.nwb_metadata = metadata_obj.complete_metadata
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
        if not isinstance(self.nwb_metadata['NWBFile']['session_start_time'], datetime):
            self.nwb_metadata['NWBFile']['session_start_time'] = \
                datetime.strptime(self.nwb_metadata['NWBFile']['session_start_time'], '%Y-%m-%dT%X').replace(
                    tzinfo=get_localzone())
            self.nwb_metadata['IBLSubject']['date_of_birth'] = \
                datetime.strptime(self.nwb_metadata['IBLSubject']['date_of_birth'], '%Y-%m-%dT%X').replace(
                    tzinfo=get_localzone())
        # create nwbfile:
        self.initialize_nwbfile()
        self.no_probes = len(self.nwb_metadata['Probes'])
        if self.no_probes == 0:
            warnings.warn('could not find probe information, will create trials, behavior, acquisition')
        self.electrode_table_exist = False
        self.one_data = OneData(self.one_object, self.eid, self.no_probes, self.nwb_metadata, 
                                save_raw=save_raw, save_camera_raw=save_camera_raw)

    def initialize_nwbfile(self):
        """
        Creates self.nwbfile, devices and electrode group of nwb file.
        """
        nwbfile_args = dict(identifier=str(uuid.uuid4()), )
        nwbfile_args.update(**self.nwb_metadata['NWBFile'])
        self.nwbfile = NWBFile(**nwbfile_args)
        # create devices
        [self.nwbfile.create_device(**idevice_meta) for idevice_meta in self.nwb_metadata['Ecephys']['Device']]
        if 'ElectrodeGroup' in self.nwb_metadata['Ecephys']:
            self.create_electrode_groups(self.nwb_metadata['Ecephys'])

    def create_electrode_groups(self, metadata_ecephys):
        """
        This method is called at __init__.
        Use metadata to create ElectrodeGroup object(s) in the NWBFile

        Parameters
        ----------
        metadata_ecephys : dict
            Dict with key:value pairs for defining the Ecephys group from where this
            ElectrodeGroup belongs. This should contain keys for required groups
            such as 'Device', 'ElectrodeGroup', etc.
        """
        for metadata_elec_group in metadata_ecephys['ElectrodeGroup']:
            eg_name = metadata_elec_group['name']
            # Tests if ElectrodeGroup already exists
            aux = [i.name == eg_name for i in self.nwbfile.children]
            if any(aux):
                print(eg_name + ' already exists in current NWBFile.')
            else:
                device_name = metadata_elec_group['device']
                if device_name in self.nwbfile.devices:
                    device = self.nwbfile.devices[device_name]
                else:
                    print('Device ', device_name, ' for ElectrodeGroup ', eg_name, ' does not exist.')
                    print('Make sure ', device_name, ' is defined in metadata.')

                eg_description = metadata_elec_group['description']
                eg_location = metadata_elec_group['location']
                self.nwbfile.create_electrode_group(
                    name=eg_name,
                    location=eg_location,
                    device=device,
                    description=eg_description
                )

    def check_module(self, name, description=None):
        """
        Check if processing module exists. If not, create it. Then return module

        Parameters
        ----------
        name: str
        description: str | None (optional)

        Returns
        -------
        pynwb.module

        """

        if name in self.nwbfile.processing:
            return self.nwbfile.processing[name]
        else:
            if description is None:
                description = name
            return self.nwbfile.create_processing_module(name, description)

    def create_stimulus(self):
        """
        Creates stimulus data in nwbfile
        """
        stimulus_list = self._get_data(self.nwb_metadata['Stimulus'].get('time_series'))
        for i in stimulus_list:
            self.nwbfile.add_stimulus(pynwb.TimeSeries(**i))

    def create_units(self):
        """
        Units table in nwbfile
        """
        if self.no_probes == 0:
            return
        if not self.electrode_table_exist:
            self.create_electrode_table_ecephys()
        unit_table_list = self._get_data(self.nwb_metadata['Units'])
        # no required arguments for units table. Below are default columns in the table.
        default_args = ['id', 'waveform_mean', 'electrodes', 'electrode_group', 'spike_times', 'obs_intervals']
        default_ids = get_default_column_ids(default_args, [i['name'] for i in unit_table_list])
        if len(default_ids) != len(default_args):
            warnings.warn(f'could not find all of {default_args} clusters')
            # return None
        non_default_ids = list(set(range(len(unit_table_list))).difference(set(default_ids)))
        default_dict = dict()
        [default_dict.update({unit_table_list[i]['name']: unit_table_list[i]['data']}) for i in default_ids]
        for j in range(len(unit_table_list[0]['data'])):
            add_dict = dict()
            for i in default_dict:
                if i == 'electrodes':
                    add_dict.update({i: [default_dict[i][j]]})
                if i == 'spike_times':
                    add_dict.update({i: default_dict[i][j]})
                elif i == 'obs_intervals':  # common across all clusters
                    add_dict.update({i: default_dict[i]})
                elif i == 'electrode_group':
                    add_dict.update(
                        {i: self.nwbfile.electrode_groups[self.nwb_metadata['Probes'][default_dict[i][j]]['name']]})
                elif i == 'id':
                    if j >= self.one_data.data_attrs_dump['unit_table_length'][0]:
                        add_dict.update({i: default_dict[i][j] + self.one_data.data_attrs_dump['unit_table_length'][0]})
                    else:
                        add_dict.update({i: default_dict[i][j]})
                elif i == 'waveform_mean':
                    add_dict.update({i: np.mean(default_dict[i][j],
                                                axis=1)})  # finding the mean along all the channels of the sluter
            self.nwbfile.add_unit(**add_dict)

        for i in non_default_ids:
            if isinstance(unit_table_list[i]['data'], object):
                unit_table_list[i]['data'] = unit_table_list[i]['data'].tolist()  # convert string numpy
            self.nwbfile.add_unit_column(name=unit_table_list[i]['name'],
                                         description=unit_table_list[i]['description'],
                                         data=unit_table_list[i]['data'])

    def create_electrode_table_ecephys(self):
        """
        Creates electrode table
        """
        if self.no_probes == 0:
            return
        if self.electrode_table_exist:
            pass
        electrode_table_list = self._get_data(self.nwb_metadata['ElectrodeTable'])
        # electrode table has required arguments:
        required_args = ['group', 'x', 'y']
        default_ids = get_default_column_ids(required_args, [i['name'] for i in electrode_table_list])
        non_default_ids = list(set(range(len(electrode_table_list))).difference(set(default_ids)))
        default_dict = dict()
        [default_dict.update({electrode_table_list[i]['name']: electrode_table_list[i]['data']}) for i in default_ids]
        if 'group' in default_dict:
            group_labels = default_dict['group']
        else:  # else fill with probe zero data.
            group_labels = np.concatenate(
                [np.ones(self.one_data.data_attrs_dump['electrode_table_length'][i], dtype=int)*i for i in
                 range(self.no_probes)])
        for j in range(len(electrode_table_list[0]['data'])):
            if 'x' in default_dict:
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
                                       location='None',
                                       group=group_data,
                                       filtering='none'
                                       )
        for i in non_default_ids:
            self.nwbfile.add_electrode_column(name=electrode_table_list[i]['name'],
                                              description=electrode_table_list[i]['description'],
                                              data=electrode_table_list[i]['data'])
        # create probes specific DynamicTableRegion:
        self.probe_dt_region = [self.nwbfile.create_electrode_table_region(name=i['name'],
                                                                           region=list(range(self.one_data.data_attrs_dump[
                                                                                                 'electrode_table_length'][
                                                                                                 j])),
                                                                           description=i['name'])
                                for j, i in enumerate(self.nwb_metadata['Probes'])]
        self.probe_dt_region_all = self.nwbfile.create_electrode_table_region(name='AllProbes',
                                                                              region=list(range(sum(
                                                                                  self.one_data.data_attrs_dump[
                                                                                      'electrode_table_length']))),
                                                                              description='AllProbes')
        self.electrode_table_exist = True

    def create_timeseries_ecephys(self):
        """
        create SpikeEventSeries, ElectricalSeries, Spectrum datatypes within nwbfile>processing>ecephys
        """
        if self.no_probes == 0:
            return
        if not self.electrode_table_exist:
            self.create_electrode_table_ecephys()
        if 'ecephys' not in self.nwbfile.processing:
            mod = self.nwbfile.create_processing_module('ecephys', 'Processed electrophysiology data of IBL')
        else:
            mod = self.nwbfile.get_processing_module('ecephys')
        for func, argmts in self.nwb_metadata['Ecephys']['Ecephys'].items():
            data_retrieve = self._get_data(argmts)
            for no, i in enumerate(data_retrieve):
                if 'ElectricalSeries' in func:
                    timestamps_names = self.one_data.data_attrs_dump['_iblqc_ephysTimeRms.timestamps']
                    data_names = self.one_data.data_attrs_dump['_iblqc_ephysTimeRms.rms']
                    for data_idx, data in enumerate(i['data']):
                        mod.add(TimeSeries(name=data_names[data_idx],
                                           description=i['description'],
                                           timestamps=i['timestamps'][timestamps_names.index(data_names[data_idx])],
                                           data=data))
                elif 'Spectrum' in func:
                    if argmts[no]['data'] in '_iblqc_ephysSpectralDensity.power':
                        freqs_names = self.one_data.data_attrs_dump['_iblqc_ephysSpectralDensity.freqs']
                        data_names = self.one_data.data_attrs_dump['_iblqc_ephysSpectralDensity.power']
                        for data_idx, data in enumerate(i['data']):
                            mod.add(Spectrum(name=data_names[data_idx],
                                             frequencies=i['frequencies'][freqs_names.index(data_names[data_idx])],
                                             power=data))
                elif 'SpikeEventSeries' in func:
                    i.update(dict(electrodes=self.probe_dt_region_all))
                    mod.add(pynwb.ecephys.SpikeEventSeries(**i))

    def create_behavior(self):
        """
        Create behavior processing module
        """
        self.check_module('behavior')
        for i in self.nwb_metadata['Behavior']:
            if i == 'Position':
                position_cont = pynwb.behavior.Position()
                time_series_list_details = self._get_data(self.nwb_metadata['Behavior'][i]['spatial_series'])
                if len(time_series_list_details) == 0:
                    continue
                # rate_list = [150.0,60.0,60.0] # based on the google doc for _iblrig_body/left/rightCamera.raw,
                dataname_list = self.one_data.data_attrs_dump['camera.dlc']
                data_list = time_series_list_details[0]['data']
                timestamps_list = time_series_list_details[0]['timestamps']
                for dataname, data, timestamps in zip(dataname_list, data_list, timestamps_list):
                    colnames = data.columns
                    data_np = data.to_numpy()
                    x_column_ids = [n for n, k in enumerate(colnames) if 'x' in k]
                    for x_column_id in x_column_ids:
                        data_loop = data_np[:, x_column_id:x_column_id + 2]
                        position_cont.create_spatial_series(name=dataname + colnames[x_column_id][:-2], data=data_loop,
                                                            reference_frame='none', timestamps=timestamps,
                                                            conversion=1e3)
                self.nwbfile.processing['behavior'].add(position_cont)
            elif not (i == 'BehavioralEpochs'):
                time_series_func = pynwb.TimeSeries
                time_series_list_details = self._get_data(self.nwb_metadata['Behavior'][i]['time_series'])
                if len(time_series_list_details) == 0:
                    continue
                time_series_list_obj = [time_series_func(**i) for i in time_series_list_details]
                func = getattr(pynwb.behavior, i)
                self.nwbfile.processing['behavior'].add(func(time_series=time_series_list_obj))
            else:
                time_series_func = pynwb.misc.IntervalSeries
                time_series_list_details = self._get_data(self.nwb_metadata['Behavior'][i]['interval_series'])
                if len(time_series_list_details) == 0:
                    continue
                for k in time_series_list_details:
                    k['timestamps'] = k['timestamps'].flatten()
                    k['data'] = np.vstack((k['data'], -1*np.ones(k['data'].shape, dtype=float))).flatten()
                time_series_list_obj = [time_series_func(**i) for i in time_series_list_details]
                func = getattr(pynwb.behavior, i)
                self.nwbfile.processing['behavior'].add(func(interval_series=time_series_list_obj))

    def create_acquisition(self):
        """
        Acquisition data like audiospectrogram(raw beh data), nidq(raw ephys data), raw camera data.
        These are independent of probe type.
        """
        for func, argmts in self.nwb_metadata['Acquisition'].items():
            data_retrieve = self._get_data(argmts)
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
                    i.update(dict(starting_time=np.float64(starting_time), rate=1/np.mean(np.diff(ts.squeeze())),
                                  unit='sec'))
                    self.nwbfile.add_acquisition(nwbfunc(**i))
                else:
                    if i['name'] in ['raw.lf', 'raw.ap']:
                        for j, probes in enumerate(range(self.no_probes)):
                            self.nwbfile.add_acquisition(
                                TimeSeries(
                                    name=i['name'] + '_' + self.nwb_metadata['Probes'][j]['name'],
                                    starting_time=i['timestamps'][j][0, 1],
                                    rate=i['data'][j].fs,
                                    data=H5DataIO(DataChunkIterator(iter_datasetview(i['data'][j])),
                                                  compression=True, shuffle=self.shuffle,
                                                  compression_opts=self.complevel)))
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
        table_data = self._get_data(self.nwb_metadata['Trials'])
        required_fields = ['start_time', 'stop_time']
        required_data = [i for i in table_data if i['name'] in required_fields]
        optional_data = [i for i in table_data if i['name'] not in required_fields]
        if len(required_fields) != len(required_data):
            warnings.warn('could not find required datasets: trials.start_time, trials.stop_time, '
                          'skipping trials table')
            return
        for start_time, stop_time in zip(required_data[0]['data'][:, 0], required_data[1]['data'][:, 1]):
            self.nwbfile.add_trial(start_time=start_time, stop_time=stop_time)
        for op_data in optional_data:
            self.nwbfile.add_trial_column(name=op_data['name'],
                                          description=op_data['description'],
                                          data=op_data['data'])

    def _get_data(self, sub_metadata):
        """
        Uses OneData class to query ONE datasets on server and download them locally
        Parameters
        ----------
        sub_metadata: dict
            metadata dict containing a data field with a dataset type to retrieve data from(npy, tsv etc)

        Returns
        -------
        out_dict: dict
            dictionary with actual data loaded in the data field
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
                    j[alt_names] = self.one_data.download_dataset(j[alt_names], j['name'])
            if j['name'] == 'id':  # valid in case of units table.
                j['data'] = self.one_data.download_dataset(j['data'], 'cluster_id')
            else:
                out_dict[i]['data'] = self.one_data.download_dataset(j['data'], j['name'])
            if out_dict[i]['data'] is not None:
                include_idx.extend([i])
        out_dict_trim.extend([out_dict[j0] for j0 in include_idx])
        return out_dict_trim

    def run_conversion(self):
        """
        Single method to create all datasets and metadata in nwbfile in one go
        Returns
        -------

        """
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

    def write_nwb(self, read_check=True):
        """
        After run_conversion(), write nwbfile to disk with the loaded nwbfile
        Parameters
        ----------
        read_check: bool
            Round trip verification
        """
        print('Saving to file, please wait...')
        with NWBHDF5IO(self.saveloc, 'w') as io:
            io.write(self.nwbfile)
            print('File successfully saved at: ', str(self.saveloc))

        if read_check:
            with NWBHDF5IO(self.saveloc, 'r') as io:
                io.read()
                print('Read check: OK')

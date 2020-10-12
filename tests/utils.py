from ndx_ibl_metadata import IblSessionData, IblSubject, IblProbes
from pynwb import NWBFile, TimeSeries
from ndx_spectrum import Spectrum
from pynwb.misc import DecompositionSeries

def _get_values_dict(names_list, docval_list):
    return_dict=dict()
    for i in names_list:
        for j in docval_list:
            if i in j['name']:
                return_dict.update({i:j['type']})
    return return_dict

metafile_base_fields = ['eid','probes','NWBFile','IBLSessionsData','IBLSubject','Behavior',
                        'Trials','Stimulus','Units','ElectrodeTable','Ecephys','Acquisition',
                        'Ophys','Icephys']

_nwbfile_optional_fields = [
    'experiment_description',
    'session_id',
    'institution',
    'notes',
    'pharmacology',
    'protocol',
    'slices',
    'source_script',
    'source_script_file_name',
    'data_collection',
    'surgery',
    'virus',
    'stimulus_notes',
    'lab',
    'experimenter',
    'related_publications']
_nwbfile_required_fields = [
    'session_description',
    'identifier',
    'session_start_time']
_subject_data_fields = [i['name'] for i in IblSubject.__init__.__docval__['args']]
_sessions_data_fields = [i['name'] for i in IblSessionData.__init__.__docval__['args']]
_probes_data_fields = [i['name'] for i in IblProbes.__init__.__docval__['args']]
_timeseries_data_fields = [i['name'] for i in TimeSeries.__init__.__docval__['args']]
_spectrum_data_fields = [i['name'] for i in Spectrum.__init__.__docval__['args']]
_decomposition_data_fields = [i['name'] for i in DecompositionSeries.__init__.__docval__['args']]

nwbfile_required_dict = _get_values_dict(_nwbfile_required_fields,
                                        NWBFile.__init__.__docval__['args'])
nwbfile_optional_dict = _get_values_dict(_nwbfile_optional_fields,
                                        NWBFile.__init__.__docval__['args'])
subject_data_dict = _get_values_dict(_subject_data_fields,
                                        IblSubject.__init__.__docval__['args'])
sessions_data_dict = _get_values_dict(_sessions_data_fields,
                                        IblSessionData.__init__.__docval__['args'])
probes_data_dict = _get_values_dict(_probes_data_fields,
                                        IblProbes.__init__.__docval__['args'])

timeseries_data_dict = {i:str for i in _timeseries_data_fields}
spectrum_data_dict = {i:str for i in _spectrum_data_fields}
decomposition_data_dict = {i:str for i in _decomposition_data_fields}

dt_columns_data_dict = dict(name=str,data=str,description=str)
device_data_dict = dict(name=str,description=str)
electrode_group_data_dict = dict(name=str, description=str,device=str,location=str)
from NWBToONE.nwb_to_ibl_metadata.nwb_to_ibl_metadata import NWBToIBLSession
from pathlib import Path

nwbfilename='iblguisave_5e4a.nwb'

nwb_filepath=str(Path(__file__).parent.parent.joinpath('guitests').joinpath(nwbfilename))
json_session_path = str(Path(__file__).parent.joinpath('sessions_'+nwbfilename[-8:-4]+'.json'))
json_subject_path = str(Path(__file__).parent.joinpath('subject_'+nwbfilename[-8:-4]+'.json'))

nwb2ibl=NWBToIBLSession(nwb_filepath)

nwb2ibl.write_json(json_session_path,'sessions')

nwb2ibl.write_json(json_subject_path,'subject')
from oneibl.one import ONE
from ibl_to_nwb.AlyxToNWB.alyx_to_nwb_metadata import Alyx2NWBMetadata
from ibl_to_nwb.AlyxToNWB.alyx_to_nwb_converter import Alyx2NWBConverter
from joblib import Parallel, delayed
from pathlib import Path
from pynwb import NWBHDF5IO
from csv import writer, reader
import pandas as pd
from tqdm import tqdm

with open(r'path-to-csv.csv','r') as io:
    eid_list = [row[0] for row in reader(io)]
one = ONE()
dir = Path.cwd()
metadata_errors = dir/f'metadata_errors.csv'
converter_errors = dir/f'converter_errors.csv'
def converter(eid,no):
    fileloc = dir/f'beh_eid_{eid}.json'
    nwb_saveloc = dir/f'beh_eid_{eid}.nwb'
    print(no)
    if not Path(fileloc).is_file():
        try:
            converter_metadata = Alyx2NWBMetadata(eid=eid, one_obj=one)
            converter_metadata.write_metadata(fileloc)
        except Exception as e:
            print(f'could not convert metadata for {eid}\n {str(e)}')
            with open(metadata_errors, 'a+', newline='') as write_obj:
                # Create a writer object from csv module
                csv_writer = writer(write_obj)
                csv_writer.writerow([eid, str(e)])
            return

    if not Path(nwb_saveloc).is_file():
        try:
            converter_nwb = Alyx2NWBConverter(one_object=one, nwb_metadata_file=fileloc,
                                              saveloc=nwb_saveloc,
                                              save_raw=False)

            execute_list = [converter_nwb.create_stimulus,
                            converter_nwb.create_trials,
                            converter_nwb.create_behavior,
                            converter_nwb.create_probes,
                            converter_nwb.create_iblsubject,
                            converter_nwb.create_lab_meta_data,
                            converter_nwb.create_acquisition]
            t = tqdm(execute_list)
            for i in t:
                t.set_postfix(current=f'creating nwb ' + i.__name__.split('_')[-1])
                i()
            print('done converting')

            converter_nwb.write_nwb()
        except Exception as e:
            print(f'could not convert for {eid}, {e}')
            with open(converter_errors, 'a+', newline='') as write_obj:
                # Create a writer object from csv module
                csv_writer = writer(write_obj)
                csv_writer.writerow([eid, str(e)])


Parallel(n_jobs=20)(delayed(converter)(eid,no) for no,eid in enumerate(eid_list))

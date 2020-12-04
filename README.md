# IBL-to-nwb
[![PyPI version](https://badge.fury.io/py/ibl-to-nwb.svg)](https://badge.fury.io/py/ibl-to-nwb)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

This repository houses the modules used to convert IBL specific neurophysiology data in the open source [ONE](https://docs.internationalbrainlab.org/en/stable/03_tutorial.html) format (Alyx + ALF) into NWB data standard.

- __Alyx__: a data base that contains all the metadata associated with an experiment: session details, subject details, probe information etc. This data has a one-to-one mapping to supported metadata of NWB. 
- __ALF__: format for storage of all the experimental data: electrophysiology time series (raw + processed), trials data, sorted spikes data, behavior (raw + processed), stimulus.
The figure below shows the mapping from ALF/ALyx to NWB: 
![](https://github.com/catalystneuro/IBL-to-nwb/blob/documentation/images/ibl_nwb_map.jpg)

## Usage:
1. **IBL to NWB conversion (using API):**  
 
    1. Installation: 
    
    create virtual environment and install dependencies from requirements.txt: 
       
    ```shell
    conda env create -n IBL2NWB
    conda activate IBL2NWB
    # alternatively create a venv and activate:
    python -m venv iblvenv
    activate ~\iblvenv\Scripts\Activate
    ```
       
    ```shell
    pip install ibl_to_nwb
    ```
       
    2. Retrive the id of the experiment of interest using [ONE](https://docs.internationalbrainlab.org/en/stable/03_tutorial.html) api:
    
       ```python
       from oneibl.one import ONE
       one=ONE()
       # use the ONE doc to use correct search terms to retrieve the eid
       eid = one.search(date_range=['2020-03-23', '2020-03-24'],subject='CSH_ZAD_011')[0]
       # example eid:
       eid = 'da188f2c-553c-4e04-879b-c9ea2d1b9a93'
       ```
     3. Using the eid, generate a json file containing all the collected data/metadata from the servers (Example output [file](https://github.com/catalystneuro/IBL-to-nwb/blob/master/AlyxToNWB/schema/example_metadata_output_file.json)):
     
        ```python
        from ibl_to_nwb import Alyx2NWBMetadata
        metadata_object = Alyx2NWBMetadata(eid=eid,one_obj=one)
        # alternatively, you can also provide one search **kwargs directly:
        metadata_obj = Alyx2NWBMetadata(date_range=['2020-03-23', '2020-03-24'],subject='CSH_ZAD_011')
        json_save_loc = r'path-to-save-json-file.json'
        metadata_obj.write_metadata(json_save_loc)
        ```
     4. Generate nwb file using the saved json file:
      
        ```python
        from ibl_to_nwb import Alyx2NWBConverter
        nwb_saveloc = r'nwb-save-path.nwb'
        save_raw = False # keep as true if you want to add raw (ephysData.raw.* , camera.raw*) files, these are large files and will take time to download and create the nwbfile!!
        converter=Alyx2NWBConverter(nwb_metadata_file=json_save_loc, saveloc=nwb_saveloc, save_raw=save_raw)
        # alternatively you can also provide the metadata object:
        converter=Alyx2NWBConverter(metadata_obj=metadata_obj, saveloc=nwb_saveloc)
        # create nwb file: 
        converter.run_conversion()
        converter.write_nwb()
        ```
        
     This should create an nwb file. [Example file](https://drive.google.com/file/d/1BEQ0z-qby6tO_QtA_FJ-Up51Thh6jYGu/view?usp=sharing). 
       

2. **IBL to NWB conversion (using GUI):** 

    ```python
    from ibl_to_nwb import Alyx2NWBGui
    Alyx2NWBGui(eid=eid, nwbfile_saveloc=nwb_saveloc, metadata_fileloc=json_save_loc)
    #alternatively provide the one search kwargs:
    Alyx2NWBGui(nwbfile_saveloc=nwb_saveloc, metadata_fileloc=json_save_loc, dataset_types=['_iblmic_audioSpectrogram.frequencies''])
    ```
    This opens up a gui which will allow you to edit nwbfile/ibl session related metadata and also convert to nwb using `run_conversion` button. Check the animation       below on how to navigate this gui:
    
    ![](https://github.com/catalystneuro/IBL-to-nwb/blob/master/images/gui_gif.gif)
    
3. **Visualization of nwbfile using [nwbwigets](https://github.com/NeurodataWithoutBorders/nwb-jupyter-widgets) in a __Jupyter notebook__**:
 
    ```python
    from pynwb import NWBHDF5IO
    from nwbwidgets import nwb2widget
    from IPython.display import display
    io = NWBHDF5IO(r"path-to-saved-nwb-file.nwb", mode='r', load_namespaces=True)
    nwb = io.read()
    a=nwb2widget(nwb)
    display(a)
    ```
    ![](https://github.com/catalystneuro/IBL-to-nwb/blob/master/images/nwbwidgets.gif)
    
4. **Parallization of a large batch of eids:** Retrieve a list of eids based on a search criteria.

    ```python
   from joblib import Parallel, delayed
   from oneibl.one import ONE
   from ibl_to_nwb.AlyxToNWB.alyx_to_nwb_metadata import Alyx2NWBMetadata
   from ibl_to_nwb.AlyxToNWB.alyx_to_nwb_converter import Alyx2NWBConverter
   one=ONE()
   eid_list = ['0963537d-9c46-4245-9cbf-de1d42a49c02',
               'b2727b3b-6ed2-486d-a283-a5970a48d471'] # define a list of eids to convert
   
   # define a conversion function
   def eid_convert_nwb(eid):
       nwbfile_saveloc = f'nwbfile{eid}.nwb'#define a save location for each eid
       metadata_saveloc = f'metadata{eid}.json'#define a save location for metadata file
       converter_metadata = Alyx2NWBMetadata(eid=eid, one_obj=one)
       converter_metadata.write_metadata(metadata_saveloc)
   
       converter_nwb = Alyx2NWBConverter(one_object=one, 
                                         nwb_metadata_file=metadata_saveloc, 
                                         saveloc=nwbfile_saveloc,
                                         save_raw=False)
       converter_nwb.run_conversion()
       converter_nwb.write_nwb()
   
   # use parallelization
   Parallel(n_jobs=-1)(delayed(eid_convert_nwb)(eid) for eid in eid_list)
``

# IBL-to-nwb
This repository houses the modules used to convert IBL specific neurophysiology data in the open source [ONE](https://docs.internationalbrainlab.org/en/stable/03_tutorial.html) format (Alyx + ALF) into NWB data standard.

- __Alyx__: a data base that contains all the metadata associated with an experiment: session details, subject details, probe information etc. This data has a one-to-one mapping to supported metadata of NWB. 
- __ALF__: format for storage of all the experimental data: electrophysiology time series (raw + processed), trials data, sorted spikes data, behavior (raw + processed), stimulus.
The figure below shows the mapping from ALF/ALyx to NWB: 
![](https://github.com/catalystneuro/IBL-to-nwb/blob/documentation/images/ibl_nwb_map.jpg)

## Usage:
1. **IBL to NWB conversion (using API):**  
 
    1. Installation: 
    
       ```shell
       cd desired-path
       git clone https://github.com/catalystneuro/IBL-to-nwb.git
       cd IBL-to-nwb
       ```
       create virtual environment and install dependencies from requirements.txt: 
       
       ```shell
       python -m venv venv
       venv\Scripts\activate
       pip install -r requirements.txt
       ```
    2. Retrive the id of the experiment of interest using [ONE](https://docs.internationalbrainlab.org/en/stable/03_tutorial.html) api:
    
       ```python
       from oneibl.one import ONE
       one=ONE()
       # use the ONE doc to use correct search terms to retrieve the eid
       eid = one.search(dataset_types=['_iblmic_audioSpectrogram.frequencies'])[0]
       ```
     3. Using the eid, generate a json file containing all the collected data/metadata from the servers:
     
        ```python
        from .AlyxToNWB import Alyx2NWBMetadata
        metadata_object = Alyx2NWBMetadata(eid=eid,one_obj=one)
        # alternatively, you can also provide one search **kwargs directly:
        metadata_obj = Alyx2NWBMetadata(dataset_types=['_iblmic_audioSpectrogram.frequencies'])
        json_save_loc = r'path-to-save-json-file.json'
        metadata_obj.write_metadata(json_save_loc)
        ```
     4. Generate nwb file using the saved json file:
      
        ```python
        from .AlyxToNWB import Alyx2NWBConverter
        nwb_saveloc = r'nwb-save-path.nwb'
        converter=Alyx2NWBConverter(nwb_metadata_file=json_save_loc, saveloc=nwb_saveloc)
        # alternatively you can also provide the metadata object:
        converter=Alyx2NWBConverter(metadata_obj=metadata_obj, saveloc=nwb_saveloc)
        # create nwb file: 
        converter.run_conversion()
        ```
        
     This should create an nwb file. [Example file](https://drive.google.com/file/d/1BEQ0z-qby6tO_QtA_FJ-Up51Thh6jYGu/view?usp=sharing). 
       

2. **IBL to NWB conversion (using GUI):** 

    ```python
    from .AlyxToNWB import Alyx2NWBGui
    Alyx2NWBGui(eid=eid, nwbfile_saveloc=nwb_saveloc, metadata_fileloc=json_save_loc)
    #alternatively provide the one search kwargs:
    Alyx2NWBGui(nwbfile_saveloc=nwb_saveloc, metadata_fileloc=json_save_loc, dataset_types=['_iblmic_audioSpectrogram.frequencies''])
    ```
    This opens up a gui which will allow you to edit nwbfile/ibl session related metadata and also convert to nwb using `run_conversion` button. Check the animation       below on how to navigate this gui:
    
    ![](https://github.com/catalystneuro/IBL-to-nwb/blob/documentation/images/gui_gif.gif)
    
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


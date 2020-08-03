# IBL-to-nwb
This repository houses the modules used to convert IBL specific neurophysiology data present in their propreitary format (Alyx + ALF) into NWB data standard. 

- __Alyx__: a data base that contains all the metadata associated with an experiment: session details, subject details, probe information etc. This data has a one-to-one mapping to supported metadata of NWB. 
- __ALF__: format for storage of all the experimental data: electrophysiology time series (raw + processed), trials data, sorted spikes data, behavior (raw + processed), stimulus.
The figure below shows the mapping from ALF/ALyx to NWB: 
 (Image)

## Usage:
1. **IBL to NWB conversion:**  

    The conversion is a two step process: 
- The metadata and names of data files are first retrieved from the databases: mapped to the framework of various inbuilt NWB [neurodata_types](https://nwb-schema.readthedocs.io/en/latest/format_description.html). For example, electrophysiology time series raw data is mapped into NWB [Timeseries](https://nwb-schema.readthedocs.io/en/latest/format_description.html#time-series-a-base-neurodata-type-for-storing-time-series-data) by unpacking that into fields: `name`, `description`, `timestamps` and `data` which constitute the `TimeSeries` datatype. Similar unpacking happends for various other data to match the corresponding NWB datatype. 

    These unpacked datatypes are then structured in a hirarchical manner into a schema (in compliance with the NWB schema) which is then input to the next conversion step. 
    
- The schema is read, actual data retrieved from ALF servers and NWB file is created. The user has the option to specify changes to metadata using a gui before storage. This NWB file is stored locally on the users machine.    

2. **NWB file to IBL format:**
 
#### API usage: 

#### GUI usage: 


## Notes:


# IBL-to-nwb
[![PyPI version](https://badge.fury.io/py/ibl-to-nwb.svg)](https://badge.fury.io/py/ibl-to-nwb)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

This repository houses the modules used to convert IBL specific neurophysiology data in the open source [ONE](https://docs.internationalbrainlab.org/en/stable/03_tutorial.html) format (Alyx + ALF) into NWB data standard.

- __Alyx__: a data base that contains all the metadata associated with an experiment: session details, subject details, probe information etc. This data has a one-to-one mapping to supported metadata of NWB. 
- __ALF__: format for storage of all the experimental data: electrophysiology time series (raw + processed), trials data, sorted spikes data, behavior (raw + processed), stimulus.
The figure below shows the mapping from ALF/ALyx to NWB: 

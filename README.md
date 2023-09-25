# IBL-to-nwb
[![PyPI version](https://badge.fury.io/py/ibl-to-nwb.svg)](https://badge.fury.io/py/ibl-to-nwb)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

This repository houses conversion piplines for the IBL data releases, including the Brain Wide Map project.



# Installation

For Brain Wide Map,

```
git clone https:/github.com/catalystneuro/IBL-to-nwb
cd IBL-to-nwb
pip install -e .[brainwide_map]
```

(not tested on all platforms or Python environments)



# How to convert processed-only data for BWM

From the first level of the repo as the working directory,

```
python ibl_to_nwb/updated_conversion/brainwide_map/convert_brainwide_map_processed_only_parallel.py
```

The script contains some values that might want to be changed, such as `number_of_parallel_jobs`, or `base_path` if not running on the DANDI Hub.

The block about skipping sessions already on DANDI would need to be commented out if a 'patch' conversion + new release is being performed.

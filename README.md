# IBL-to-nwb
[![PyPI version](https://badge.fury.io/py/ibl-to-nwb.svg)](https://badge.fury.io/py/ibl-to-nwb)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

This repository houses conversion pipelines for the IBL data releases, including the Brain Wide Map project.



# Installation

```
git clone https:/github.com/catalystneuro/IBL-to-nwb
cd IBL-to-nwb
pip install -e .
```

for the exact environment used for the initial conversion, see `src/ibl_to_nwb/_environments`.

It is recommended to follow a similar approach for future conversions to leave a record of provenance.



# Running data conversions

## NeuroConv structure

NeuroConv has two primarily classes for handling conversions.

An `Interface` reads a single data stream (such as DLC pose estimation) and creates one or more neurodata objects, adding them to an in-memory `pynwb.NWBFile` object via the `.add_to_nwbfile` method. Before that it can also fetch and set local `metadata: dict` values for use or modification.

The `Converter` orchestrates the conversion by combining multiple interfaces, and can also be used to add additional metadata to the NWB file. It is responsible for creating the NWB file saved to disk.

## Metadata

Anywhere you see handwritten text in the NWB files that is meant to be human-readable, it is likely that it was copied from the public Google IBL documents and written in the `.yaml` files found in `src/ibl_to_nwb/_metadata`.

Occasionally, especially if a portion of the text is pulled from source data, these values might be overwritten in the `.add_to_nwbfile` protocol of an interface, so always be sure to check that as well.

## Raw only

Open the script `src/ibl_to_nwb/_scripts/convert_brainwide_map_raw_only.py`.

Change any values at the top as needed, such as the `session_id` (equivalent to the 'eid' of ONE).

Then run the script.

## Processed only

Open the script `src/ibl_to_nwb/_scripts/convert_brainwide_map_processed_only.py`.

Change any values at the top as needed, such as the `session_id` (equivalent to the 'eid' of ONE).

Then run the script.



# Upload to DANDI

Set the environment variable `DANDI_API_KEY`, obtainable from clicking on your initials in the top right of https://dandiarchive.org/dandiset.

In an fresh environment, install the DANDI CLI:

```
pip install dandi
```

Download a shell of the dandiset:

```
dandi download DANDI:000409 --download dandiset.yaml
```

All outputs from the conversion scripts should be pre-organized, so we can just directly move all the `sub-` folders from the conversion output directory into the Dandiset folder. This should appear like:

```
|- 000409
|   |- sub-CSH-ZAR-001
|   |-   |- sub-CSH-ZAR-001_ses-3e7..._desc-processed_behavior+ecephys.nwb
|   |-   |- sub-CSH-ZAR-001_ses-3e7..._desc-raw_ecephys+image.nwb
|   |-   |- ...
|   |- ...
```


From a working directory of `000409`, you can either scan for validations directly with:

```
dandi validate .
```

Of course, all assets ought to be valid, so you could also just directly upload the data to DANDI (this will also run validation as it iterates through the files):

```
dandi upload
```

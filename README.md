# IBL-to-NWB

[![PyPI version](https://badge.fury.io/py/ibl-to-nwb.svg)](https://badge.fury.io/py/ibl-to-nwb)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

IBL-to-NWB is the data conversion pipeline that produced the
[Brain Wide Map NWB dataset](https://dandiarchive.org/dandiset/000409) on the
DANDI Archive. It transforms International Brain Laboratory (IBL) experimental
data into Neurodata Without Borders (NWB) format using
[NeuroConv](https://neuroconv.readthedocs.io/).

The dataset contains both raw electrophysiology recordings and processed
behavioral/spike sorting data for hundreds of Neuropixels sessions across
multiple labs.

## Using the data

The converted data is publicly available on DANDI. You can stream NWB files
directly without downloading them:

```python
from dandi.dandiapi import DandiAPIClient
import remfile, h5py
from pynwb import NWBHDF5IO

client = DandiAPIClient()
dandiset = client.get_dandiset("000409", "draft")

# Find a session
session_eid = "6ed57216-498d-48a6-b48b-a243a34710ea"
assets = [a for a in dandiset.get_assets() if session_eid in a.path]
processed = next(a for a in assets if "desc-processed" in a.path)

# Stream it
s3_url = processed.get_content_url(follow_redirects=1, strip_query=False)
file = h5py.File(remfile.File(s3_url), "r")
io = NWBHDF5IO(file=file, load_namespaces=True)
nwbfile = io.read()
```

See [notebooks/bwm_usage_notebook.ipynb](notebooks/bwm_usage_notebook.ipynb)
for a complete walkthrough of the dataset including trials, spike sorting,
pose estimation, wheel data, and video streaming.

## Running conversions

**See [documentation/introduction_to_documentation.md](documentation/introduction_to_documentation.md) for complete documentation including system architecture, concepts, and how-tos.**

### Installation

```bash
git clone https://github.com/catalystneuro/IBL-to-nwb.git
cd IBL-to-nwb
uv sync
```

Alternatively, `pip install -e .` or `conda env create -f environment.yml`.
See [documentation/development/lock_files.md](documentation/development/lock_files.md)
for details on reproducing the exact conversion environment.

### Convert a single session

```bash
uv run python src/ibl_to_nwb/_scripts/convert_single_bwm_to_nwb.py <session-eid>
```

Or edit `TARGET_EID` in the script and run without arguments. The script
requires ONE API credentials (you will be prompted on first use).

## Project structure

```
src/ibl_to_nwb/
├── datainterfaces/      # Modality-specific data readers
├── converters/          # High-level orchestrators
├── conversion/          # Entry points (raw.py, processed.py, session.py)
├── utils/               # Shared utilities (atlas, electrodes, etc.)
├── _metadata/           # YAML metadata templates
├── _scripts/            # Conversion and debugging scripts
└── _aws/                # AWS distributed infrastructure
```

## Environment

- Python 3.10+ (tested on 3.10, 3.12, 3.13)
- Uses `uv` for dependency management
- Lock files: `uv.lock`, `pylock.toml` (PEP 751), `environment.yml` (conda)

## License

BSD 3-Clause License. See LICENSE file for details.

## Citation

If you use this dataset or pipeline in your research, please cite:

- The International Brain Laboratory et al., "Brain Wide Map" (2024). DANDI:000409.
- NWB: Neurodata Without Borders
- NeuroConv

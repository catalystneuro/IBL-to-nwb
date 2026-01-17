# IBL-to-NWB

[![PyPI version](https://badge.fury.io/py/ibl-to-nwb.svg)](https://badge.fury.io/py/ibl-to-nwb)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

IBL-to-NWB is a data conversion pipeline that transforms International Brain Laboratory (IBL) experimental data into Neurodata Without Borders (NWB) format. The pipeline uses NeuroConv, a flexible data conversion framework, to orchestrate multiple data interfaces that read IBL-specific formats and write standardized NWB files.

**See [documentation/index.md](documentation/index.md) for complete documentation including system architecture, concepts, and how-tos.**

## Quick Start

### Installation

```bash
git clone https://github.com/h-mayorquin/IBL-to-nwb.git
cd IBL-to-nwb
pip install -e .
```

For development, install with `uv sync --group dev`.

### Running a Conversion

1. **Configure ONE API access** (first time only):
   ```bash
   python -c "from one.api import ONE; one = ONE()"
   ```
   You'll be prompted for lab name and credentials.

2. **Edit the conversion script**:
   ```bash
   vim src/ibl_to_nwb/_scripts/convert_bwm_to_nwb.py
   # Change: session_id = "your-session-uuid"
   ```

3. **Run the conversion**:
   ```bash
   python src/ibl_to_nwb/_scripts/convert_bwm_to_nwb.py
   ```

The script converts both raw and processed data to NWB format and saves the files locally.

### Testing Before Full Conversion

```bash
# Quick test with minimal data (~5 minutes)
python -c "
from ibl_to_nwb.conversion import convert_raw_session
from one.api import ONE

one = ONE()
convert_raw_session(eid='your-session-uuid', one=one, stub_test=True)
"
```


## Project Structure

```
src/ibl_to_nwb/
├── datainterfaces/      # Modality-specific data readers
├── converters/          # High-level orchestrators
├── conversion/          # Entry points (raw.py, processed.py)
├── utils/               # Shared utilities (atlas, electrodes, etc.)
├── _metadata/           # YAML metadata templates
├── _scripts/            # Conversion and debugging scripts
└── _aws/                # AWS distributed infrastructure
```

## Development

For contributing to the codebase:

1. Install dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

2. Run code quality checks:
   ```bash
   ruff check src/
   black src/
   pre-commit run --all-files
   ```

3. See [documentation/conversion/ibl_data_interface_design.md](documentation/conversion/ibl_data_interface_design.md) for adding new interfaces.

## Key Dependencies

- **neuroconv** - Data conversion framework
- **pynwb** - NWB file I/O
- **ndx-ibl**, **ndx-ibl-bwm** - IBL-specific NWB extensions
- **ONE-api** - IBL data access
- **ibllib** - IBL-specific utilities
- **spikeinterface**, **probeinterface** - Electrophysiology tools

## Environment

- Python 3.10+ (tested on 3.11, 3.12, 3.13)
- Uses `uv` for fast dependency management

## License

BSD 3-Clause License - See LICENSE file for details.

## Citation

If you use this pipeline in your research, please cite:
- International Brain Laboratory
- NWB: Neurodata Without Borders
- NeuroConv

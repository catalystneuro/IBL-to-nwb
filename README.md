# IBL-to-NWB

[![PyPI version](https://badge.fury.io/py/ibl-to-nwb.svg)](https://badge.fury.io/py/ibl-to-nwb)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

IBL-to-NWB is a data conversion pipeline that transforms International Brain Laboratory (IBL) experimental data into Neurodata Without Borders (NWB) format. The pipeline uses NeuroConv, a flexVible data conversion framework, to orchestrate multiple data interfaces that read IBL-specific formats and write standardized NWB files.

**See [documentation/introduction_to_documentation.md](documentation/introduction_to_documentation.md) for complete documentation including system architecture, concepts, and how-tos.**

## Quick Start

### Installation

```bash
git clone https://github.com/catalystneuro/IBL-to-nwb.git
cd IBL-to-nwb
pip install -e .
```

For development, install with `uv sync --group dev`.

### Running a Conversion

1. **Configure ONE API access** (first time only):
   ```bash
   python -c "from one.api import ONE; one = ONE()"
   ```
   You'll be prompted for credentials.

2. **Convert a single session**:
   ```bash
   python src/ibl_to_nwb/_scripts/convert_single_bwm_to_nwb.py <session-eid>
   ```

   Or edit `TARGET_EID` in the script and run without arguments.

3. **Convert all Brain-Wide Map sessions**:
   ```bash
   python src/ibl_to_nwb/_scripts/convert_bwm_to_nwb.py
   ```

The scripts convert both raw and processed data to NWB format and save the files locally.


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

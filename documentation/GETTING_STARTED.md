# Getting Started with Development

This guide is for **developers** working on the IBL-to-NWB codebase. For general installation and usage, see the [main README.md](../README.md).

## Prerequisites

- **Python 3.10+** (tested on 3.11, 3.12, 3.13)
- **Git** - For cloning the repository
- **ONE API access** - To download IBL data (contact the lab for credentials)

## Development Setup

### 1. Clone and Install

```bash
git clone https://github.com/h-mayorquin/IBL-to-nwb.git
cd IBL-to-nwb
uv sync --group dev  # Install with dev dependencies
```

### 2. Configure ONE API

```bash
# The ONE library will prompt you for your credentials on first use
python -c "from one.api import ONE; one = ONE()"
```

You'll be asked for:
- **Lab name** (e.g., "mainenlab", "steinmetzlab")
- **Username/password** or **token**

Credentials are saved locally in `~/.one/` for future use.

## Code Quality Commands

```bash
# Check code style with ruff
ruff check src/

# Auto-fix style issues
ruff check --fix src/

# Format code with black
black src/

# Run all pre-commit hooks
pre-commit run --all-files

# Run tests
pytest tests/
```

## Testing Conversions

### Quick Test (Stub Mode)

```bash
# Download minimal data and test conversion (~5 minutes)
python -c "
from ibl_to_nwb.conversion import convert_raw_session
from one.api import ONE

one = ONE()
# Edit with your session UUID
convert_raw_session(eid='your-session-uuid', one=one, stub_test=True)
"
```

### Full Conversion Test

```bash
# Edit with your session UUID and run
python src/ibl_to_nwb/_scripts/heberto_conversion_script.py
```

### Inspect Output

```bash
# View the generated NWB file
python src/ibl_to_nwb/_scripts/inspect_single.py
```

## Understanding the Codebase

**Key files to read first:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design and key abstractions
- `src/ibl_to_nwb/datainterfaces/_base_ibl_interface.py` - Base pattern for all interfaces
- `src/ibl_to_nwb/converters/brainwide_map_converter.py` - Main converter orchestration
- `src/ibl_to_nwb/conversion/raw.py` - Raw conversion entry point
- `src/ibl_to_nwb/conversion/processed.py` - Processed conversion entry point

**Directory structure:**
```
src/ibl_to_nwb/
├── datainterfaces/      # Individual data readers (pose, ephys, behavior, etc.)
├── converters/          # High-level orchestrators
├── conversion/          # Entry points for raw/processed conversion
├── utils/               # Shared utilities (atlas, electrodes, metadata)
├── _metadata/           # YAML metadata templates
├── _scripts/            # Conversion scripts
└── _aws/                # AWS infrastructure for distributed processing
```

## Adding a New Interface

### 1. Create the Interface Class

```python
from ibl_to_nwb.datainterfaces import BaseIBLDataInterface

class MyNewInterface(BaseIBLDataInterface):
    REVISION = "2025-05-06"

    def get_data_requirements(self):
        """Declare what data is needed"""
        return {
            'dataset1.npy': 'alf/',
            'dataset2.npy': 'alf/',
        }

    def check_availability(self, one, eid):
        """Check if data exists without downloading"""
        try:
            one.list_datasets(eid, collection='alf')
            return {"available": True}
        except Exception as e:
            return {"available": False, "reason": str(e)}

    def download_data(self, one, eid, base_path):
        """Download data to local cache"""
        # Use one.load_dataset() to download
        pass

    def add_to_nwbfile(self, nwbfile, metadata):
        """Convert data and add to NWB file"""
        # Read data and write to nwbfile
        pass
```

### 2. Add to Converter

```python
# In src/ibl_to_nwb/converters/brainwide_map_converter.py
self.interfaces.append(MyNewInterface(eid, one))
```

### 3. Document in [conversion/conversion_modalities.md](conversion/conversion_modalities.md)

### 4. Add Tests

Create tests in `tests/` following the existing patterns.

## Debugging Tips

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect NWB File

```python
from pynwb import NWBHDF5IO

with NWBHDF5IO('file.nwb', 'r') as io:
    nwbfile = io.read()
    print(nwbfile)  # Overview
    print(nwbfile.units)  # Units table
    print(nwbfile.electrodes)  # Electrodes table
```

### Check Data Availability

```python
from one.api import ONE

one = ONE()
datasets = one.list_datasets('your-session-uuid')
print(datasets)  # See what data exists
```

## Common Issues

**Issue:** ONE API authentication fails
```bash
# Clear cached credentials and try again
rm -rf ~/.one/
python -c "from one.api import ONE; one = ONE()"
```

**Issue:** ModuleNotFoundError for neuroconv
```bash
# Reinstall with all dependencies
uv sync --group dev
```

**Issue:** Session data not found
```bash
# Check if you can list datasets
python -c "from one.api import ONE; one = ONE(); print(one.list_datasets('your-session-uuid'))"
```

## Next Steps

1. **Understand the system** → Read [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Learn the conversion flow** → Read [conversion/conversion_overview.md](conversion/conversion_overview.md)
3. **Explore specific topics** → Use the [index.md](index.md) to navigate
4. **Make changes** → Follow code quality checks above and add tests

## Documentation Map

- **System Overview** → [ARCHITECTURE.md](ARCHITECTURE.md)
- **Documentation Index** → [index.md](index.md)
- **All Documentation** → Browse [ibl_concepts/](ibl_concepts/), [conversion/](conversion/), [development/](development/), [dandi_and_aws/](dandi_and_aws/)

## Getting Help

- **Documentation** → [index.md](index.md)
- **Code comments** → Many interfaces have detailed docstrings
- **GitHub Issues** → https://github.com/h-mayorquin/IBL-to-nwb/issues
- **CLAUDE.md** → Project guidance for AI assistants (useful for developers too)

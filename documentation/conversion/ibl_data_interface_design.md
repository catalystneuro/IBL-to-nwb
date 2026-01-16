# IBL Data Interface Design

This document specifies the `BaseIBLDataInterface` contract and the `get_data_requirements()` architecture that ensures consistent data management across all interfaces.

## Design Philosophy

The interface design follows a **single source of truth** principle: each interface declares exactly what data it needs via `get_data_requirements()`, and both availability checking and downloading use this declaration. This ensures:

- **Explicit contracts** - No hidden data dependencies
- **Provenance tracking** - Clear audit trail of what files are converted
- **Fail-fast behavior** - Missing data is detected early
- **Testability** - Requirements can be validated without running full conversions

## The Three-Method Contract

Every interface inherits from `BaseIBLDataInterface` and implements three data management methods:

```
get_data_requirements()  ──────────────────────────────────────┐
        │                                                      │
        │  Declares exact files needed (source of truth)       │
        ↓                                                      │
check_availability() ← reads requirements, queries ONE API     │
        │              returns: available, alternative_used    │
        │              NO downloads, read-only check           │
        ↓                                                      │
download_data() ← reads requirements, downloads files          │
        │          uses REVISION class attribute               │
        │          returns: success, downloaded_files          │
        ↓                                                      │
add_to_nwbfile() ← loads data from cache (same files)  ────────┘
                   uses REVISION for consistency
```

### Method Signatures

```python
class BaseIBLDataInterface:
    REVISION: str | None = "2025-05-06"  # Class-level revision for reproducibility

    @classmethod
    @abstractmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        """Single source of truth for what data is needed."""
        ...

    @classmethod
    def check_availability(cls, one: ONE, eid: str, **kwargs) -> dict:
        """Read-only check without downloading. Uses get_data_requirements()."""
        ...

    @classmethod
    def download_data(cls, one: ONE, eid: str, **kwargs) -> dict:
        """Download files declared in get_data_requirements(). Fail-fast on errors."""
        ...

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, **kwargs) -> None:
        """Load cached data and write to NWB. Assumes download_data() was called."""
        ...
```

## Data Requirements Format

### Structure

`get_data_requirements()` returns a dictionary with two optional keys:

```python
@classmethod
def get_data_requirements(cls, **kwargs) -> dict:
    return {
        "one_objects": [...],           # Optional: ONE API object abstractions
        "exact_files_options": {...},   # Required: specific file paths
    }
```

### `one_objects` (Optional)

Declares data using ONE API's object abstraction. This is primarily for **documentation purposes** - it describes the logical data objects an interface needs, making it easier for developers to understand the data dependencies at a glance.

**Why a list?** A single interface often needs multiple related objects. For example, wheel data requires both the wheel position/timestamps AND the wheel movement intervals. Each object maps to a distinct `one.load_object()` call.

**Structure:**
```python
"one_objects": [
    {
        "object": "wheel",                              # ONE object name
        "collection": "alf",                            # Collection path (where to find it)
        "attributes": ["position", "timestamps"],       # Required attributes of this object
    },
    {
        "object": "wheelMoves",                         # Second object needed by this interface
        "collection": "alf",
        "attributes": ["intervals", "peakAmplitude"],
    },
]
```

**How it's used:**
- `download_data()` iterates through the list and calls `one.load_object()` for each entry
- `add_to_nwbfile()` loads the same objects from cache
- The `attributes` field documents which attributes are required (not all objects have all attributes)

**Note:** `check_availability()` uses `exact_files_options` for file-level checking, not `one_objects`. The `one_objects` field provides a higher-level view that maps to how the code loads data.

### `exact_files_options` (Required)

Declares exact file paths. This is what `check_availability()` and `download_data()` actually use.

**Single format (most common):**
```python
"exact_files_options": {
    "standard": [
        "alf/wheel.position.npy",
        "alf/wheel.timestamps.npy",
        "alf/wheelMoves.intervals.npy",
        "alf/wheelMoves.peakAmplitude.npy",
    ],
}
```

**Multiple format alternatives:**
```python
"exact_files_options": {
    "bwm_format": ["alf/trials.table.pqt"],
    "legacy_format": [
        "alf/trials.intervals.npy",
        "alf/trials.choice.npy",
        "alf/trials.feedbackType.npy",
        "alf/trials.contrastLeft.npy",
        "alf/trials.contrastRight.npy",
        # ... additional files
    ],
}
```

**When are multiple formats used?** Format alternatives handle cases where the same logical data exists in different file structures:
- **Data evolution**: IBL transitioned from many `.npy` files (`legacy_format`) to consolidated `.pqt` files (`bwm_format`). Older sessions have the legacy format; newer sessions have the consolidated format.
- **Processing pipelines**: Pose estimation can come from different trackers (Lightning Pose vs DeepLabCut), each producing different file formats.
- **Backward compatibility**: Supporting both formats allows the pipeline to convert both old and new sessions without modification.

The system tries options **in order** until finding one where ALL files exist. Put the preferred/newer format first.

**Wildcard patterns (for multi-probe sessions):**
```python
"exact_files_options": {
    "standard": [
        "alf/probe*/spikes.times.npy",
        "alf/probe*/spikes.clusters.npy",
        "alf/probe*/spikes.amps.npy",
        "alf/probe*/spikes.depths.npy",
    ],
}
```

### Option Names

Option names describe the format variant. Common conventions:

| Option Name | Meaning |
|-------------|---------|
| `"standard"` | Default/preferred format |
| `"bwm_format"` | Brain-Wide Map consolidated format (e.g., single parquet file) |
| `"legacy_format"` | Older file structure (multiple numpy files) |
| `"lightning_pose"` | Lightning Pose tracker output |
| `"dlc"` | DeepLabCut tracker output |

The system tries each option in order until finding one where ALL files exist.

## How Each Method Works

### `check_availability()`

The base class provides a default implementation that:

1. Calls `get_data_requirements()` to get `exact_files_options`
2. Queries ONE API for available datasets (no download)
3. Tries each option until finding one where ALL files exist
4. Returns availability status and which option was found

```python
# Simplified logic
requirements = cls.get_data_requirements(**kwargs)
available_datasets = one.list_datasets(eid)

for option_name, files in requirements["exact_files_options"].items():
    if all(file_exists(f, available_datasets) for f in files):
        return {
            "available": True,
            "alternative_used": option_name,
            "found_files": files,
        }

return {
    "available": False,
    "missing_required": missing_files,
}
```

**Key behaviors:**

- **No revision filtering**: Checks if ANY version exists (allows checking before specific revisions are available)
- **Wildcard expansion**: `probe*` patterns are expanded via regex
- **Namespace handling**: Tries both `wheel.position` and `_ibl_wheel.position`
- **Revision tag handling**: Ignores `#2025-05-06#` tags in filenames when matching

**Return format:**
```python
{
    "available": bool,              # True if any complete option found
    "missing_required": [str],      # Files not found (if unavailable)
    "found_files": [str],           # Files that were found
    "alternative_used": str,        # Option name that matched (e.g., "bwm_format")
    "requirements": dict,           # The full requirements dict
}
```

### `download_data()`

Downloads the files declared in `get_data_requirements()`:

```python
# Pattern 1: Object-based download
requirements = cls.get_data_requirements(**kwargs)
for obj_spec in requirements.get("one_objects", []):
    one.load_object(
        id=eid,
        obj=obj_spec["object"],
        collection=obj_spec["collection"],
        revision=cls.REVISION,
        download_only=True,
    )

# Pattern 2: File-based download with format fallback
for option_name, files in requirements["exact_files_options"].items():
    try:
        for file_path in files:
            one.load_dataset(eid, file_path, revision=cls.REVISION)
        return {"success": True, "alternative_used": option_name}
    except FileNotFoundError:
        continue  # Try next format option

raise FileNotFoundError("No complete format option available")
```

**Key behaviors:**

- **Uses REVISION**: Downloads the specific version declared in the class
- **Respects ONE cache**: Doesn't re-download if files already exist locally
- **Fail-fast**: Raises exceptions for missing required data
- **Format fallback**: Tries each option until one succeeds

**Return format:**
```python
{
    "success": bool,
    "downloaded_objects": [str],    # ONE objects that were downloaded
    "downloaded_files": [str],      # Individual files downloaded
    "already_cached": [str],        # Files that were already local
    "alternative_used": str,        # Which format option was used
}
```

### `add_to_nwbfile()`

Does **not** call `get_data_requirements()` directly. Instead:

1. Assumes data was already downloaded via `download_data()`
2. Loads from ONE's local cache using the same file paths
3. Uses the same `REVISION` for consistency

```python
def add_to_nwbfile(self, nwbfile, metadata, stub_test=False):
    # Load from cache - same files as declared in get_data_requirements
    wheel = self.one.load_object(
        id=self.session,
        obj="wheel",
        collection="alf",
        revision=self.revision,
    )

    # Process and add to NWB
    wheel_position = TimeSeries(
        name="wheel_position",
        data=wheel["position"],
        timestamps=wheel["timestamps"],
        unit="radians",
    )
    nwbfile.add_acquisition(wheel_position)
```

This design ensures the files loaded during conversion match what was declared and downloaded.

## Revision Handling

### Class-Level Declaration

Each interface declares a fixed revision for reproducibility:

```python
class WheelInterface(BaseIBLDataInterface):
    REVISION: str | None = "2025-05-06"  # Brain-Wide Map standard

class RawVideoInterface(BaseIBLDataInterface):
    REVISION: str | None = "2025-05-06"

class PassiveReplayStimInterface(BaseIBLDataInterface):
    # Some interfaces support multiple revision candidates
    REVISION_CANDIDATES: list[str] = ["2025-12-04", "2025-12-05"]
```

### Revision Flow

| Method | Revision Behavior |
|--------|-------------------|
| `check_availability()` | Ignores revision - checks if ANY version exists |
| `download_data()` | Uses `REVISION` - downloads specific version |
| `add_to_nwbfile()` | Uses `REVISION` - loads specific version |

This allows availability checking to work even before specific revisions exist, while ensuring conversion uses consistent data versions.

## Complete Examples

### Simple Interface: LickInterface

Single file, single format:

```python
class LickInterface(BaseIBLDataInterface):
    REVISION: str | None = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        return {
            "exact_files_options": {
                "standard": ["alf/licks.times.npy"],
            },
        }

    def add_to_nwbfile(self, nwbfile, metadata, stub_test=False):
        lick_times = self.one.load_dataset(
            self.session,
            "licks.times",
            collection="alf",
            revision=self.revision,
        )
        # Add to NWB...
```

### Object-Based Interface: WheelInterface

Uses ONE objects with multiple attributes:

```python
class WheelInterface(BaseIBLDataInterface):
    REVISION: str | None = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        return {
            "one_objects": [
                {
                    "object": "wheel",
                    "collection": "alf",
                    "attributes": ["position", "timestamps"],
                },
                {
                    "object": "wheelMoves",
                    "collection": "alf",
                    "attributes": ["intervals", "peakAmplitude"],
                },
            ],
            "exact_files_options": {
                "standard": [
                    "alf/wheel.position.npy",
                    "alf/wheel.timestamps.npy",
                    "alf/wheelMoves.intervals.npy",
                    "alf/wheelMoves.peakAmplitude.npy",
                ],
            },
        }
```

### Format-Flexible Interface: BrainwideMapTrialsInterface

Supports two different file formats:

```python
class BrainwideMapTrialsInterface(BaseIBLDataInterface):
    REVISION: str | None = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        return {
            "exact_files_options": {
                "bwm_format": ["alf/trials.table.pqt"],
                "legacy_format": [
                    "alf/trials.intervals.npy",
                    "alf/trials.choice.npy",
                    "alf/trials.feedbackType.npy",
                    "alf/trials.contrastLeft.npy",
                    "alf/trials.contrastRight.npy",
                    "alf/trials.probabilityLeft.npy",
                    "alf/trials.feedback_times.npy",
                    "alf/trials.response_times.npy",
                    "alf/trials.stimOn_times.npy",
                    "alf/trials.goCue_times.npy",
                    "alf/trials.firstMovement_times.npy",
                ],
            },
        }
```

### Parameterized Interface: IblPoseEstimationInterface

Takes parameters that affect file paths:

```python
class IblPoseEstimationInterface(BaseIBLDataInterface):
    REVISION: str | None = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, camera_view: str, **kwargs) -> dict:
        return {
            "exact_files_options": {
                "standard": [f"alf/_ibl_{camera_view}Camera.lightningPose.pqt"],
            },
        }

    @classmethod
    def check_availability(cls, one, eid, camera_view: str, **kwargs):
        # Can add additional checks (e.g., video QC) beyond file existence
        requirements = cls.get_data_requirements(camera_view=camera_view)
        # ... check files + QC status
```

### Wildcard Interface: IblSortingInterface

Handles variable probe names:

```python
class IblSortingInterface(BaseIBLDataInterface):
    REVISION: str | None = "2025-05-06"

    @classmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        return {
            "exact_files_options": {
                "standard": [
                    "alf/probe*/spikes.times.npy",
                    "alf/probe*/spikes.clusters.npy",
                    "alf/probe*/spikes.amps.npy",
                    "alf/probe*/spikes.depths.npy",
                    "alf/probe*/clusters.channels.npy",
                    "alf/probe*/clusters.depths.npy",
                    "alf/probe*/clusters.metrics.pqt",
                ],
            },
        }
```

## Integration with Conversion Pipeline

### In Download Scripts

```python
# Check availability first (cheap, no download)
interfaces_to_download = []
if LickInterface.check_availability(one, eid)["available"]:
    interfaces_to_download.append(LickInterface)
if WheelInterface.check_availability(one, eid)["available"]:
    interfaces_to_download.append(WheelInterface)

# Download only what's available
for interface_class in interfaces_to_download:
    interface_class.download_data(one=one, eid=eid)
```

### In Conversion Functions

```python
# Initialize only available interfaces
data_interfaces = []
for camera_name in ["left", "right", "body"]:
    if IblPoseEstimationInterface.check_availability(one, eid, camera_view=camera_name)["available"]:
        data_interfaces.append(
            IblPoseEstimationInterface(camera_name=camera_name, one=one, session=eid)
        )

# During conversion
for interface in data_interfaces:
    interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata)
```

## Design Considerations

### Why Separate `check_availability()` from `download_data()`?

1. **Cost**: Availability checking queries metadata only; downloading transfers large files
2. **Planning**: Converters can determine which interfaces to use before committing to downloads
3. **Reporting**: Can generate reports of what data exists without downloading everything

### Why Class Methods for Requirements?

`get_data_requirements()` and `check_availability()` are class methods because:

1. They don't require instance state
2. Can be called before instantiating the interface
3. Enables batch availability checking across many sessions

### Why Format Options Instead of Single Format?

IBL data evolved over time. Format options allow:

1. **Backward compatibility**: Support both old and new file formats
2. **Graceful migration**: New sessions use `bwm_format`, old sessions fall back to `legacy_format`
3. **Tracker flexibility**: Pose data can come from different trackers (Lightning Pose, DLC)

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System overview and component relationships
- [conversion_overview.md](conversion_overview.md) - How to run conversions
- [revisions.md](revisions.md) - Data versioning system
- [ONE API Data Access](../one_api_data_access/index.md) - Data loading patterns

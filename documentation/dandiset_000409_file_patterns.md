# DANDI 000409 File Pattern Analysis

**Generated:** 2025-12-09
**Dandiset:** [000409](https://dandiarchive.org/dandiset/000409)
**Total Files:** 1,597

## Summary

| Category | Count | Format |
|----------|-------|--------|
| **NEW format (uploaded)** | 8 NWB files | `desc-raw` / `desc-processed` |
| **OLD format (to be replaced)** | 680 NWB files | Various legacy patterns |
| **Videos** | 909 files | Mix of old and new naming |

---

## File Naming Conventions

### NEW Format (Current Standard)

The new format splits data into two separate NWB files per session:

| File Type | Pattern | Contents |
|-----------|---------|----------|
| **Raw** | `sub-{subject}_ses-{eid}_desc-raw_ecephys.nwb` | Raw electrophysiology data, raw videos |
| **Processed** | `sub-{subject}_ses-{eid}_desc-processed_behavior+ecephys.nwb` | Spike sorting, behavioral data, processed camera data |

**Video files (new format):**
- `sub-{subject}_ses-{eid}_ecephys+image/sub-{subject}_ses-{eid}_VideoLeftCamera.mp4`
- `sub-{subject}_ses-{eid}_ecephys+image/sub-{subject}_ses-{eid}_VideoRightCamera.mp4`
- `sub-{subject}_ses-{eid}_ecephys+image/sub-{subject}_ses-{eid}_VideoBodyCamera.mp4`

### OLD Format (Legacy - To Be Deleted)

| File Type | Pattern | Count | Notes |
|-----------|---------|-------|-------|
| Processed-only behavior | `*-processed-only_behavior.nwb` | 347 | Old processed files |
| behavior+ecephys+image | `*_behavior+ecephys+image.nwb` | 305 | Combined format |
| behavior+ecephys | `*_behavior+ecephys.nwb` | 25 | No video data |
| ecephys+image | `*_ecephys+image.nwb` | 3 | Raw format variant |
| raw-only ecephys+image | `*-raw-only_ecephys+image.nwb` | 1 | Legacy raw format |

**Video files (old format):**
- `*_OriginalVideoLeftCamera.mp4` (899 files) - will be replaced
- `*_external_file_0.mp4` (3 files) - very old format

---

## Upload Progress

### Sessions with NEW Format Only (2 sessions)

These sessions have been fully migrated to the new format:

| Subject | Session EID | Files |
|---------|-------------|-------|
| NYU-12 | `b182b754-3c3e-4942-8144-6ee790926b58` | desc-raw, desc-processed |
| NYU-12 | `4364a246-f8d7-4ce7-ba23-a098104b96e4` | desc-raw, desc-processed |

### Sessions with BOTH Formats (2 sessions)

These sessions have both old and new files (old should be deleted):

| Subject | Session EID | Old Files | New Files |
|---------|-------------|-----------|-----------|
| NYU-11 | `56956777-dca5-468c-87cb-78150432cc57` | behavior+ecephys+image | desc-raw, desc-processed |
| NYU-11 | `6713a4a7-faed-4df2-acab-ee4e63326f8d` | behavior+ecephys | desc-raw, desc-processed |

### Sessions with OLD Format Only (674 sessions)

These sessions still need to be converted to the new format.

---

## File Pattern Examples

### NEW Format Examples

```
sub-NYU-12/
    sub-NYU-12_ses-b182b754-3c3e-4942-8144-6ee790926b58_desc-raw_ecephys.nwb
    sub-NYU-12_ses-b182b754-3c3e-4942-8144-6ee790926b58_desc-processed_behavior+ecephys.nwb
    sub-NYU-12_ses-b182b754-3c3e-4942-8144-6ee790926b58_ecephys+image/
        sub-NYU-12_ses-b182b754-3c3e-4942-8144-6ee790926b58_VideoLeftCamera.mp4
        sub-NYU-12_ses-b182b754-3c3e-4942-8144-6ee790926b58_VideoRightCamera.mp4
```

### OLD Format Examples (to be deleted)

```
sub-CSH-ZAD-001/
    sub-CSH-ZAD-001_ses-3e7ae7c0-fe8b-487c-9354-036236fa1010-processed-only_behavior.nwb
    sub-CSH-ZAD-001_ses-3e7ae7c0-fe8b-487c-9354-036236fa1010_behavior+ecephys+image.nwb
    sub-CSH-ZAD-001_ses-3e7ae7c0-fe8b-487c-9354-036236fa1010_behavior+ecephys+image/
        sub-CSH-ZAD-001_ses-3e7ae7c0-fe8b-487c-9354-036236fa1010_OriginalVideoLeftCamera.mp4
```

---

## Statistics

| Metric | Value |
|--------|-------|
| Total unique sessions | 679 |
| Sessions fully migrated (new only) | 2 |
| Sessions partially migrated (both) | 2 |
| Sessions pending migration (old only) | 674 |
| **Migration progress** | **0.6%** |

---

## Actions Required

1. **Delete old files** for sessions that have new format uploads (2 sessions with both formats)
2. **Convert remaining 674 sessions** to new format
3. **Upload new format files** to replace old ones

---

## Utility Scripts

### Check for OLD format files

```python
"""List all OLD format files in dandiset 000409."""
from dandi.dandiapi import DandiAPIClient

client = DandiAPIClient()
dandiset = client.get_dandiset('000409')

old_patterns = [
    '-processed-only_behavior.nwb',
    '_behavior+ecephys+image.nwb',
    '_behavior+ecephys.nwb',
    '_ecephys+image.nwb',
    '-raw-only_ecephys+image.nwb',
    '_external_file_',
    '_OriginalVideo',
]

print("OLD FORMAT FILES:")
print("=" * 80)
for asset in dandiset.get_assets():
    if any(pattern in asset.path for pattern in old_patterns):
        print(asset.path)
```

### Check for NEW format files

```python
"""List all NEW format files in dandiset 000409."""
from dandi.dandiapi import DandiAPIClient

client = DandiAPIClient()
dandiset = client.get_dandiset('000409')

new_patterns = [
    'desc-raw_ecephys.nwb',
    'desc-processed_behavior+ecephys.nwb',
]

print("NEW FORMAT FILES:")
print("=" * 80)
for asset in dandiset.get_assets():
    if any(pattern in asset.path for pattern in new_patterns):
        print(asset.path)
```

### Check upload progress

```python
"""Show upload progress: sessions with new vs old format."""
from dandi.dandiapi import DandiAPIClient
from collections import defaultdict
import re

client = DandiAPIClient()
dandiset = client.get_dandiset('000409')

sessions = defaultdict(lambda: {'old': False, 'new': False})

for asset in dandiset.get_assets():
    if not asset.path.endswith('.nwb'):
        continue
    match = re.search(r'ses-([a-f0-9-]+)', asset.path)
    if match:
        sid = match.group(1)
        if 'desc-raw' in asset.path or 'desc-processed' in asset.path:
            sessions[sid]['new'] = True
        else:
            sessions[sid]['old'] = True

new_only = sum(1 for s in sessions.values() if s['new'] and not s['old'])
old_only = sum(1 for s in sessions.values() if s['old'] and not s['new'])
both = sum(1 for s in sessions.values() if s['new'] and s['old'])

print(f"Sessions with NEW format only: {new_only}")
print(f"Sessions with OLD format only: {old_only}")
print(f"Sessions with BOTH (need cleanup): {both}")
print(f"Migration progress: {new_only}/{len(sessions)} ({100*new_only/len(sessions):.1f}%)")
```

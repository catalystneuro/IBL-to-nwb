# BWM Conversion Tracking

Track DANDI upload status for Brain-Wide Map (BWM) session conversions.

## Quick Start

```bash
# Verify uploads (creates tracking.json automatically if needed)
python verify_tracking.py

# Check summary
python verify_tracking.py --summary

# Get incomplete session ranges for re-launch
python verify_tracking.py --incomplete-ranges
# Output: 3-4 28-30 45-47
```

**Terminology:** "Incomplete" = a session where at least one file (raw or processed) is missing from DANDI.

## Files

| File | Purpose |
|------|---------|
| `tracking.json` | Single source of truth for verification status (auto-created) |
| `bwm_session_eids.json` | Simple EID list for launch script (auto-created) |

## Usage

### verify_tracking.py

```bash
# Full verification (queries DANDI, updates tracking.json)
# Creates tracking.json from bwm_df.pqt if it doesn't exist
python verify_tracking.py

# Summary only (no DANDI query, reads tracking.json)
python verify_tracking.py --summary

# Get incomplete ranges (for launch script --range argument)
python verify_tracking.py --incomplete-ranges

# Get incomplete EIDs (one per line)
python verify_tracking.py --incomplete-eids
```

## Configuration

Edit the constants at the top of `verify_tracking.py`:

```python
DANDISET_ID = "000409"
DANDI_INSTANCE = "dandi"  # "dandi" for production, "dandi-sandbox" for testing
```

## Re-launching Incomplete Sessions

```bash
# Get incomplete ranges
RANGES=$(python verify_tracking.py --incomplete-ranges)
echo "Incomplete ranges: $RANGES"

# Launch each range
for range in $RANGES; do
    python ../launch_ec2_instances.py --profile ibl --range $range
done
```

## JSON Schema

### tracking.json

```json
{
  "metadata": {
    "created": "2026-02-02T10:00:00+00:00",
    "last_verified": "2026-02-02T14:30:00+00:00",
    "dandiset_id": "000409",
    "dandi_instance": "dandi",
    "source_fixture": "bwm_df.pqt"
  },
  "summary": {
    "total_sessions": 459,
    "complete": 46,
    "incomplete": 413,
    "raw_verified": 48,
    "processed_verified": 46
  },
  "sessions": [
    {
      "index": 0,
      "eid": "6713a4a7-faed-4df2-acab-ee4e63326f8d",
      "subject": "NYU-11",
      "subject_sanitized": "NYU-11",
      "raw_path": "sub-NYU-11/sub-NYU-11_ses-..._desc-raw_ecephys.nwb",
      "raw_verified": true,
      "processed_path": "sub-NYU-11/sub-NYU-11_ses-..._desc-processed_behavior+ecephys.nwb",
      "processed_verified": true
    }
  ]
}
```

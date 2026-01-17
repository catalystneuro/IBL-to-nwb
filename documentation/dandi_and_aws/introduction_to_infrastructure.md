# DANDI and AWS Infrastructure

This section documents the cloud infrastructure for uploading NWB files to the DANDI archive and running distributed conversions on AWS.

## Overview

IBL NWB files are published on the [DANDI archive](https://dandiarchive.org/) (Dandiset 000409). For the full Brain-Wide Map dataset (459 sessions), we use AWS EC2 instances for parallel conversion processing.

## Documents in This Section

- [AWS Infrastructure](aws_infrastructure.md) - Running distributed conversions on AWS EC2: instance setup, session management, cost estimation, and monitoring
- [DANDI File Patterns](dandi_file_patterns.md) - File naming conventions and directory structure for DANDI uploads

## Key Workflows

### Single Session Conversion (Local)

For testing or small-scale work:
```python
from ibl_to_nwb.conversion import convert_processed_session
nwbfile_path = convert_processed_session(eid, one, stub_test=False)
```

### Full Dataset Conversion (AWS)

For the complete BWM dataset:
1. Launch EC2 instances (one per session)
2. Each instance converts one session and uploads to S3
3. After all complete, validate and upload to DANDI

**Cost estimate**: ~$600 for 459 sessions (~$0.42/hour per instance, 2-4 hours per session)

### DANDI Upload

```bash
# Validate NWB files
dandi validate .

# Upload to DANDI (requires API key)
dandi upload
```

## Related Sections

- [NWB Conversion](../conversion/introduction_to_conversion.md) - How conversions work
- [Conversion Overview](../conversion/conversion_overview.md) - Detailed pipeline stages

# EC2 Monitoring Architecture

## Overview

This document describes how EC2 instance logs are captured and stored during IBL NWB conversion jobs.

## How EC2 Console Output Works

```
EC2 Instance                              AWS Infrastructure                    Local Machine
─────────────────────────────────────     ──────────────────────────────────    ────────────────────────

cloud-init / boot.sh                      EC2 Hypervisor                        monitor.py
    │                                         │                                     │
    │ writes to stdout/stderr                 │                                     │
    └─────────────────────────────────────────►                                     │
                                              │                                     │
                                         Captures output                            │
                                         to ring buffer                             │
                                         (~64KB, ~24h retention)                    │
                                              │                                     │
                                              │◄────────────────────────────────────┤
                                              │   aws ec2 get-console-output        │
                                              │                                     │
                                              ├────────────────────────────────────►│
                                              │   returns console text              │
                                                                                    │
                                                                              Saves to local
                                                                              log files
```

### Key Points

| Aspect | Detail |
|--------|--------|
| Capture mechanism | AWS hypervisor captures VM serial console output |
| Buffer size | ~64KB ring buffer (older content gets overwritten) |
| Retention | ~24 hours after instance termination |
| Impact on instance | Zero - instance is unaware of log reads |
| Latency | 1-5 minute delay from output to availability |
| Access method | `aws ec2 get-console-output` API call |

## Log Storage Strategy

### Single File Per Instance (Incremental)

Each instance gets one log file that grows incrementally:

```
/media/heberto/Expansion/conversion_logs/ec2_runs/
├── ec2_console_{session_eid}_{index}_{instance_id}.log
```

Example:
```
ec2_console_8c025071-c4f3-426c-9aed-f149e8f75b7b_39_i-0f0ca195ece428609.log
```

### Incremental Append Logic

```python
# Track lines already saved per instance
_saved_line_counts: dict[str, int] = {}

def save_logs(instance_id, console_output):
    lines = console_output.splitlines()
    last_saved = _saved_line_counts.get(instance_id, 0)

    if len(lines) > last_saved:
        new_lines = lines[last_saved:]
        append_to_file(new_lines)
        _saved_line_counts[instance_id] = len(lines)
```

### Why This Approach?

| Concern | Solution |
|---------|----------|
| **Duplicate content** | Track line count, only append new lines |
| **Missed lines** | Poll frequently (~30-60s) before buffer rotates |
| **Searchability** | One file per instance, easy to grep |
| **Disk space** | No redundant snapshots |

## Monitoring Flow

### Automatic Start (Recommended)

```bash
# Launch instances - monitor starts automatically
uv run python launch_ec2_instances.py --profile ibl --range 0-10

# Monitor runs in background, saves logs to ~/ibl_scratch/conversion_logs/
# Auto-exits when all instances terminate
```

### Manual Start

```bash
# Start monitor manually
uv run python monitor.py --interval 60

# Or run once (no continuous monitoring)
uv run python monitor.py --once
```

### Disable Automatic Monitoring

```bash
uv run python launch_ec2_instances.py --profile ibl --range 0-10 --no-monitor
```

## Log File Format

```
# EC2 Console Output
# Instance ID: i-0f0ca195ece428609
# Session EID: 8c025071-c4f3-426c-9aed-f149e8f75b7b
# Session Index: 39
# Instance Name: ibl-conversion-NYU-65_2022-09-15_001
# Started: 2026-02-03T19:18:11+00:00
#================================================================================

[    0.000000] Linux version 5.15.0-1052-aws ...
...
=== PHASE: ebs_setup | START | 2026-02-03T19:20:00+00:00 ===
...
=== PHASE: conversion | END | 2026-02-03T21:30:00+00:00 | duration_seconds=7200 ===
...
=== RESULT: SUCCESS | eid=8c025071-... | total_minutes=360 ===
```

## Extracting Timing Data

The logs contain machine-parseable markers for analysis:

```bash
# Get all phase timings
grep "PHASE:.*duration_seconds" logfile.log

# Get final result
grep "RESULT:" logfile.log

# Get instance metadata
grep "INSTANCE_METADATA" -A 15 logfile.log

# Get file sizes before upload
grep "FILE_INVENTORY" -A 5 logfile.log
```

## Limitations

1. **64KB buffer**: Long-running jobs may lose early output if not polled frequently
2. **1-5 min delay**: Not real-time; output appears with slight delay
3. **No stderr separation**: stdout and stderr are interleaved
4. **Cloud-init wrapper**: Output is wrapped in cloud-init log format with timestamps

## Troubleshooting

### Logs Not Appearing

1. Check instance is running: `aws ec2 describe-instances --instance-ids i-xxx`
2. Wait 2-3 minutes for cloud-init to start
3. Check monitor is running: `ps aux | grep monitor.py`

### Missing Early Output

Buffer may have rotated. Solutions:
- Reduce poll interval: `--monitor-interval 30`
- Check if output is in older snapshot files (if using legacy mode)

### Monitor Not Auto-Exiting

Monitor exits after 3 consecutive polls with no instances. If instances are stuck:
- Check AWS console for instance state
- Manually terminate: `aws ec2 terminate-instances --instance-ids i-xxx`

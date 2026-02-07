#!/usr/bin/env python3
"""Monitor IBL conversion instances in real-time."""

import atexit
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# PID file location (shared with launch_ec2_instances.py)
MONITOR_PID_FILE = Path("/tmp/ibl_conversion_monitor.pid")


def cleanup_pid_file():
    """Remove PID file on exit if it belongs to this process."""
    if MONITOR_PID_FILE.exists():
        try:
            stored_pid = int(MONITOR_PID_FILE.read_text().strip())
            if stored_pid == os.getpid():
                MONITOR_PID_FILE.unlink()
        except (ValueError, OSError):
            pass


# Register cleanup to run on normal exit
atexit.register(cleanup_pid_file)


def run_aws_command(cmd):
    """Run AWS CLI command and return output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return None


def get_instances():
    """Get all running IBL conversion instances."""
    cmd = [
        "aws",
        "ec2",
        "describe-instances",
        "--region",
        "us-east-2",
        "--filters",
        "Name=tag:Project,Values=IBL-NWB-Conversion",
        "Name=instance-state-name,Values=running,pending",
        "--query",
        "Reservations[*].Instances[*].[InstanceId,State.Name,Tags[?Key==`SessionEID`].Value|[0],Tags[?Key==`SessionIndex`].Value|[0],Tags[?Key==`StubTest`].Value|[0],LaunchTime,Tags[?Key==`Name`].Value|[0]]",
        "--output",
        "json",
    ]

    output = run_aws_command(cmd)
    if not output:
        return []

    # Flatten nested list structure
    instances = []
    for reservation in json.loads(output):
        for instance in reservation:
            instances.append(
                {
                    "id": instance[0],
                    "state": instance[1],
                    "session_eid": instance[2],
                    "session_index": instance[3],
                    "stub_test": instance[4],
                    "launch_time": instance[5],
                    "name": instance[6],
                }
            )

    return instances


def get_console_output(instance_id, lines=50):
    """Get console output for an instance."""
    cmd = [
        "aws",
        "ec2",
        "get-console-output",
        "--region",
        "us-east-2",
        "--instance-id",
        instance_id,
        "--latest",
        "--output",
        "text",
    ]

    output = run_aws_command(cmd)
    if not output:
        return "[No console output available yet]"

    # Return last N lines
    lines_list = output.strip().split("\n")
    return "\n".join(lines_list[-lines:])


def extract_progress_info(console_output):
    """Extract key progress indicators from console output."""
    info = {"status": "Booting", "stage": "", "errors": [], "real_errors": []}

    lines = console_output.split("\n")

    for i, line in enumerate(lines):
        # Check for key stages
        if "Stub test mode: true" in line:
            info["stub_test_confirmed"] = True
        elif "Stub test mode: false" in line:
            info["stub_test_confirmed"] = False
        elif "Found existing filesystem" in line or "Formatting..." in line:
            info["stage"] = "EBS mounted"
            info["status"] = "Running"
        elif "Installing system dependencies" in line:
            info["stage"] = "Installing packages"
            info["status"] = "Running"
        elif "Cloning IBL-to-nwb repository" in line:
            info["stage"] = "Cloning repo"
            info["status"] = "Running"
        elif "Setting up Python environment" in line:
            info["stage"] = "Setting up Python"
            info["status"] = "Running"
        elif "Starting conversion process" in line:
            info["stage"] = "Starting conversion"
            info["status"] = "Converting"
        elif "CONVERTING RAW EPHYS" in line:
            info["stage"] = "Converting RAW ephys"
            info["status"] = "Converting"
        elif "CONVERTING PROCESSED DATA" in line:
            info["stage"] = "Converting PROCESSED data"
            info["status"] = "Converting"
        elif "Decompressing" in line:
            info["stage"] = "Decompressing ephys data"
            info["status"] = "Converting"
        elif "Chunk size:" in line:
            info["stage"] = "Writing NWB (chunking data)"
            info["status"] = "Converting"
        elif "Writing ElectricalSeries" in line or "Adding" in line and "to NWB" in line:
            info["stage"] = "Writing NWB data"
            info["status"] = "Converting"
        elif "PROCESSING SESSION" in line:
            # Extract session number
            parts = line.split("PROCESSING SESSION")
            if len(parts) > 1:
                info["stage"] = "Converting: " + parts[1].split(":")[0].strip()
            info["status"] = "Converting"
        elif "Running in STUB TEST mode" in line:
            info["mode"] = "STUB TEST"
            info["status"] = "Converting"
        elif "Running in PRODUCTION mode" in line:
            info["mode"] = "PRODUCTION"
            info["status"] = "Converting"
        elif "Downloading dandiset.yaml" in line:
            info["stage"] = "Preparing DANDI upload"
            info["status"] = "Uploading"
        elif "Uploading to DANDI" in line:
            info["stage"] = "Uploading to DANDI"
            info["status"] = "Uploading"
        elif "dandi upload" in line:
            info["stage"] = "DANDI upload in progress"
            info["status"] = "Uploading"
        elif "Upload complete" in line:
            info["stage"] = "Upload complete"
            info["status"] = "Finishing"
        elif "Upload successful" in line:
            info["stage"] = "Upload successful"
            info["status"] = "Finishing"
        elif "Shutting down" in line:
            info["status"] = "Shutting down"

        # Check for errors - look before cc_scripts warning to find real issue
        if "ERROR:" in line or "FAILED" in line or "Failed to" in line:
            info["errors"].append(line.strip())

        # Special handling for cc_scripts error - find the actual error before it
        if "cc_scripts_user.py[WARNING]" in line:
            # Look back up to 10 lines to find the real error
            for j in range(max(0, i - 10), i):
                prev_line = lines[j]
                if any(err in prev_line for err in [
                    "apparently in use",
                    "Could not read from remote",
                    "fatal:",
                    "Unable to locate package",
                    "No such file",
                    "Permission denied",
                    "Connection refused",
                ]):
                    info["real_errors"].append(prev_line.strip())
                    break

    return info


def clear_screen():
    """Clear the terminal screen."""
    print("\033[2J\033[H", end="")


# Track last few lines saved per instance (for overlap detection with ring buffer)
_ANCHOR_LINE_COUNT = 10
_instance_anchor_lines: dict[str, list[str]] = {}
# Track timestamp assigned to each instance's log file (set once on first poll)
_instance_log_timestamps: dict[str, str] = {}
# Track all instances we've ever seen (for final-poll on disappearance)
_known_instances: dict[str, dict] = {}
# Instances that already got their final poll
_final_polled: set[str] = set()


def save_console_logs(instances: list, logs_dir: Path) -> None:
    """Save console output incrementally for each instance.

    The EC2 console output API returns a ~64KB ring buffer. When output exceeds
    this, old content is evicted. This function handles the ring buffer by
    tracking the last few lines written ("anchor lines") and finding where they
    appear in the new buffer to determine what's truly new.

    If the anchor lines are not found (complete buffer rollover), all new content
    is appended with a gap marker.

    Args:
        instances: List of instance dicts with 'id', 'session_eid', etc.
        logs_dir: Directory to save log files to.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)

    for inst in instances:
        instance_id = inst["id"]
        session_eid = inst.get("session_eid") or "unknown"
        session_index = inst.get("session_index") or "unknown"

        # Get full console output
        console = get_console_output(instance_id, lines=10000)

        if not console or console == "[No console output available yet]":
            continue

        # Filename starts with datetime for easy sorting (timestamp set once per instance)
        if instance_id not in _instance_log_timestamps:
            _instance_log_timestamps[instance_id] = datetime.now().strftime("%Y%m%d_%H%M%S")
        ts = _instance_log_timestamps[instance_id]
        filename = f"{ts}_ec2_console_{session_eid}_{session_index}_{instance_id}.log"
        log_file = logs_dir / filename

        # Split into lines
        lines = console.splitlines(keepends=True)
        if not lines:
            continue

        # Write header on first write
        if not log_file.exists():
            with open(log_file, "w") as f:
                f.write(f"# EC2 Console Output\n")
                f.write(f"# Instance ID: {instance_id}\n")
                f.write(f"# Session EID: {session_eid}\n")
                f.write(f"# Session Index: {session_index}\n")
                f.write(f"# Instance Name: {inst.get('name', 'N/A')}\n")
                f.write(f"# Stub Test: {inst.get('stub_test', 'N/A')}\n")
                f.write(f"# Started: {datetime.now().isoformat()}\n")
                f.write("#" + "=" * 79 + "\n\n")

        anchor = _instance_anchor_lines.get(instance_id)

        if anchor is None:
            # First poll -- write everything
            new_lines = lines
        else:
            # Find where our anchor lines appear in the new buffer
            anchor_len = len(anchor)
            found_at = None
            for line_index in range(len(lines) - anchor_len + 1):
                if lines[line_index:line_index + anchor_len] == anchor:
                    found_at = line_index + anchor_len
                    break

            if found_at is not None:
                # Overlap found -- append only what comes after
                new_lines = lines[found_at:]
            else:
                # Complete rollover -- anchor lines were evicted from the buffer.
                # Append all content with a gap marker.
                new_lines = [f"\n# --- GAP: buffer rolled over, some output lost ({datetime.now().isoformat()}) ---\n\n"]
                new_lines.extend(lines)

        if new_lines:
            with open(log_file, "a") as f:
                f.writelines(new_lines)
            print(f"  Appended {len(new_lines)} lines to: {filename}")
        else:
            print(f"  No new output for: {filename}")

        # Update anchor to last N lines of current buffer
        _instance_anchor_lines[instance_id] = lines[-_ANCHOR_LINE_COUNT:]


if platform.system() == "Darwin":  # macOS
    DEFAULT_LOGS_DIR = Path("/Volumes/Expansion/conversion_logs/ec2_runs")
else:  # Linux
    DEFAULT_LOGS_DIR = Path("/media/heberto/Expansion/conversion_logs/ec2_runs")


def monitor_instances(interval=30, continuous=True, show_logs=0, save_logs=False, logs_dir=None, auto_exit=True):
    """Monitor instances and display status.

    Parameters
    ----------
    interval : int, optional
        Refresh interval in seconds. Default is 30.
    continuous : bool, optional
        If True, keep refreshing; if False, run once. Default is True.
    show_logs : int, optional
        Number of recent log lines to show per instance. Default is 0 (none).
    save_logs : bool, optional
        If True, save console logs to disk on each refresh. Default is False.
        Use --save-logs flag to enable when running manually.
    logs_dir : Path or str, optional
        Directory to save log files. Default is '~/ibl_scratch/conversion_logs'.
    auto_exit : bool, optional
        If True, exit after 3 consecutive polls with no instances. Default is True.
    """
    if save_logs:
        logs_dir = Path(logs_dir) if logs_dir else DEFAULT_LOGS_DIR
    else:
        logs_dir = None

    # Track consecutive empty polls for auto-exit
    empty_poll_count = 0
    MAX_EMPTY_POLLS = 3

    try:
        while True:
            clear_screen()

            print("=" * 80)
            print(f"IBL Conversion Instance Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            print()

            instances = get_instances()

            if not instances:
                empty_poll_count += 1
                print("No running instances found.")

                # Final poll for any instances that just disappeared
                if logs_dir:
                    disappeared = [
                        inst for iid, inst in _known_instances.items()
                        if iid not in _final_polled
                    ]
                    if disappeared:
                        print(f"  Final poll for {len(disappeared)} terminated instance(s)...")
                        save_console_logs(disappeared, logs_dir)
                        _final_polled.update(inst["id"] for inst in disappeared)

                print()

                if auto_exit and empty_poll_count >= MAX_EMPTY_POLLS:
                    print(f"No instances for {MAX_EMPTY_POLLS} consecutive polls. Auto-exiting.")
                    break

                print(f"Empty polls: {empty_poll_count}/{MAX_EMPTY_POLLS} (will auto-exit at {MAX_EMPTY_POLLS})")
                print("Press Ctrl+C to exit earlier")

                if not continuous:
                    break
                time.sleep(interval)
                continue

            # Reset empty poll counter when instances are found
            empty_poll_count = 0

            print(f"Found {len(instances)} instances:")
            print()

            for inst in instances:
                # Show instance name (e.g., "ibl-conversion-NYU-11_2020-02-18_001") or fallback to ID
                name = inst.get('name') or inst['id']
                session_info = f"Session #{inst.get('session_index', '?')}" if inst.get('session_index') else ""
                print(f"{name} ({session_info}) - {inst['id']}")
                print(f"  State: {inst['state']}")
                print(f"  Stub Test: {inst['stub_test']}")

                # Get progress info
                console = get_console_output(inst["id"], lines=100)
                progress = extract_progress_info(console)

                print(f"  Status: {progress.get('status', 'Running')}")
                if progress.get("stage"):
                    print(f"  Stage: {progress['stage']}")
                if progress.get("mode"):
                    print(f"  Mode: {progress['mode']}")

                # Show real errors first (these are the actual issues)
                if progress.get("real_errors"):
                    print(f"  [ERROR]:")
                    for error in progress["real_errors"]:
                        # Clean up cloud-init prefix and show more characters
                        clean_error = error.split("cloud-init[")[-1] if "cloud-init[" in error else error
                        print(f"    {clean_error[:100]}")

                # Show other errors
                if progress.get("errors"):
                    print(f"  [WARN] Other warnings: {len(progress['errors'])}")
                    for error in progress["errors"][-2:]:  # Show last 2
                        print(f"    - {error[:80]}")

                # Show recent log lines if requested
                if show_logs > 0:
                    print(f"  Recent logs ({show_logs} lines):")
                    print("  " + "-" * 60)
                    log_lines = console.strip().split("\n")[-show_logs:]
                    for line in log_lines:
                        # Truncate long lines and indent
                        truncated = line[:100] + "..." if len(line) > 100 else line
                        print(f"    {truncated}")
                    print("  " + "-" * 60)

                print()

            # Save logs if enabled
            if logs_dir:
                print()
                print(f"Saving logs to: {logs_dir}")
                save_console_logs(instances, logs_dir)

                # Final poll: capture logs for instances that disappeared since last poll.
                # EC2 keeps console output briefly after termination, so we can still
                # grab the RESULT line that would otherwise be lost.
                running_ids = {inst["id"] for inst in instances}
                _known_instances.update({inst["id"]: inst for inst in instances})
                disappeared = [
                    inst for iid, inst in _known_instances.items()
                    if iid not in running_ids and iid not in _final_polled
                ]
                if disappeared:
                    print(f"  Final poll for {len(disappeared)} terminated instance(s)...")
                    save_console_logs(disappeared, logs_dir)
                    _final_polled.update(inst["id"] for inst in disappeared)

            print("-" * 80)
            print(f"Refreshing every {interval} seconds... (Press Ctrl+C to exit)")
            print()

            # Show quick stats
            stub_count = sum(1 for i in instances if i["stub_test"] == "true")
            prod_count = len(instances) - stub_count
            print(f"Summary: {stub_count} stub test, {prod_count} production")

            if not continuous:
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monitor IBL conversion EC2 instances")
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=30,
        help="Refresh interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--once", action="store_true", help="Run once and exit (don't refresh continuously)"
    )
    parser.add_argument(
        "--logs",
        "-l",
        type=str,
        metavar="INSTANCE_ID",
        help="Show full console logs for a specific instance ID",
    )
    parser.add_argument(
        "--lines",
        "-n",
        type=int,
        default=200,
        help="Number of log lines to show (default: 200)",
    )
    parser.add_argument(
        "--show-logs",
        "-s",
        type=int,
        default=0,
        metavar="N",
        help="Show last N log lines for each instance in overview (default: 0, meaning off)",
    )
    parser.add_argument(
        "--save-logs",
        action="store_true",
        help="Save console logs to disk (default: display only, no saving)",
    )
    parser.add_argument(
        "--logs-dir",
        type=str,
        metavar="DIR",
        help=f"Directory to save console logs (default: {DEFAULT_LOGS_DIR})",
    )
    parser.add_argument(
        "--no-auto-exit",
        action="store_true",
        help="Disable auto-exit when no instances are found (keep running indefinitely)",
    )

    args = parser.parse_args()

    # If --logs is specified, show logs and exit
    if args.logs:
        console = get_console_output(args.logs, lines=args.lines)
        if console and console != "[No console output available yet]":
            print(f"Console output for {args.logs} (last {args.lines} lines):")
            print("=" * 80)
            print(console)
        else:
            print(f"No console output available for {args.logs}")
        sys.exit(0)

    monitor_instances(
        interval=args.interval,
        continuous=not args.once,
        show_logs=args.show_logs,
        save_logs=args.save_logs,
        logs_dir=args.logs_dir,
        auto_exit=not args.no_auto_exit,
    )

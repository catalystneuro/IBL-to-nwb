#!/usr/bin/env python3
"""Monitor IBL conversion instances in real-time."""

import json
import subprocess
import sys
import time
from datetime import datetime


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
        "Reservations[*].Instances[*].[InstanceId,State.Name,Tags[?Key==`ShardId`].Value|[0],Tags[?Key==`ShardRange`].Value|[0],Tags[?Key==`StubTest`].Value|[0],LaunchTime]",
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
                    "shard": instance[2],
                    "range": instance[3],
                    "stub_test": instance[4],
                    "launch_time": instance[5],
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
    info = {"status": "Booting", "stage": "", "errors": []}

    lines = console_output.split("\n")

    for line in lines:
        # Check for key stages
        if "Stub test mode: true" in line:
            info["stub_test_confirmed"] = True
        elif "Stub test mode: false" in line:
            info["stub_test_confirmed"] = False
        elif "Found existing filesystem" in line or "Formatting..." in line:
            info["stage"] = "EBS mounted"
        elif "Installing system dependencies" in line:
            info["stage"] = "Installing packages"
        elif "Cloning IBL-to-nwb repository" in line:
            info["stage"] = "Cloning repo"
        elif "Setting up Python environment" in line:
            info["stage"] = "Setting up Python"
        elif "Starting conversion process" in line:
            info["stage"] = "Starting conversion"
        elif "PROCESSING SESSION" in line:
            # Extract session number
            parts = line.split("PROCESSING SESSION")
            if len(parts) > 1:
                info["stage"] = "Converting: " + parts[1].split(":")[0].strip()
        elif "Running in STUB TEST mode" in line:
            info["mode"] = "STUB TEST"
        elif "Running in PRODUCTION mode" in line:
            info["mode"] = "PRODUCTION"
        elif "Upload successful" in line:
            info["stage"] = "Upload successful"
        elif "Shutting down" in line:
            info["status"] = "Shutting down"

        # Check for errors
        if "ERROR:" in line or "FAILED" in line or "Failed to" in line:
            info["errors"].append(line.strip())

    return info


def clear_screen():
    """Clear the terminal screen."""
    print("\033[2J\033[H", end="")


def monitor_instances(interval=30, continuous=True):
    """Monitor instances and display status."""
    try:
        while True:
            clear_screen()

            print("=" * 80)
            print(f"IBL Conversion Instance Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            print()

            instances = get_instances()

            if not instances:
                print("No running instances found.")
                print()
                print("Press Ctrl+C to exit")
                if not continuous:
                    break
                time.sleep(interval)
                continue

            print(f"Found {len(instances)} instances:")
            print()

            for inst in instances:
                print(f"Shard {inst['shard']} (Range: {inst['range']}) - {inst['id']}")
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
                if progress.get("errors"):
                    print(f"  ⚠️  Errors: {len(progress['errors'])}")
                    for error in progress["errors"][-3:]:  # Show last 3 errors
                        print(f"    - {error[:70]}")

                print()

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

    args = parser.parse_args()

    monitor_instances(interval=args.interval, continuous=not args.once)

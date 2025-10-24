#!/usr/bin/env python3
"""Simple real-time log tail viewer for all IBL conversion instances."""

import json
import subprocess
import sys
import time
from datetime import datetime


def get_instances():
    """Get all running IBL conversion instances."""
    cmd = [
        "aws", "ec2", "describe-instances",
        "--region", "us-east-2",
        "--filters",
        "Name=tag:Project,Values=IBL-NWB-Conversion",
        "Name=instance-state-name,Values=running,pending",
        "--query",
        "Reservations[*].Instances[*].[InstanceId,Tags[?Key==`ShardId`].Value|[0],Tags[?Key==`ShardRange`].Value|[0]]",
        "--output", "json",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        instances = []
        for reservation in json.loads(result.stdout):
            for instance in reservation:
                instances.append({
                    "id": instance[0],
                    "shard": instance[1],
                    "range": instance[2],
                })
        return instances
    except Exception as e:
        print(f"Error getting instances: {e}", file=sys.stderr)
        return []


def get_console_output(instance_id, num_lines=10):
    """Get last N lines of console output for an instance."""
    cmd = [
        "aws", "ec2", "get-console-output",
        "--region", "us-east-2",
        "--instance-id", instance_id,
        "--output", "text",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        # Return last N non-empty lines
        relevant_lines = [l for l in lines if l.strip()]
        return relevant_lines[-num_lines:] if len(relevant_lines) > num_lines else relevant_lines
    except Exception:
        return ["(no output yet)"]


def main():
    """Main loop to display logs."""
    import argparse
    parser = argparse.ArgumentParser(description="Tail logs from all IBL conversion instances")
    parser.add_argument("-n", "--lines", type=int, default=5, help="Number of lines to show per instance (default: 5)")
    parser.add_argument("-i", "--interval", type=int, default=5, help="Refresh interval in seconds (default: 5)")
    args = parser.parse_args()

    try:
        while True:
            # Clear screen
            print("\033[2J\033[H", end="")

            print("=" * 100)
            print(f"IBL Instance Logs - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Showing last {args.lines} lines | Refreshing every {args.interval}s | Press Ctrl+C to exit")
            print("=" * 100)
            print()

            instances = get_instances()

            if not instances:
                print("No running instances found.")
                print()
            else:
                for inst in instances:
                    print(f"▶ Shard {inst['shard']} (Range: {inst['range']}) - {inst['id']}")
                    print("─" * 100)

                    logs = get_console_output(inst['id'], args.lines)
                    for line in logs:
                        # Strip cloud-init timestamps for cleaner output
                        if '] cloud-init[' in line:
                            # Extract just the message after cloud-init prefix
                            parts = line.split('] cloud-init[', 1)
                            if len(parts) == 2:
                                msg = parts[1].split(']: ', 1)
                                if len(msg) == 2:
                                    line = msg[1]
                        print(f"  {line}")
                    print()

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n\nStopped monitoring.")
        sys.exit(0)


if __name__ == "__main__":
    main()

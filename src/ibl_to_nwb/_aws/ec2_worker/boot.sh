#!/bin/bash
# EC2 user-data script for IBL NWB conversion. See README for details.
set -euxo pipefail

# Timing helper functions for machine-parseable logs
SCRIPT_START_TIME=$(date +%s)

log_phase_start() {
    local phase="$1"
    echo "=== PHASE: ${phase} | START | $(date -Iseconds) ==="
}

log_phase_end() {
    local phase="$1"
    local start_time="$2"
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    echo "=== PHASE: ${phase} | END | $(date -Iseconds) | duration_seconds=${duration} ==="
}

log_disk_usage() {
    local label="$1"
    echo "=== DISK: ${label} ==="
    df -h /ebs 2>/dev/null || df -h /
    echo "=== END DISK ==="
}

# Dead man's switch: EXIT trap ALWAYS shuts down the instance, no matter how the script exits.
# SCRIPT_RESULT starts as FAILED and is only set to SUCCESS at the very end.
# This guarantees no zombie instances from: exit calls, set -e aborts, signals, or forgotten code paths.
SCRIPT_RESULT="FAILED"

cleanup_and_shutdown() {
    local end_time=$(date +%s)
    local duration=$((end_time - SCRIPT_START_TIME))

    if [ "$SCRIPT_RESULT" != "SUCCESS" ]; then
        echo "=== RESULT: FAILED | eid=${SESSION_EID:-unknown} | duration_seconds=${duration} ==="
        echo "ERROR: Script exiting without success. Shutting down in 180 seconds..."
    else
        echo "Shutting down in 180 seconds..."
    fi
    # Sleep long enough for monitor.py to capture console output (polls every 30s).
    # EC2 Nitro instances lose console output immediately after termination,
    # so the RESULT line must be captured while the instance is still running.
    sleep 180
    shutdown -h now
}

trap cleanup_and_shutdown EXIT

# Configuration variables (substituted by launch script)
MOUNT_POINT="/ebs"
REPO_URL="{{REPO_URL}}"
REPO_BRANCH="{{REPO_BRANCH}}"
DANDISET_ID="{{DANDISET_ID}}"
DANDI_INSTANCE="{{DANDI_INSTANCE}}"
CONVERSION_MODE="{{CONVERSION_MODE}}"  # Empty string, "--raw-only", or "--processed-only"
VERBOSE="{{VERBOSE}}"
DISPLAY_PROGRESS_BAR="{{DISPLAY_PROGRESS_BAR}}"

# Fetch instance metadata (IMDSv2 - requires token)
IMDS_TOKEN="$(curl -X PUT -fsS "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")"

INSTANCE_ID="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/instance-id)"
REGION="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/placement/region)"

# Get the SessionEID and SessionIndex tags from instance metadata (no AWS CLI/IAM role needed!)
SESSION_EID="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/tags/instance/SessionEID)"
SESSION_INDEX="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/tags/instance/SessionIndex)"
STUB_TEST="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/tags/instance/StubTest)"

if [[ -z "${SESSION_EID}" || "${SESSION_EID}" == "None" ]]; then
    echo "ERROR: Missing SessionEID tag on instance ${INSTANCE_ID}" >&2
    exit 1
fi

echo "Instance ${INSTANCE_ID} processing session ${SESSION_EID} (index ${SESSION_INDEX})"
echo "Stub test mode: ${STUB_TEST}"

# Log instance metadata for debugging
INSTANCE_TYPE="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/instance-type)" || INSTANCE_TYPE="unknown"

echo ""
echo "=== INSTANCE_METADATA: START ==="
echo "instance_id=${INSTANCE_ID}"
echo "instance_type=${INSTANCE_TYPE}"
echo "region=${REGION}"
echo "session_eid=${SESSION_EID}"
echo "session_index=${SESSION_INDEX}"
echo "stub_test=${STUB_TEST}"
echo "repo_url=${REPO_URL}"
echo "repo_branch=${REPO_BRANCH}"
echo "dandi_instance=${DANDI_INSTANCE}"
echo "dandiset_id=${DANDISET_ID}"
echo "conversion_mode=${CONVERSION_MODE:-both}"
echo "start_time=$(date -Iseconds)"
echo "=== INSTANCE_METADATA: END ==="
echo ""

# Setup EBS volume with bulletproof device detection
log_phase_start "ebs_setup"
EBS_SETUP_START=$(date +%s)
echo "Setting up EBS volume at ${MOUNT_POINT}..."

# Strategy: Find the EBS volume by size (100GB for stub test, 700GB for production)
# This is more reliable than device naming which can vary
echo "Detecting EBS volume by characteristics..."

# Get root device to exclude it
ROOT_DEVICE=$(findmnt -n -o SOURCE / | sed 's|/dev/||;s|p\?[0-9]*$||')
echo "Root device: ${ROOT_DEVICE}"

# List all block devices with size in GB (excluding root device)
echo "Available block devices:"
lsblk -ndo NAME,SIZE,TYPE | awk '$3=="disk"{print $1, $2}'

# Find the largest non-root disk (our EBS volume)
# EBS volume is either 100GB (stub test) or 700GB (production), always larger than 50GB root
DEVICE=$(lsblk -ndo NAME,SIZE,TYPE | \
    awk '$3=="disk"{print $1, $2}' | \
    grep -v "^${ROOT_DEVICE}" | \
    awk '{
        # Convert size to GB (handle G, T suffixes)
        size = $2;
        if (size ~ /T$/) { gsub(/T/, "", size); size = size * 1024; }
        else if (size ~ /G$/) { gsub(/G/, "", size); }
        else if (size ~ /M$/) { gsub(/M/, "", size); size = size / 1024; }

        # Force numeric conversion by adding 0
        size = size + 0;

        # Only consider disks >= 90GB (our EBS volumes are 100GB or 700GB)
        if (size >= 90) print $1, size;
    }' | \
    sort -k2 -nr | \
    head -1 | \
    awk '{print $1}')

if [[ -z "${DEVICE}" ]]; then
    echo "ERROR: No EBS volume found (looking for disk >= 90GB)"
    echo "This should not happen - EBS volume was specified in launch config"
    exit 1
fi

DEVICE_PATH="/dev/${DEVICE}"
echo "Selected EBS volume: ${DEVICE_PATH}"

# Verify this is NOT the root device (safety check)
if [[ "${DEVICE}" == "${ROOT_DEVICE}" ]]; then
    echo "ERROR: Selected device ${DEVICE} is the root device! Aborting."
    exit 1
fi

# Check if device is already mounted
if mount | grep -q "^${DEVICE_PATH}"; then
    echo "ERROR: ${DEVICE_PATH} is already mounted. Aborting."
    exit 1
fi

# Check if device has a filesystem (not just partition table metadata)
if ! blkid -s TYPE "${DEVICE_PATH}" | grep -q 'TYPE='; then
    echo "No filesystem found on ${DEVICE_PATH}. Formatting..."
    mkfs.ext4 -F "${DEVICE_PATH}"
else
    echo "Found existing filesystem on ${DEVICE_PATH}"
fi

mkdir -p "${MOUNT_POINT}"
mount "${DEVICE_PATH}" "${MOUNT_POINT}"

# Verify mount succeeded
if ! mountpoint -q "${MOUNT_POINT}"; then
    echo "ERROR: Failed to mount ${DEVICE_PATH} to ${MOUNT_POINT}"
    exit 1
fi

echo "Successfully mounted ${DEVICE_PATH} to ${MOUNT_POINT}"
df -h "${MOUNT_POINT}"

# Add to fstab for persistence across reboots (though we auto-terminate)
if ! grep -q "${MOUNT_POINT}" /etc/fstab; then
    UUID=$(blkid -s UUID -o value "${DEVICE_PATH}")
    echo "UUID=${UUID} ${MOUNT_POINT} ext4 defaults,nofail 0 2" >> /etc/fstab
fi

chmod 777 "${MOUNT_POINT}"
log_phase_end "ebs_setup" "${EBS_SETUP_START}"
log_disk_usage "after_ebs_mount"

# Install minimal system dependencies
log_phase_start "dependencies"
DEPS_START=$(date +%s)
# Note: uv handles all Python packages and downloads pre-built wheels
# No build tools needed since nothing is compiled!
echo "Installing system dependencies..."
apt-get update
apt-get install -y git curl ca-certificates

# Install uv
echo "Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.local/bin:${PATH}"  # uv installs to .local/bin
echo 'export PATH="/root/.local/bin:${PATH}"' >> /root/.bashrc
log_phase_end "dependencies" "${DEPS_START}"

# Clone repository
log_phase_start "clone_and_setup"
CLONE_START=$(date +%s)
echo "Cloning IBL-to-nwb repository..."
REPO_DIR="${MOUNT_POINT}/IBL-to-nwb"
git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${REPO_DIR}"

cd "${REPO_DIR}"

# Setup virtual environment with uv
echo "Setting up Python environment with uv..."
uv venv --seed  # Create venv with pip, setuptools, wheel
uv sync         # Install project dependencies from pyproject.toml

# Activate virtual environment
source .venv/bin/activate
log_phase_end "clone_and_setup" "${CLONE_START}"

# Setup DANDI API key from template substitution
# Disable command echoing to prevent key from appearing in cloud-init logs
set +x
# Export appropriate API key based on DANDI instance
# dandi-cli looks for DANDI_API_KEY (production) or DANDI_SANDBOX_API_KEY (sandbox)
if [[ "${DANDI_INSTANCE}" == "dandi" ]]; then
    DANDI_API_KEY="{{DANDI_API_KEY}}"
    export DANDI_API_KEY
else
    DANDI_SANDBOX_API_KEY="{{DANDI_API_KEY}}"
    export DANDI_SANDBOX_API_KEY
fi

# Shred the user-data file (contains the API key) after reading it
# This removes the on-disk copy that cloud-init caches
if [[ -f /var/lib/cloud/instance/user-data.txt ]]; then
    shred -u /var/lib/cloud/instance/user-data.txt 2>/dev/null || true
fi
set -x  # Re-enable command echoing for debugging


# Pass all configuration to Python orchestrator via environment variables
# The IBL_ prefix avoids collisions with system environment variables
echo "Instance will process single session: ${SESSION_EID} (index ${SESSION_INDEX})"
export IBL_SESSION_EID="${SESSION_EID}"
export IBL_SESSION_INDEX="${SESSION_INDEX}"
export IBL_STUB_TEST="${STUB_TEST}"
export IBL_INSTANCE_ID="${INSTANCE_ID}"
export IBL_INSTANCE_TYPE="${INSTANCE_TYPE}"
export IBL_REGION="${REGION}"
export IBL_DANDISET_ID="${DANDISET_ID}"
export IBL_DANDI_INSTANCE="${DANDI_INSTANCE}"
export IBL_CONVERSION_MODE="${CONVERSION_MODE}"
export IBL_VERBOSE="${VERBOSE}"
export IBL_DISPLAY_PROGRESS_BAR="${DISPLAY_PROGRESS_BAR}"
export IBL_MOUNT_POINT="${MOUNT_POINT}"

# Run Python orchestrator with bash-level safety net timeout
# The orchestrator handles: conversion, DANDI folder prep, DANDI upload, result reporting.
# Python handles per-phase timeouts (SIGALRM), but SIGALRM doesn't interrupt C extensions
# (HDF5, mtscomp). The bash timeout (SIGKILL) is the last-resort safety net.
# Total budget: conversion(6h) + upload(3h) + buffer(1h) = 10 hours
ORCHESTRATOR_TIMEOUT=36000

cd "${REPO_DIR}"
echo "Running: python -m ibl_to_nwb._aws.ec2_worker.orchestrate"

set +e
timeout --signal=KILL ${ORCHESTRATOR_TIMEOUT} python -m ibl_to_nwb._aws.ec2_worker.orchestrate
ORCHESTRATOR_EXIT_CODE=$?
set -e

if [ "$ORCHESTRATOR_EXIT_CODE" -ne 0 ]; then
    if [ "$ORCHESTRATOR_EXIT_CODE" -eq 137 ]; then
        # Exit code 137 = SIGKILL. Two possible causes:
        #   1. OOM killer (kernel ran out of memory)
        #   2. Safety-net timeout (bash timeout --signal=KILL)
        # Check dmesg for recent OOM events to distinguish them.
        if dmesg | tail -20 | grep -q "Out of memory"; then
            echo "=== RESULT: OOM_KILLED | eid=${SESSION_EID} | duration_seconds=$(($(date +%s) - SCRIPT_START_TIME)) ==="
            echo "ERROR: Process killed by Linux OOM killer (not enough RAM)."
            dmesg | grep "Out of memory" | tail -3
        else
            echo "=== RESULT: TIMEOUT | eid=${SESSION_EID} | phase=safety_net | timeout_seconds=${ORCHESTRATOR_TIMEOUT} ==="
            echo "ERROR: Orchestrator exceeded safety net timeout (${ORCHESTRATOR_TIMEOUT}s). Process was killed."
        fi
    fi
    # For all other exit codes, the Python orchestrator already printed its own RESULT marker
    exit 1  # EXIT trap handles shutdown
fi

# Only reached if orchestrator exited 0 (success)
SCRIPT_RESULT="SUCCESS"
# EXIT trap handles shutdown

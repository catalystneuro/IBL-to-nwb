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

# Force shutdown on error to prevent runaway instances
# Note: Only trap ERR, not EXIT - EXIT would trigger on successful completion too
trap 'FAIL_TIME=$(date +%s); FAIL_DURATION=$((FAIL_TIME - SCRIPT_START_TIME)); echo "=== RESULT: FAILED | eid=${SESSION_EID:-unknown} | duration_seconds=${FAIL_DURATION} | line=${LINENO} ==="; echo "ERROR: Script failed at line ${LINENO}. Shutting down in 60 seconds..."; sleep 60; shutdown -h now' ERR

# Configuration variables (substituted by launch script)
MOUNT_POINT="/ebs"
REPO_URL="{{REPO_URL}}"
REPO_BRANCH="{{REPO_BRANCH}}"
DANDISET_ID="{{DANDISET_ID}}"
DANDI_INSTANCE="{{DANDI_INSTANCE}}"
CONVERSION_MODE="{{CONVERSION_MODE}}"  # Empty string, "--raw-only", or "--processed-only"

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


# Note: Session assignment is read from SessionEID tag via IMDSv2 by convert_and_upload.py
echo "Instance will process single session: ${SESSION_EID} (index ${SESSION_INDEX})"

# Run conversion (upload happens after in bash)
log_phase_start "conversion"
CONVERSION_START=$(date +%s)
echo "Starting conversion process..."
cd "${REPO_DIR}/src/ibl_to_nwb/_aws/ec2_worker"

# Virtual environment is already activated, just run python directly
# Build command with optional flags
CONVERSION_CMD="python convert_and_upload.py"

# Add --stub-test flag if StubTest tag is "true"
if [[ "${STUB_TEST}" == "true" ]]; then
    CONVERSION_CMD="${CONVERSION_CMD} --stub-test"
    echo "Running in STUB TEST mode (only metadata, no raw data)"
else
    echo "Running in PRODUCTION mode (full data conversion)"
fi

# Add conversion mode flag if specified (--raw-only or --processed-only)
if [[ -n "${CONVERSION_MODE}" ]]; then
    CONVERSION_CMD="${CONVERSION_CMD} ${CONVERSION_MODE}"
    echo "Conversion mode: ${CONVERSION_MODE}"
else
    echo "Conversion mode: both (raw + processed)"
fi

echo "Running: ${CONVERSION_CMD}"

# Run conversion with bash-level safety net timeout
# Python handles per-phase timeouts (SIGALRM), but SIGALRM doesn't interrupt C extensions
# (HDF5, mtscomp). The bash timeout ensures we never run indefinitely.
# Phase timeouts: download(1h) + decompress(1.5h) + raw(3h) + processed(0.5h) = 6h
# Safety net: 7 hours = 25200 seconds (allows phases to timeout naturally, catches hangs)
CONVERSION_TIMEOUT=25200

if ! timeout --signal=KILL ${CONVERSION_TIMEOUT} ${CONVERSION_CMD}; then
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 137 ]; then
        # SIGKILL (128 + 9 = 137) from bash timeout
        echo "=== RESULT: TIMEOUT | eid=${SESSION_EID} | phase=safety_net | timeout_seconds=${CONVERSION_TIMEOUT} ==="
        echo "ERROR: Conversion exceeded safety net timeout (${CONVERSION_TIMEOUT}s). Process was killed."
        sleep 10
        shutdown -h now
    elif [ "$EXIT_CODE" -eq 124 ]; then
        # Python phase timeout
        echo "ERROR: Conversion phase timed out (see Python logs for details). Shutting down..."
        sleep 10
        shutdown -h now
    fi
    exit $EXIT_CODE
fi

log_phase_end "conversion" "${CONVERSION_START}"
log_disk_usage "after_conversion"

# Download dandiset.yaml - this creates the ${DANDISET_ID}/ folder automatically
echo "Downloading dandiset.yaml for dandiset ${DANDISET_ID} from ${DANDI_INSTANCE}..."
cd "${MOUNT_POINT}/nwbfiles"
if [[ "${DANDI_INSTANCE}" == "dandi" ]]; then
    DANDI_URL="https://dandiarchive.org/dandiset/${DANDISET_ID}"
else
    DANDI_URL="https://sandbox.dandiarchive.org/dandiset/${DANDISET_ID}"
fi
dandi download --download dandiset.yaml "${DANDI_URL}"

# Now ${DANDISET_ID}/ folder exists with dandiset.yaml inside it
DANDISET_FOLDER="${MOUNT_POINT}/nwbfiles/${DANDISET_ID}"

# Move converted NWB files and videos into dandiset folder
# Only stub or full is run at the same time, no danger of collisions
echo "Moving NWB files and videos into dandiset folder..."
for conversion_type in full stub; do
    CONVERSION_OUTPUT="${MOUNT_POINT}/nwbfiles/${conversion_type}"
    if [ -d "${CONVERSION_OUTPUT}" ] && [ -n "$(ls -A ${CONVERSION_OUTPUT} 2>/dev/null)" ]; then
        echo "Moving files from ${conversion_type}/ to dandiset folder..."
        # Move entire subject directories (includes NWB files and video subdirectories)
        mv "${CONVERSION_OUTPUT}"/sub-* "${DANDISET_FOLDER}/" 2>/dev/null || true
    fi
done

echo "Files moved to dandiset folder"


# Upload to DANDI
log_phase_start "dandi_upload"
UPLOAD_START=$(date +%s)
echo "Uploading to DANDI..."
cd "${DANDISET_FOLDER}"

# File inventory before upload (machine-parseable)
echo "=== FILE_INVENTORY: START ==="
NWB_COUNT=$(find "${DANDISET_FOLDER}" -name "*.nwb" -type f | wc -l)
NWB_TOTAL_BYTES=$(find "${DANDISET_FOLDER}" -name "*.nwb" -type f -exec stat --format="%s" {} + 2>/dev/null | awk '{sum+=$1} END {print sum}')
NWB_TOTAL_GB=$(echo "scale=2; ${NWB_TOTAL_BYTES:-0} / 1073741824" | bc)
echo "nwb_file_count=${NWB_COUNT}"
echo "nwb_total_bytes=${NWB_TOTAL_BYTES:-0}"
echo "nwb_total_gb=${NWB_TOTAL_GB}"
echo "=== FILE_INVENTORY: END ==="

# Debug: Show directory structure before upload
echo "=== Contents of dandiset folder ==="
ls -lah "${DANDISET_FOLDER}"
echo ""
echo "=== Subject directories ==="
ls -d "${DANDISET_FOLDER}"/sub-*/ 2>/dev/null || echo "No subject directories found"
echo ""
echo "=== NWB files with sizes ==="
find "${DANDISET_FOLDER}" -name "*.nwb" -type f -exec ls -lh {} \;
echo ""

# Debug: Check if DANDI API keys are still set
echo "DEBUG: DANDI_API_KEY is set: ${DANDI_API_KEY:+YES}"
echo "DEBUG: DANDI_SANDBOX_API_KEY is set: ${DANDI_SANDBOX_API_KEY:+YES}"
echo "DEBUG: Uploading to DANDI instance: ${DANDI_INSTANCE}"

# Track upload timing
UPLOAD_CMD_START=$(date +%s)
echo "=== DANDI_UPLOAD: START | $(date -u +%Y-%m-%dT%H:%M:%S%z) ==="

# DANDI upload with 3-hour timeout
UPLOAD_TIMEOUT=10800  # 3 hours
if ! timeout ${UPLOAD_TIMEOUT} dandi upload -i "${DANDI_INSTANCE}" .; then
    DANDI_EXIT_CODE=$?
    if [ "$DANDI_EXIT_CODE" -eq 124 ]; then
        echo "=== RESULT: TIMEOUT | eid=${SESSION_EID} | phase=dandi_upload | timeout_seconds=${UPLOAD_TIMEOUT} ==="
        echo "ERROR: DANDI upload exceeded ${UPLOAD_TIMEOUT} seconds (3 hours). Shutting down..."
        sleep 10
        shutdown -h now
    fi
else
    DANDI_EXIT_CODE=0
fi

UPLOAD_CMD_END=$(date +%s)
UPLOAD_DURATION=$((UPLOAD_CMD_END - UPLOAD_CMD_START))

# Calculate upload speed
if [ -n "${NWB_TOTAL_GB}" ] && [ "${UPLOAD_DURATION}" -gt 0 ]; then
    UPLOAD_SPEED_MBPS=$(echo "scale=1; ${NWB_TOTAL_GB} * 1024 / ${UPLOAD_DURATION}" | bc)
else
    UPLOAD_SPEED_MBPS="unknown"
fi

echo "=== DANDI_UPLOAD: END | duration_seconds=${UPLOAD_DURATION} | size_gb=${NWB_TOTAL_GB:-unknown} | speed_mbps=${UPLOAD_SPEED_MBPS} ==="

# Always print the DANDI log for debugging (especially useful when validation fails)
echo ""
echo "=== DANDI CLI Log ==="
DANDI_LOG_DIR="/root/.local/state/dandi-cli/log"
if [ -d "${DANDI_LOG_DIR}" ]; then
    # Find the most recent log file
    DANDI_LOG=$(ls -t "${DANDI_LOG_DIR}"/*.log 2>/dev/null | head -1)
    if [ -n "${DANDI_LOG}" ] && [ -f "${DANDI_LOG}" ]; then
        echo "Log file: ${DANDI_LOG}"
        echo "--- Log contents ---"
        cat "${DANDI_LOG}"
        echo "--- End of log ---"
    else
        echo "No DANDI log files found in ${DANDI_LOG_DIR}"
    fi
else
    echo "DANDI log directory not found: ${DANDI_LOG_DIR}"
fi
echo ""

# Check if upload succeeded
if [ ${DANDI_EXIT_CODE} -ne 0 ]; then
    echo "=== RESULT: FAILED | eid=${SESSION_EID} | phase=dandi_upload | error=exit_code_${DANDI_EXIT_CODE} ==="
    exit ${DANDI_EXIT_CODE}
fi

log_phase_end "dandi_upload" "${UPLOAD_START}"

# Final summary with all timings
SCRIPT_END_TIME=$(date +%s)
TOTAL_DURATION=$((SCRIPT_END_TIME - SCRIPT_START_TIME))
TOTAL_MINUTES=$((TOTAL_DURATION / 60))
TOTAL_HOURS=$(echo "scale=2; ${TOTAL_DURATION} / 3600" | bc)

echo ""
echo "=== FINAL_SUMMARY: START ==="
echo "eid=${SESSION_EID}"
echo "session_index=${SESSION_INDEX}"
echo "instance_id=${INSTANCE_ID}"
echo "stub_test=${STUB_TEST}"
echo "conversion_mode=${CONVERSION_MODE:-both}"
echo "dandi_instance=${DANDI_INSTANCE}"
echo "dandiset_id=${DANDISET_ID}"
echo "nwb_file_count=${NWB_COUNT}"
echo "nwb_total_gb=${NWB_TOTAL_GB}"
echo "total_duration_seconds=${TOTAL_DURATION}"
echo "total_duration_minutes=${TOTAL_MINUTES}"
echo "total_duration_hours=${TOTAL_HOURS}"
echo "=== FINAL_SUMMARY: END ==="
echo ""
echo "=== RESULT: SUCCESS | eid=${SESSION_EID} | total_minutes=${TOTAL_MINUTES} ==="

# Cleanup and shutdown
echo "Upload complete. Shutting down in 60 seconds..."
sleep 60
shutdown -h now

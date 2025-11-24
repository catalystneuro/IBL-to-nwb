#!/bin/bash
# EC2 user-data script for distributed IBL NWB conversion and DANDI upload
#
# This script executes once during instance boot and performs:
#   1. Mounts and formats the EBS volume for scratch/cache storage
#   2. Installs uv and required system dependencies
#   3. Clones the IBL-to-nwb repository (includes bwm_session_eids.json)
#   4. Runs the conversion script (reads SessionEID tag from IMDSv2)
#   5. Uploads NWB files to DANDI
#   6. Shuts down the instance when complete
#
# PREREQUISITES:
#   - Instance must be tagged with "SessionEID" and "SessionIndex" (e.g., "abc123...", "42")
#   - Instance must have IMDSv2 metadata access enabled (for reading tags)
#   - DANDI_API_KEY, REPO_URL, REPO_BRANCH, DANDISET_ID are substituted at launch time

set -euxo pipefail

# Force shutdown on error to prevent runaway instances
# Note: Only trap ERR, not EXIT - EXIT would trigger on successful completion too
trap 'echo "ERROR: Script failed. Shutting down in 60 seconds..."; sleep 60; shutdown -h now' ERR

# Configuration variables (substituted by launch script)
MOUNT_POINT="/ebs"
REPO_URL="{{REPO_URL}}"
REPO_BRANCH="{{REPO_BRANCH}}"
DANDISET_ID="{{DANDISET_ID}}"

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

# Setup EBS volume with bulletproof device detection
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

# Install minimal system dependencies
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

# Clone repository
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

# Setup DANDI API key from template substitution
# Disable command echoing to prevent key from appearing in cloud-init logs
set +x
DANDI_API_KEY="{{DANDI_API_KEY}}"
export DANDI_API_KEY

# Shred the user-data file (contains the API key) after reading it
# This removes the on-disk copy that cloud-init caches
if [[ -f /var/lib/cloud/instance/user-data.txt ]]; then
    shred -u /var/lib/cloud/instance/user-data.txt 2>/dev/null || true
fi
set -x  # Re-enable command echoing for debugging


# Note: Session assignment is read from SessionEID tag via IMDSv2 by convert_assigned_sessions.py
echo "Instance will process single session: ${SESSION_EID} (index ${SESSION_INDEX})"

# Run conversion (upload happens after in bash)
echo "Starting conversion process..."
cd "${REPO_DIR}/src/ibl_to_nwb/_aws"

# Virtual environment is already activated, just run python directly
# Pass --stub-test flag if StubTest tag is "true"
if [[ "${STUB_TEST}" == "true" ]]; then
    echo "Running in STUB TEST mode (only metadata, no raw data)"
    python convert_assigned_sessions.py --stub-test
else
    echo "Running in PRODUCTION mode (full data conversion)"
    python convert_assigned_sessions.py
fi

# Download dandiset.yaml - this creates the ${DANDISET_ID}/ folder automatically
echo "Downloading dandiset.yaml for dandiset ${DANDISET_ID}..."
cd "${MOUNT_POINT}/nwbfiles"
dandi download --download dandiset.yaml https://sandbox.dandiarchive.org/dandiset/${DANDISET_ID}

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
echo "Uploading to DANDI..."
cd "${DANDISET_FOLDER}"

# Debug: Show directory structure before upload
echo "=== Contents of dandiset folder ==="
ls -lah "${DANDISET_FOLDER}"
echo ""
echo "=== Subject directories ==="
ls -d "${DANDISET_FOLDER}"/sub-*/ 2>/dev/null || echo "No subject directories found"
echo ""
echo "=== NWB files ==="
find "${DANDISET_FOLDER}" -name "*.nwb" -type f
echo ""

dandi upload -i dandi-sandbox .

# Cleanup and shutdown
echo "Upload complete. Shutting down in 60 seconds..."
sleep 60
shutdown -h now

#!/bin/bash
# EC2 user-data script for distributed IBL NWB conversion and DANDI upload
#
# This script executes once during instance boot and performs:
#   1. Mounts and formats the EBS volume for scratch/cache storage
#   2. Installs uv and required system dependencies
#   3. Clones the IBL-to-nwb repository
#   4. Downloads the shard assignment file
#   5. Runs the conversion + upload script using uv
#   6. Shuts down the instance when complete
#
# PREREQUISITES:
#   - Instance must be tagged with "ShardId" (e.g., "001", "002", ...)
#   - Instance must have IMDSv2 metadata access enabled (for reading tags)
#   - DANDI_API_KEY is substituted into this script at launch time (template substitution)
#   - Assignment files must be accessible via GitHub

set -euxo pipefail

# Configuration variables
MOUNT_POINT="/ebs"
REPO_URL="git@github.com:catalystneuro/IBL-to-nwb.git"
REPO_BRANCH="heberto_conversion"
ASSIGNMENT_BASE_URL="https://raw.githubusercontent.com/catalystneuro/IBL-to-nwb/heberto_conversion/assignments"

# Fetch instance metadata (IMDSv2 - requires token)
IMDS_TOKEN="$(curl -X PUT -fsS "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")"

INSTANCE_ID="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/instance-id)"
REGION="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/placement/region)"

# Get the ShardId tag from instance metadata (no AWS CLI/IAM role needed!)
SHARD_ID="$(curl -fsS -H "X-aws-ec2-metadata-token: ${IMDS_TOKEN}" \
    http://169.254.169.254/latest/meta-data/tags/instance/ShardId)"

if [[ -z "${SHARD_ID}" || "${SHARD_ID}" == "None" ]]; then
    echo "ERROR: Missing ShardId tag on instance ${INSTANCE_ID}" >&2
    exit 1
fi

echo "Instance ${INSTANCE_ID} processing shard ${SHARD_ID}"

# Setup EBS volume
echo "Setting up EBS volume at ${MOUNT_POINT}..."
DEVICE=$(lsblk -ndo NAME,TYPE | awk '$2=="disk"{print $1}' | grep -v "$(df / | tail -1 | awk '{print $1}' | sed 's|/dev/||;s|[0-9]*$||')" | head -1)

if [[ -z "${DEVICE}" ]]; then
    echo "WARNING: No additional EBS volume found. Using root volume."
    MOUNT_POINT="/opt/ebs"
    mkdir -p "${MOUNT_POINT}"
else
    DEVICE_PATH="/dev/${DEVICE}"
    if ! blkid "${DEVICE_PATH}"; then
        echo "Formatting ${DEVICE_PATH}..."
        mkfs.ext4 -F "${DEVICE_PATH}"
    fi
    mkdir -p "${MOUNT_POINT}"
    mount "${DEVICE_PATH}" "${MOUNT_POINT}"
    UUID=$(blkid -s UUID -o value "${DEVICE_PATH}")
    echo "UUID=${UUID} ${MOUNT_POINT} ext4 defaults,nofail 0 2" >> /etc/fstab
fi

chmod 777 "${MOUNT_POINT}"

# Install minimal system dependencies
# Note: uv handles all Python packages and downloads pre-built wheels
# No build tools needed since nothing is compiled!
echo "Installing system dependencies..."
apt-get update
apt-get install -y \
    git \                   # Clone repository from GitHub
    curl \                  # Required for IMDSv2 metadata access and uv install
    ca-certificates         # Required for HTTPS connections (GitHub, DANDI)

# Install uv
echo "Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.cargo/bin:${PATH}"
echo 'export PATH="/root/.cargo/bin:${PATH}"' >> /root/.bashrc

# Clone repository
echo "Cloning IBL-to-nwb repository..."
REPO_DIR="${MOUNT_POINT}/IBL-to-nwb"
git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${REPO_DIR}"

cd "${REPO_DIR}"

# Setup virtual environment with uv
echo "Setting up Python environment with uv..."
/root/.cargo/bin/uv venv --seed  # Create venv with pip, setuptools, wheel
/root/.cargo/bin/uv sync         # Install project dependencies from pyproject.toml

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


# Download assignment file to standard location
echo "Downloading assignment file for shard ${SHARD_ID}..."
ASSIGNMENT_FILE="${MOUNT_POINT}/chunk.json"
wget -O "${ASSIGNMENT_FILE}" "${ASSIGNMENT_BASE_URL}/chunk-${SHARD_ID}.json"

# Run conversion (upload happens after in bash)
echo "Starting conversion process..."
cd "${REPO_DIR}/src/ibl_to_nwb/_aws_run"

# Virtual environment is already activated, just run python directly
python convert_assigned_sessions.py

# Move converted NWB files into dandiset folder
echo "Moving NWB files into dandiset folder..."
DANDISET_FOLDER="${MOUNT_POINT}/nwbfiles/217706"

# Download dandiset.yaml from dandi-staging
echo "Downloading dandiset.yaml..."
mkdir -p "${MOUNT_POINT}/nwbfiles/217706"
cd "${MOUNT_POINT}/nwbfiles/217706"
dandi download --download dandiset.yaml dandi://dandi-staging/217706

# Check both full and stub folders (conversion writes to one or the other)
for conversion_type in full stub; do
    CONVERSION_OUTPUT="${MOUNT_POINT}/nwbfiles/${conversion_type}"
    if [ -d "${CONVERSION_OUTPUT}" ] && [ -n "$(ls -A ${CONVERSION_OUTPUT} 2>/dev/null)" ]; then
        echo "Moving files from ${conversion_type}/ to dandiset folder..."
        mv "${CONVERSION_OUTPUT}"/sub-* "${DANDISET_FOLDER}/" 2>/dev/null || true
    fi
done

echo "Files moved to dandiset folder"


# Upload to DANDI
echo "Uploading to DANDI..."
cd "${DANDISET_FOLDER}"
dandi upload -i dandi-staging .

# Cleanup and shutdown
echo "Upload complete. Shutting down in 60 seconds..."
sleep 60
shutdown -h now

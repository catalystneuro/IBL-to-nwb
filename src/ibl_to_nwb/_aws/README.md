# IBL NWB Conversion - AWS Distributed Processing

Unified AWS infrastructure for distributed conversion of International Brain Laboratory (IBL) sessions to Neurodata Without Borders (NWB) format.

## Architecture

### One-Session-Per-Instance Model

This system uses a **simplified one-session-per-instance** architecture:

- Each EC2 instance processes **exactly one** IBL session
- No complex sharding or range calculations
- Direct EID-to-instance mapping for easier debugging
- Auto-termination protection prevents runaway costs

### Key Components

```
_aws/
├── profiles/              # Profile-based configuration
│   ├── catalyst_neuro.env # CatalystNeuro account settings
│   └── ibl.env            # IBL account settings
├── setup_infrastructure.py      # Creates VPC/subnet/security group (run once)
├── launch_ec2_instances.py      # Launches instances (main CLI)
├── convert_assigned_sessions.py # Worker: converts single session
├── ec2_userdata_production.sh   # EC2 boot script
├── monitor.py                   # Real-time instance monitoring
├── verify_dandi_uploads.py      # Post-conversion verification
├── bwm_session_eids.json        # 459 unique session EIDs
├── generate_unique_eids.py      # Creates session EID list
├── generate_tracking_json.py    # Creates verification tracking
└── README.md                    # This file
```

## Setup (One-Time)

### 1. Prerequisites

- **AWS Account**: Access to either CatalystNeuro or IBL AWS account
- **AWS CLI**: Configured with credentials (`aws configure`)
- **DANDI API Key**: Get from https://dandiarchive.org/user/settings
- **Python**: Python 3.10+ (local machine only, EC2 instances install their own)

### 2. Configure Infrastructure

Run setup script to create VPC, subnet, security group, etc. (or update existing profile):

```bash
# For CatalystNeuro account
python setup_infrastructure.py --profile catalyst_neuro

# For IBL account
python setup_infrastructure.py --profile ibl
```

This creates/updates `profiles/{profile}.env` with network IDs.

### 3. Add DANDI API Key

Edit the profile config and add your DANDI API key:

```bash
vim profiles/catalyst_neuro.env

# Change this line:
# DANDI_API_KEY=your-dandi-api-key-here

# To your actual key:
# DANDI_API_KEY=abc123...xyz789
```

**IMPORTANT**: This file is gitignored. Never commit secrets to git!

## Usage

### Launching Instances

The launch script supports two simple session selection methods:

#### 1. Launch All Sessions

```bash
python launch_ec2_instances.py --profile catalyst_neuro --all
```

Launches **459 instances** (one per session in `bwm_session_eids.json`).

#### 2. Launch Session Range

```bash
# Launch first 10 sessions (indices 0-9)
python launch_ec2_instances.py --profile ibl --range 0-10

# Launch single session (index 42)
python launch_ec2_instances.py --profile catalyst_neuro --range 42-43

# Launch sessions 100-149 (50 sessions)
python launch_ec2_instances.py --profile ibl --range 100-150
```

Range uses **Python-style slicing**: start is **inclusive**, end is **exclusive** (like `array[0:10]`).

#### 3. Test with Stub Mode

```bash
# Test first session with lightweight stub conversion (100GB storage)
python launch_ec2_instances.py --profile catalyst_neuro --range 0-1 --stub-test
```

Stub mode:
- Uses 100GB EBS volume (vs 700GB production)
- Downloads only metadata (no raw ephys or video data)
- Faster conversion for testing infrastructure

#### 4. Custom Instance Type

```bash
# Use larger instance for faster processing (first 10 sessions)
python launch_ec2_instances.py --profile ibl --range 0-10 --instance-type m6a.4xlarge
```

Default is `m6a.2xlarge` (8 vCPUs, 32GB RAM, best value).

### Monitoring

#### Real-Time Monitoring

Monitor all running instances with auto-refresh:

```bash
python monitor.py --interval 30  # Refresh every 30 seconds (default)
```

Shows:
- Instance state (pending/running/stopping)
- Current stage (mounting EBS, installing packages, converting)
- Session being processed
- Errors and warnings

#### View Instance Logs

```bash
# Get instance ID from monitor.py output
python monitor.py --logs i-0123456789abcdef0 --lines 200
```

Shows last 200 lines of console output for debugging.

### Verification

After all conversions complete, verify uploads to DANDI:

```bash
python verify_dandi_uploads.py \
    --dandiset-id 217706 \
    --dandi-instance dandi-sandbox
```

Output:
- Complete sessions (RAW + PROCESSED uploaded)
- Incomplete sessions (missing files)
- Generates `failed_eids.json` for re-runs

To re-run failed sessions:

```bash
# Manual re-launch (example for sessions 10-15)
python launch_ec2_instances.py --profile catalyst_neuro --range 10-15
```

## Architecture Details

### Session Assignment

Each instance receives tags via IMDSv2 (EC2 metadata service):

```bash
SessionEID: "abc123-def456-789..."  # Unique session identifier
SessionIndex: "42"                  # Index in bwm_session_eids.json
StubTest: "true"                    # Stub test mode flag
```

The worker script (`convert_assigned_sessions.py`) reads these tags and processes the single assigned session.

### Auto-Termination Protection

Two layers prevent runaway instances:

1. **Instance shutdown behavior**: `InstanceInitiatedShutdownBehavior: "terminate"`
   - Converts `shutdown -h now` → terminate (not stop)
   - Stopped instances cost $36/month, terminated cost $0

2. **Bash trap**: `trap 'shutdown -h now' ERR EXIT`
   - Forces shutdown on ANY script error
   - Catches failures that don't reach the end of the script

### Conversion Workflow

Each instance executes this workflow:

```
1. Boot → ec2_userdata_production.sh runs
2. Mount EBS volume (700GB for production, 100GB for stub test)
3. Install system dependencies (git, curl)
4. Install uv (fast Python package manager)
5. Clone IBL-to-nwb repository
6. Create Python virtual environment
7. Read SessionEID tag from instance metadata (IMDSv2)
8. Run convert_assigned_sessions.py:
   a. Download session data from ONE API
   b. Convert to RAW NWB (SpikeGLX ephys + videos)
   c. Convert to PROCESSED NWB (spike sorting, behavior, tracking)
   d. Write NWB files to /ebs/nwbfiles/full/sub-*/
9. Download dandiset.yaml
10. Move NWB files into dandiset folder structure
11. Upload to DANDI with dandi-cli
12. Shutdown → auto-terminate
```

### Cost Estimation

**Production mode (700GB storage):**
- Instance: m6a.2xlarge = $0.345/hour (on-demand)
- EBS: 700GB gp3 = $0.08/GB-month = $56/month ($0.077/hour)
- Network: Negligible (< $0.01/GB egress)
- **Total per instance**: ~$0.42/hour

**Stub test mode (100GB storage):**
- Instance: m6a.2xlarge = $0.345/hour
- EBS: 100GB gp3 = $0.08/GB-month = $8/month ($0.011/hour)
- **Total per instance**: ~$0.36/hour

**Full dataset (459 sessions):**
- Estimated time per session: 2-4 hours (varies by session size)
- Total cost: 459 sessions × 3 hours × $0.42/hour = **~$580**

**Cost savings vs stopped instances:**
- Stopped instance: $36/month (50GB root EBS)
- Running for 19 days: $152 wasted (actual incident from logs)
- Auto-termination pays for itself after 1-2 failures

## Session Database

### bwm_session_eids.json

Contains **459 unique session EIDs** deduplicated from the Brain-Wide Map dataset.

**Source**: `fixtures/bwm_df.pqt` (699 rows = probe insertions)

**Why 459 < 699?**
- Some sessions have multiple probes (2-4 probes per session)
- Each NWB file contains ALL probes for that session
- Deduplication prevents duplicate work

**Generation**:

```bash
python generate_unique_eids.py
```

Reads `fixtures/bwm_df.pqt` → writes `bwm_session_eids.json`.

### Session Indexing

The `--range` argument uses **Python-style slicing** (0-indexed, end exclusive):

```python
# bwm_session_eids.json structure:
{
    "total": 459,
    "eids": [
        "aba04da9-970e-47bb-ab77-56f8672c8008",  # Index 0
        "b1a4c0e3-e8a7-4a0c-8c4f-2e5f3a6b7c8d",  # Index 1
        ...
        "z9y8x7w6-v5u4-t3s2-r1q0-p9o8n7m6l5k4"   # Index 458
    ]
}
```

```bash
# Launch first session (index 0)
python launch_ec2_instances.py --profile catalyst_neuro --range 0-1

# Launch sessions 0-9 (first 10 sessions)
python launch_ec2_instances.py --profile catalyst_neuro --range 0-10

# Launch last session (index 458)
python launch_ec2_instances.py --profile catalyst_neuro --range 458-459
```

**Math check**: `--range 0-10` launches indices [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] = 10 sessions (end - start = count).

## Tracking & Verification

### Pre-Conversion Tracking

Generate expected DANDI paths for verification:

```bash
python generate_tracking_json.py
```

Creates `tracking.json` with expected upload paths for all 459 sessions.

### Post-Conversion Verification

Check which files successfully uploaded to DANDI:

```bash
python verify_dandi_uploads.py \
    --dandiset-id 217706 \
    --dandi-instance dandi-sandbox
```

Output files:
- `tracking_verified.json` - Full tracking with verification status
- `failed_sessions.json` - Sessions with missing files
- `failed_eids.json` - Just the EIDs (ready for re-launch)

### Console Logs

Each instance logs to:
- **Cloud-init logs**: `/var/log/cloud-init-output.log` (on instance)
- **Conversion logs**: `/ebs/conversion_logs/conversion_log_{eid}_{timestamp}.log`
- **Conversion summary**: `/ebs/conversion_logs/conversion_summary_{eid}_{timestamp}.json`

Access via `monitor.py` or SSH (if `--key-name` was provided).

## Troubleshooting

### Instance Won't Launch

**Error**: "SecurityGroup not found" or "VPC not found"

**Solution**: Run setup script first:

```bash
python setup_infrastructure.py --profile catalyst_neuro
```

### Instance Launches But Fails Immediately

**Check console logs**:

```bash
# Get instance ID from AWS console or monitor.py
python monitor.py --logs i-0123456789abcdef0 --lines 500
```

**Common issues**:
- Missing DANDI API key in profile config
- GitHub repository not accessible (check branch name)
- EBS volume mount failure (check device detection logic)

### Conversion Succeeds But Upload Fails

**Check DANDI credentials**:

```bash
# On instance (if you SSH'd in):
echo $DANDI_API_KEY
dandi ls --dandi-instance dandi-sandbox
```

**Check DANDI API status**: https://status.dandiarchive.org/

### Instance Doesn't Auto-Terminate

**This should never happen** due to trap + InstanceInitiatedShutdownBehavior.

If it does:
1. Check console logs: `python monitor.py --logs INSTANCE_ID`
2. Manually terminate: `aws ec2 terminate-instances --instance-ids INSTANCE_ID`
3. Report bug with logs

### Cost Overrun

**Monitor running instances**:

```bash
# List all instances (including stopped)
aws ec2 describe-instances --region us-east-2 \
    --filters "Name=tag:Project,Values=IBL-NWB-Conversion" \
    --query 'Reservations[*].Instances[*].[InstanceId,State.Name,LaunchTime]' \
    --output table
```

**Terminate all instances** (emergency stop):

```bash
# Get all running instance IDs
INSTANCE_IDS=$(aws ec2 describe-instances --region us-east-2 \
    --filters "Name=tag:Project,Values=IBL-NWB-Conversion" \
              "Name=instance-state-name,Values=running,pending" \
    --query 'Reservations[*].Instances[*].InstanceId' \
    --output text)

# Terminate them
if [ -n "$INSTANCE_IDS" ]; then
    aws ec2 terminate-instances --instance-ids $INSTANCE_IDS
fi
```

## Profile Configuration

### catalyst_neuro.env

```bash
# Network IDs (from setup_infrastructure.py)
VPC_ID=vpc-xxxxxxxxxxxxxxxxx
SUBNET_ID=subnet-xxxxxxxxxxxxxxxxx
SECURITY_GROUP_ID=sg-xxxxxxxxxxxxxxxxx
REGION=us-east-2

# DANDI credentials
DANDI_API_KEY=your-key-here

# Repository settings
REPO_URL=https://github.com/h-mayorquin/IBL-to-nwb.git
REPO_BRANCH=heberto_conversion
DANDISET_ID=217706
```

### ibl.env

Same structure, different network IDs (from IBL AWS account).

## Advanced Usage

### SSH Access for Debugging

Launch with key pair:

```bash
python launch_ec2_instances.py \
    --profile catalyst_neuro \
    --range 0-0 \
    --stub-test \
    --key-name my-ec2-keypair
```

SSH to instance:

```bash
# Get public IP from AWS console or:
INSTANCE_IP=$(aws ec2 describe-instances \
    --instance-ids i-0123456789abcdef0 \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

ssh -i ~/.ssh/my-ec2-keypair.pem ubuntu@${INSTANCE_IP}
```

**Note**: Security group allows SSH from 0.0.0.0/0. Restrict to your IP in production!

### Local Testing

Test conversion script locally (without EC2):

```bash
cd /home/heberto/development/ibl_conversion/IBL-to-nwb/src/ibl_to_nwb/_aws

python convert_assigned_sessions.py \
    --session-eid abc123-def456-789... \
    --stub-test
```

**Note**: Requires local ONE API setup and write access to `/ebs/` (or modify paths in script).

### Custom Repository

Test with your own fork:

```bash
# Edit profile config
vim profiles/catalyst_neuro.env

# Change:
# REPO_URL=https://github.com/your-username/IBL-to-nwb.git
# REPO_BRANCH=your-feature-branch

# Launch
python launch_ec2_instances.py --profile catalyst_neuro --range 0-0 --stub-test
```

## Migration from Old System

This unified `_aws/` directory replaces:
- `_aws_run/` (CatalystNeuro account, shard-based)
- `_aws_ibl/` (IBL account, shard-based)

### Key Differences

| Feature | Old (Shard-Based) | New (One-Session-Per-Instance) |
|---------|-------------------|--------------------------------|
| **Sessions per instance** | 9-13 (variable) | 1 (fixed) |
| **Tags** | ShardId, ShardRange | SessionEID, SessionIndex |
| **Launch arguments** | `--num-instances`, `--total-sessions` | `--all`, `--range` |
| **Worker script** | Loops over sessions | Processes single session |
| **Debugging** | Which session failed? | Direct EID → instance mapping |
| **Cost transparency** | Mental math required | 1 session = 1 instance |

### Why Change?

1. **Simpler**: No shard calculation, no range parsing
2. **Safer**: Failed session doesn't lose 8 other sessions
3. **Clearer**: Instance name shows session (e.g., `ibl-conversion-NYU-11-2020-08-01-001`)
4. **Debuggable**: Console logs show single session (not 9 interleaved logs)

## License

See repository root LICENSE file.

## Support

For issues or questions:
1. Check this README first
2. Search repository issues: https://github.com/h-mayorquin/IBL-to-nwb/issues
3. Create new issue with:
   - Full command you ran
   - Error message / console logs
   - Instance ID (if applicable)

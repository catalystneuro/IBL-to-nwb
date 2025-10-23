# AWS Distributed IBL NWB Conversion

Run IBL NWB conversion across 50 EC2 instances in parallel, each processing ~9 sessions independently and uploading to DANDI.

**Status**: Production-ready! Uses dedicated VPC isolation with IMDSv2 (no IAM role needed).

---

## Quick Start

### Prerequisites

1. AWS CLI configured: `aws configure`
2. Python with `boto3`: `pip install boto3`
3. DANDI API key for dandi-staging

### Step 1: Verify AWS Permissions

```bash
python verify_aws_permissions.py
```

Expected output: `✓ SUCCESS: You have all required AWS permissions!`

This checks permissions for VPC creation, EC2 instances, and S3 VPC Gateway Endpoint.

### Step 2: Configure Isolated Network (one-time)

```bash
python configure_networking.py
```

This creates a **dedicated VPC** isolated from your other infrastructure:
- VPC (10.50.0.0/16)
- Public subnet (10.50.1.0/24)
- Internet Gateway (for GitHub, DANDI access)
- Route table with internet route
- S3 VPC Gateway Endpoint (FREE - keeps S3 traffic within AWS)
- Security group with SSH access

**Output**: Creates `network_config.env` file with VPC/subnet/security group IDs.

### Step 3: Add DANDI API Key to Configuration

Edit `network_config.env` and add your DANDI API key:

```bash
vim src/ibl_to_nwb/_aws_run/network_config.env
```

Find the line `DANDI_API_KEY=your-dandi-api-key-here` and replace with your actual key.

**Security**: This file is gitignored. The key is substituted into user-data at launch time and shredded from disk after use.

### Step 4: Generate & Commit Assignments

```bash
# Testing (10 sessions across 3 instances)
python generate_assignments.py --num-shards 3 --stub-test

# Production (459 sessions across 50 instances)
python generate_assignments.py --num-shards 50

# Commit to GitHub (instances download from here)
git add assignments/
git commit -m "Add shard assignments"
git push origin heberto_conversion
```

### Step 5: Launch Instances

The script automatically reads network configuration from `network_config.env`:

```bash
# Testing (3 instances, uses network_config.env automatically):
python launch_ec2_instances.py --num-instances 3 --stub-test

# Production (50 instances):
python launch_ec2_instances.py --num-instances 50
```

**Advanced**: Override network config with CLI arguments:

```bash
# Use different VPC/subnet/security group:
python launch_ec2_instances.py \
  --vpc-id vpc-different \
  --subnet-id subnet-different \
  --security-group-id sg-different \
  --num-instances 3 \
  --stub-test

# Use default VPC (ignores network_config.env):
python launch_ec2_instances.py --num-instances 3 --stub-test
# (Creates security group in default VPC automatically)
```

**That's it!** Instances will:
1. Boot and install dependencies (10-15 min)
2. Download assigned sessions from ONE
3. Convert to NWB (raw + processed)
4. Move files to dandiset folder
5. Upload to DANDI in batch
6. Auto-shutdown when complete (~13 hours total)

---

## Architecture

### How It Works

```
┌─────────────────┐
│  459 sessions   │
│  (bwm_df)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Generate Shards │  Split into N chunks (50 shards = ~9 sessions each)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  EC2 Instance 1  │  EC2 Instance 2  │ ... │ EC2 Instance N│
│  (Shard 001)     │  (Shard 002)     │     │  (Shard 050)  │
│                  │                  │     │               │
│  1. Read ShardId │  1. Read ShardId │     │  1. Read ShardId
│     from tags    │     from tags    │     │     from tags
│  2. Download     │  2. Download     │     │  2. Download  │
│     chunk-001    │     chunk-002    │     │     chunk-050 │
│  3. Convert      │  3. Convert      │     │  3. Convert   │
│  4. Upload       │  4. Upload       │     │  4. Upload    │
│  5. Shutdown     │  5. Shutdown     │     │  5. Shutdown  │
└─────────────────────────────────────────────────────────┘
```

### IMDSv2 Tag-Based Work Distribution

**Key Innovation**: Instances discover their work assignment by reading their own tags via the metadata service (no AWS API calls, no IAM role needed).

```bash
# Each instance reads its ShardId tag via IMDSv2
TOKEN=$(curl -X PUT http://169.254.169.254/latest/api/token \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
SHARD_ID=$(curl -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  http://169.254.169.254/latest/meta-data/tags/instance/ShardId)
# Returns: "023"

# Downloads corresponding assignment file
wget .../assignments/chunk-023.json
# Contains: ["eid1", "eid2", ..., "eid9"]
```

**Why this works**: AWS allows instances to read their own tags via metadata without IAM permissions.

### File Structure on EC2

```
/ebs/
├── ibl_data/                    # ONE cache (downloads)
├── temporary_files/             # Scratch space & logs
│   ├── conversion_log_*.log
│   └── batch_summary_*.json
└── nwbfiles/
    ├── full/                    # Conversion output
    │   ├── sub-UCLA012/
    │   │   ├── *_desc-raw_ecephys.nwb
    │   │   └── *_desc-processed_behavior+ecephys.nwb
    │   └── sub-KS016/
    │       └── ...
    └── 217706/                  # Dandiset folder (for upload)
        ├── dandiset.yaml
        ├── sub-UCLA012/         # Files moved here before upload
        │   ├── *.nwb
        └── sub-KS016/
            └── *.nwb
```

**Upload Process**:
1. Convert all sessions → `/ebs/nwbfiles/full/sub-*/`
2. Move files → `/ebs/nwbfiles/217706/sub-*/` (instant, same filesystem)
3. Upload once → `dandi upload -i dandi-staging` (batch operation)

---

## Monitoring

### AWS Console (Easiest)

```
https://console.aws.amazon.com/ec2/v2/home?region=us-east-2#Instances:
```

Filter by tag: `Project = IBL-NWB-Conversion`

### AWS CLI

```bash
# List all instances with status
aws ec2 describe-instances --region us-east-2 \
    --filters "Name=tag:Project,Values=IBL-NWB-Conversion" \
    --query 'Reservations[*].Instances[*].[InstanceId,State.Name,Tags[?Key==`ShardId`].Value|[0]]' \
    --output table

# Count completed (stopped = successful)
aws ec2 describe-instances --region us-east-2 \
    --filters "Name=tag:Project,Values=IBL-NWB-Conversion" "Name=instance-state-name,Values=stopped" \
    --query 'Reservations[*].Instances[*].InstanceId' --output text | wc -w
```

### Instance States

- `pending` → `running`: Instance is working
- `running` → `stopping` → `stopped`: Completed successfully
- `terminated`: Spot interruption (re-launch that shard)

### SSH into Instance (Optional)

```bash
# Get public IP
aws ec2 describe-instances --region us-east-2 \
    --filters "Name=tag:Project,Values=IBL-NWB-Conversion" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text

# SSH in (if you added --key-name when launching)
ssh -i your-key.pem ubuntu@<public-ip>

# View logs
tail -f /ebs/temporary_files/*.log
sudo tail -f /var/log/cloud-init-output.log
```

---

## Cost Estimation

### Per Instance (t3.2xlarge Spot)
- Instance: ~$0.10/hour (8 vCPU, 32GB RAM)
- EBS storage (400GB): ~$0.04/hour
- **Total per instance**: ~$0.14/hour

### Test Run (3 instances, stub data)
- 3 × $0.14/hour × 2 hours = **$0.84**

### Production Run (50 instances, 459 sessions)
- Hourly cost: 50 × $0.14 = **$7/hour**
- Estimated time: ~13.5 hours (9 sessions/instance × 1.5 hours/session)
- **Total estimated cost**: $7/hour × 13.5 hours = **~$95**

**Note**: Actual costs vary based on:
- Session conversion time (size, complexity)
- Network transfer (ONE downloads, DANDI uploads)
- Spot instance availability

---

## Troubleshooting

### Instances Not Starting

```bash
# Check permissions
python verify_aws_permissions.py

# Check AWS credentials
aws sts get-caller-identity

# Check S3 VPC endpoint
python configure_networking.py
```

### Assignment Files Not Found

```bash
# Verify files are pushed to GitHub
git status
git push origin heberto_conversion

# Check branch name in ec2_userdata_production.sh matches
grep REPO_BRANCH ec2_userdata_production.sh
```

### DANDI Upload Failures

- Verify you set `export DANDI_API_KEY="your-key"` before launching instances
- Check dandiset 217706 exists on dandi-staging
- Verify you have write access to the dandiset
- Check `dandiset.yaml` was downloaded: SSH in and `ls /ebs/nwbfiles/217706/`

### Conversion Failures

SSH into instance and check logs:

```bash
# Conversion logs
tail -f /ebs/temporary_files/conversion_log_*.log

# Bootstrap logs
sudo tail -f /var/log/cloud-init-output.log

# Check if Python script is running
ps aux | grep python
```

### Terminate All Instances (Emergency Stop)

```bash
aws ec2 terminate-instances --region us-east-2 \
    --instance-ids $(aws ec2 describe-instances --region us-east-2 \
        --filters "Name=tag:Project,Values=IBL-NWB-Conversion" "Name=instance-state-name,Values=running,pending" \
        --query 'Reservations[*].Instances[*].InstanceId' --output text)
```

---

## File Reference

### Core Scripts (You Run These)

| File | Purpose | When to Run |
|------|---------|-------------|
| `verify_aws_permissions.py` | Check you have required AWS permissions | Once (before testing) |
| `configure_networking.py` | Create dedicated VPC, subnets, security groups, S3 endpoint | Once (one-time setup) |
| `generate_assignments.py` | Create shard assignments | Each test/production run |
| `launch_ec2_instances.py` | Launch EC2 instances | Each test/production run |
| `quick_test.sh` | Automated test (runs steps 2-5) | Once (validates setup) |

### Support Files (Run on EC2 Automatically)

| File | Purpose |
|------|---------|
| `ec2_userdata_production.sh` | Bootstrap script (runs at instance boot) |
| `convert_assigned_sessions.py` | Worker script (converts sessions) |

### Configuration Files

| File | What to Change |
|------|----------------|
| `ec2_userdata_production.sh` | Repo branch (line 23), dandiset ID (line 122) |
| `convert_assigned_sessions.py` | Dandiset ID, revision, base paths |
| Environment variable | `export DANDI_API_KEY="your-key"` before launch |

### Documentation

| File | Content |
|------|---------|
| `IMDSV2_MIGRATION.md` | Technical details of IMDSv2 approach |
| `WORK_DISTRIBUTION_ANALYSIS.md` | Comparison of 4 distribution strategies |
| `RECOMMENDED_PERMISSIONS.md` | IAM policy for recurring use |
| **THIS FILE** | Main documentation |

---

## Configuration Summary

All hardcoded values (no CLI arguments needed):

| Setting | Value | Where to Change |
|---------|-------|-----------------|
| AWS Region | us-east-2 (Ohio) | `launch_ec2_instances.py:245`, `configure_networking.py:16` |
| Base Folder | /ebs | `convert_assigned_sessions.py:261` |
| Dandiset ID | 217706 | `convert_assigned_sessions.py:265` |
| DANDI Instance | dandi-staging | `convert_assigned_sessions.py:266` |
| Revision | 2024-05-06 | `convert_assigned_sessions.py:267` |
| Instance Type | t3.2xlarge | `launch_ec2_instances.py:216` |
| Spot Pricing | Enabled by default | Use `--use-on-demand` to disable |
| Assignment File | /ebs/chunk.json | `convert_assigned_sessions.py:47` |
| Output Directory | ./assignments | `generate_assignments.py:54` |
| Repo Branch | heberto_conversion | `ec2_userdata_production.sh:18` |

---

## Advanced Usage

### Launch Options

```bash
# Use on-demand instances (more expensive, guaranteed)
python launch_ec2_instances.py --num-instances 50 --use-on-demand

# Different instance type
python launch_ec2_instances.py --num-instances 50 --instance-type c6a.2xlarge

# Add SSH key for debugging
python launch_ec2_instances.py --num-instances 50 --key-name my-key-pair
```

### Instance Types Comparison

| Type | vCPUs | RAM | Network | Spot $/hr | Use Case |
|------|-------|-----|---------|-----------|----------|
| t3.2xlarge | 8 | 32 GB | 5 Gbps | ~$0.10 | Balanced (default) |
| c6a.2xlarge | 8 | 16 GB | 12.5 Gbps | ~$0.09 | CPU-heavy workloads |
| c6i.4xlarge | 16 | 32 GB | 12.5 Gbps | ~$0.20 | Faster parallel processing |

### Modify Conversion Settings

Edit `convert_assigned_sessions.py`:

```python
# Line 265-269: Hardcoded configuration
DANDISET_ID = "217706"           # Change dandiset
DANDI_INSTANCE = "dandi-staging" # Use "dandi" for production
REVISION = "2024-05-06"          # Change spike sorting revision
CONVERT_RAW = True               # Disable raw conversion
CONVERT_PROCESSED = True         # Disable processed conversion
```

### Save Logs to S3 (Optional)

Add to `ec2_userdata_production.sh` before shutdown:

```bash
# Before: shutdown -h now
# Add:
aws s3 sync "${MOUNT_POINT}/temporary_files" \
  "s3://your-bucket/logs/shard-${SHARD_ID}/" \
  --region us-east-2

shutdown -h now
```

---

## Security Best Practices

1. **No IAM Role Needed**: Instances don't need AWS API access (IMDSv2 approach)
2. **Secrets via User-Data Substitution**: DANDI API key embedded in user-data script at launch time
3. **Automatic Secret Cleanup**: User-data file shredded after key is read (set +x prevents logging)
4. **Restrict SSH Access**: Modify security group to only allow your IP
5. **Use Spot Instances**: 70-90% cost savings (enabled by default)
6. **S3 VPC Gateway Endpoint**: Free, required for S3 access
7. **Rotate API Keys**: Change DANDI API key periodically
8. **Tag-Based Permissions**: Use ABAC to restrict who can launch instances

---

## Technical Details

### Why IMDSv2 Instead of IAM Roles?

**Problem**: Attaching IAM roles requires `iam:PassRole` permission, which many users don't have (requires admin approval).

**Solution**: Use IMDSv2 instance metadata tags:
- Instances read their own ShardId tag via metadata service (no AWS API call)
- No IAM role needed on instances
- No `iam:PassRole` permission needed
- Unblocks users waiting for admin approval

**How It Works**:
1. You launch instance with tag: `ShardId=023`
2. You enable metadata tag access: `InstanceMetadataTags=enabled`
3. Instance reads its own tag via HTTP: `http://169.254.169.254/latest/meta-data/tags/instance/ShardId`
4. Instance downloads corresponding assignment: `chunk-023.json`

See [IMDSV2_MIGRATION.md](IMDSV2_MIGRATION.md) for technical details.

### Required Permissions

**For configure_networking.py (VPC setup)**:
- `ec2:CreateVpc`
- `ec2:CreateSubnet`
- `ec2:CreateInternetGateway`
- `ec2:AttachInternetGateway`
- `ec2:CreateRouteTable`
- `ec2:CreateRoute`
- `ec2:AssociateRouteTable`
- `ec2:CreateVpcEndpoint`
- `ec2:CreateSecurityGroup`
- `ec2:AuthorizeSecurityGroupIngress`
- `ec2:DescribeVpcs`
- `ec2:DescribeSubnets`
- `ec2:DescribeRouteTables`
- `ec2:DescribeVpcEndpoints`
- `ec2:DescribeSecurityGroups`
- `ec2:ModifyVpcAttribute`
- `ec2:ModifySubnetAttribute`

**For launch_ec2_instances.py (EC2 instances)**:
- `ec2:RunInstances`
- `ec2:CreateTags`
- `ec2:DescribeImages`

**Total: 20 EC2 permissions, 0 IAM permissions**

Verify with: `python verify_aws_permissions.py`

---

## What Happens During Execution

### Bootstrap Sequence (ec2_userdata_production.sh)

```bash
1. Mount EBS volume at /ebs (400GB data storage)
2. Install system dependencies (git, curl, ca-certificates)
3. Install uv (Python package manager)
4. Clone IBL-to-nwb repository (branch: heberto_conversion)
5. Install dandi-cli
6. Download dandiset.yaml from DANDI:217706
7. Read ShardId from instance tags via IMDSv2
8. Download assignment file (chunk-{ShardId}.json)
9. Run conversion script
10. Move NWB files to dandiset folder
11. Upload to DANDI
12. Shutdown instance
```

### Conversion Sequence (convert_assigned_sessions.py)

For each session in assignment file:
```python
1. Download session data from ONE API
2. Convert to raw NWB → /ebs/nwbfiles/full/sub-{subject}/
3. Convert to processed NWB → /ebs/nwbfiles/full/sub-{subject}/
4. (Repeat for all 9 sessions)
```

### Upload Sequence (ec2_userdata_production.sh)

```bash
1. Move all sub-* folders to /ebs/nwbfiles/217706/
   (filesystem metadata operation, instant)
2. cd /ebs/nwbfiles/217706
3. dandi upload -i dandi-staging
   (uploads all NWB files in batch)
```

---

## Support

For issues or questions:
1. Check this README and linked documentation
2. Check [IMDSV2_MIGRATION.md](IMDSV2_MIGRATION.md) for technical details
3. Open an issue on the IBL-to-nwb GitHub repository
4. Contact the development team

---

## Next Steps After Successful Run

1. Validate uploads on DANDI staging
2. Run post-conversion checks
3. Generate summary statistics from batch JSON files
4. Archive logs for audit trail
5. Terminate stopped instances (optional, they're not costing money when stopped)
6. Delete VPC endpoint if no longer needed (optional, it's free)

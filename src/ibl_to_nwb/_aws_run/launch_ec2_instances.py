"""Launch EC2 instances for distributed IBL NWB conversion.

This script launches N EC2 instances in us-east-2, each tagged with a unique ShardId
and ShardRange (e.g., "0-13") for range-based session assignment.

Prerequisites:
    - AWS CLI configured with appropriate credentials
    - DANDI API key configured in network_config.env
    - ec2:RunInstances permission (no IAM role needed with IMDSv2!)

Usage:
    python launch_ec2_instances.py --num-instances 50 --instance-type t3.2xlarge
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging for the script."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)


def load_network_config(config_path: Path) -> dict:
    """Load network configuration from .env file.

    Returns dict with keys: VPC_ID, SUBNET_ID, SECURITY_GROUP_ID, REGION
    Returns empty dict if file doesn't exist.
    """
    if not config_path.exists():
        return {}

    config = {}
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()

    return config


def read_user_data_script(script_path: Path, dandi_api_key: str) -> str:
    """Read user-data script template and substitute DANDI API key."""
    if not script_path.exists():
        raise FileNotFoundError(f"User-data script not found: {script_path}")

    template = script_path.read_text()
    return template.replace("{{DANDI_API_KEY}}", dandi_api_key)


def get_latest_ubuntu_ami(ec2_client, region: str = "us-east-2") -> str:
    """Find the latest Ubuntu 22.04 LTS AMI."""
    logger = logging.getLogger(__name__)

    response = ec2_client.describe_images(
        Filters=[
            {"Name": "name", "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]},
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
            {"Name": "virtualization-type", "Values": ["hvm"]},
        ],
        Owners=["099720109477"],  # Canonical's AWS account ID
    )

    if not response["Images"]:
        raise RuntimeError("No Ubuntu 22.04 AMI found")

    # Sort by creation date and get the most recent
    images = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)
    ami_id = images[0]["ImageId"]

    logger.info(f"Using Ubuntu AMI: {ami_id} ({images[0]['Name']})")
    return ami_id


def create_security_group(ec2_client, group_name: str, description: str, vpc_id: Optional[str] = None) -> str:
    """Create a security group that allows SSH access."""
    logger = logging.getLogger(__name__)

    try:
        # Check if security group already exists
        response = ec2_client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [group_name]}]
        )

        if response["SecurityGroups"]:
            sg_id = response["SecurityGroups"][0]["GroupId"]
            logger.info(f"Using existing security group: {sg_id}")
            return sg_id

    except ClientError:
        pass

    # Create new security group
    kwargs = {"GroupName": group_name, "Description": description}
    if vpc_id:
        kwargs["VpcId"] = vpc_id

    response = ec2_client.create_security_group(**kwargs)
    sg_id = response["GroupId"]

    # Add SSH ingress rule (optional - only if you need to debug)
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # WARNING: Open to world. Restrict in production!
            }
        ],
    )

    logger.info(f"Created security group: {sg_id}")
    return sg_id


def launch_instances(
    ec2_client,
    ami_id: str,
    instance_type: str,
    security_group_id: str,
    user_data: str,
    num_instances: int,
    ebs_volume_size: int,
    total_sessions: int = 699,
    use_spot: bool = True,
    key_name: Optional[str] = None,
    subnet_id: Optional[str] = None,
) -> list[str]:
    """Launch EC2 instances with specified configuration.

    Args:
        total_sessions: Total number of sessions in bwm_df.pqt fixtures (default: 699)
    """
    logger = logging.getLogger(__name__)

    instance_ids = []
    sessions_per_shard = total_sessions // num_instances

    for i in range(1, num_instances + 1):
        shard_id = f"{i:03d}"  # Format as 001, 002, etc.

        # Calculate session range for this shard
        start_idx = (i - 1) * sessions_per_shard
        # Last shard gets any remaining sessions
        if i == num_instances:
            end_idx = total_sessions - 1
        else:
            end_idx = start_idx + sessions_per_shard - 1

        shard_range = f"{start_idx}-{end_idx}"

        logger.info(f"Launching instance {i}/{num_instances} for shard {shard_id} (sessions {shard_range})...")

        # Prepare launch parameters
        launch_params = {
            "ImageId": ami_id,
            "InstanceType": instance_type,
            "MinCount": 1,
            "MaxCount": 1,
            "SecurityGroupIds": [security_group_id],
            "UserData": user_data,
            "MetadataOptions": {
                "HttpTokens": "required",  # Require IMDSv2 (more secure)
                "InstanceMetadataTags": "enabled",  # Enable tag access via metadata
            },
            "BlockDeviceMappings": [
                {
                    "DeviceName": "/dev/sda1",  # Root volume
                    "Ebs": {
                        "VolumeSize": 50,  # GB
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True,
                    },
                },
                {
                    "DeviceName": "/dev/sdf",  # Additional EBS volume for data
                    "Ebs": {
                        "VolumeSize": ebs_volume_size,
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True,
                        "Iops": 3000,
                        "Throughput": 125,
                    },
                },
            ],
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": f"ibl-conversion-shard-{shard_id}"},
                        {"Key": "ShardId", "Value": shard_id},
                        {"Key": "ShardRange", "Value": shard_range},
                        {"Key": "Project", "Value": "IBL-NWB-Conversion"},
                    ],
                }
            ],
        }

        if key_name:
            launch_params["KeyName"] = key_name

        if subnet_id:
            launch_params["SubnetId"] = subnet_id

        if use_spot:
            # Use Spot instances for cost savings
            launch_params["InstanceMarketOptions"] = {
                "MarketType": "spot",
                "SpotOptions": {
                    "MaxPrice": "1.00",  # Maximum price per hour (on-demand is ~$0.33)
                    "SpotInstanceType": "one-time",
                    "InstanceInterruptionBehavior": "terminate",
                },
            }

        try:
            response = ec2_client.run_instances(**launch_params)
            instance_id = response["Instances"][0]["InstanceId"]
            instance_ids.append(instance_id)
            logger.info(f"  Launched instance: {instance_id}")

        except ClientError as e:
            logger.error(f"  Failed to launch instance for shard {shard_id}: {e}")
            continue

    return instance_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch EC2 instances for distributed IBL conversion"
    )
    parser.add_argument(
        "--num-instances",
        type=int,
        required=True,
        help="Number of EC2 instances to launch",
    )
    parser.add_argument(
        "--instance-type",
        default="t3.2xlarge",
        help="EC2 instance type (default: t3.2xlarge)",
    )
    parser.add_argument(
        "--stub-test",
        action="store_true",
        help="Use smaller storage for stub testing (100GB instead of 400GB)",
    )
    parser.add_argument(
        "--key-name",
        help="SSH key pair name (optional, for debugging)",
    )
    parser.add_argument(
        "--use-on-demand",
        action="store_true",
        help="Use on-demand instances instead of Spot",
    )
    parser.add_argument(
        "--vpc-id",
        help="VPC ID (from configure_networking.py output)",
    )
    parser.add_argument(
        "--subnet-id",
        help="Subnet ID (from configure_networking.py output)",
    )
    parser.add_argument(
        "--security-group-id",
        help="Security group ID (from configure_networking.py output)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = setup_logging("INFO")

    # Hardcoded configuration
    REGION = "us-east-2"
    SECURITY_GROUP_NAME = "ibl-conversion-sg"
    USER_DATA_SCRIPT = Path(__file__).parent / "ec2_userdata_production.sh"
    EBS_VOLUME_SIZE = 100 if args.stub_test else 400  # 100GB for testing, 400GB for production

    # Load network config from file if not provided via CLI
    CONFIG_FILE = Path(__file__).parent / "network_config.env"
    network_config = load_network_config(CONFIG_FILE)

    # Use CLI arguments if provided, otherwise fall back to config file
    vpc_id = args.vpc_id or network_config.get("VPC_ID")
    subnet_id = args.subnet_id or network_config.get("SUBNET_ID")
    security_group_id = args.security_group_id or network_config.get("SECURITY_GROUP_ID")

    # Get DANDI API key from environment variable or config file
    dandi_api_key = os.environ.get("DANDI_API_KEY") or network_config.get("DANDI_API_KEY")
    if not dandi_api_key:
        logger.error("ERROR: DANDI_API_KEY not found")
        logger.error("Please set it in one of these ways:")
        logger.error("  1. Add to network_config.env: DANDI_API_KEY=your-key")
        logger.error("  2. Set environment variable: export DANDI_API_KEY='your-key'")
        raise SystemExit(1)

    logger.info("=" * 80)
    logger.info("EC2 INSTANCE LAUNCHER FOR IBL CONVERSION")
    logger.info("=" * 80)
    logger.info(f"Number of instances: {args.num_instances}")
    logger.info(f"Instance type: {args.instance_type}")
    logger.info(f"EBS volume size: {EBS_VOLUME_SIZE} GB")
    logger.info(f"Region: {REGION}")
    logger.info(f"Using Spot: {not args.use_on_demand}")
    logger.info(f"Mode: {'STUB TEST' if args.stub_test else 'PRODUCTION'}")
    if network_config:
        logger.info(f"Network config: Loaded from {CONFIG_FILE}")
        logger.info(f"  VPC ID: {vpc_id or 'default VPC'}")
        logger.info(f"  Subnet ID: {subnet_id or 'default subnet'}")
        logger.info(f"  Security Group: {security_group_id or 'will create'}")
    logger.info("=" * 80)

    # Initialize AWS client
    ec2_client = boto3.client("ec2", region_name=REGION)

    # Read user-data script and substitute DANDI API key
    logger.info("Reading user-data script and substituting DANDI API key...")
    user_data = read_user_data_script(USER_DATA_SCRIPT, dandi_api_key)

    # Get AMI
    logger.info("Finding latest Ubuntu 22.04 AMI...")
    ami_id = get_latest_ubuntu_ami(ec2_client, REGION)

    # Use provided/configured security group or create new one
    if security_group_id:
        logger.info(f"Using security group: {security_group_id}")
        sg_id = security_group_id
    else:
        logger.info("Creating security group...")
        sg_id = create_security_group(
            ec2_client,
            SECURITY_GROUP_NAME,
            "Security group for IBL NWB conversion instances",
            vpc_id=vpc_id,  # Will be None if not configured, uses default VPC
        )

    # Launch instances
    logger.info(f"\nLaunching {args.num_instances} instances...")
    instance_ids = launch_instances(
        ec2_client=ec2_client,
        ami_id=ami_id,
        instance_type=args.instance_type,
        security_group_id=sg_id,
        user_data=user_data,
        num_instances=args.num_instances,
        ebs_volume_size=EBS_VOLUME_SIZE,
        use_spot=not args.use_on_demand,
        key_name=args.key_name,
        subnet_id=subnet_id,  # From config file or CLI
    )

    logger.info("\n" + "=" * 80)
    logger.info("LAUNCH COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Successfully launched {len(instance_ids)} instances")
    logger.info(f"Failed to launch {args.num_instances - len(instance_ids)} instances")
    logger.info("\nInstance IDs:")
    for instance_id in instance_ids:
        logger.info(f"  {instance_id}")
    logger.info("\nMonitor instance status with:")
    logger.info(f"  aws ec2 describe-instances --instance-ids {' '.join(instance_ids)} --region {REGION}")
    logger.info("=" * 80)


if __name__ == "__main__":
    sys.exit(main())

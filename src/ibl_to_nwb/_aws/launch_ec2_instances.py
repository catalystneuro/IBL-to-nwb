"""Launch EC2 instances for distributed IBL NWB conversion.

This script launches EC2 instances with ONE SESSION PER INSTANCE for simplified
distribution and tracking. Each instance converts a single IBL session to NWB format.

Prerequisites:
    - AWS CLI configured with appropriate credentials
    - Profile config created via setup_infrastructure.py
    - DANDI API key configured in profiles/{profile}.env

Usage:
    # Test with first session in stub mode
    python launch_ec2_instances.py --profile catalyst_neuro --range 0-0 --stub-test

    # Launch sessions 0-9 (first 10 sessions)
    python launch_ec2_instances.py --profile ibl --range 0-9

    # Launch all 459 sessions
    python launch_ec2_instances.py --profile catalyst_neuro --all
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging for the script."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger(__name__)


def load_profile_config(config_path: Path) -> dict:
    """Load profile configuration from .env file.

    Returns dict with keys: VPC_ID, SUBNET_ID, SECURITY_GROUP_ID, REGION, DANDI_API_KEY, etc.
    Raises SystemExit if file doesn't exist or required keys are missing.
    """
    if not config_path.exists():
        raise SystemExit(f"ERROR: Profile config not found: {config_path}")

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

    # Validate required keys
    required_keys = ["VPC_ID", "SUBNET_ID", "SECURITY_GROUP_ID", "REGION", "DANDI_API_KEY"]
    missing = [k for k in required_keys if not config.get(k) or config[k] == "your-dandi-api-key-here"]

    if missing:
        raise SystemExit(
            f"ERROR: Missing required configuration in {config_path}:\n"
            f"  {', '.join(missing)}\n\n"
            f"Run setup_infrastructure.py first, then edit the config to set your DANDI API key."
        )

    return config


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


def load_session_eids(json_path: Path) -> list[str]:
    """Load unique session EIDs from bwm_session_eids.json."""
    if not json_path.exists():
        raise SystemExit(f"ERROR: Session EIDs file not found: {json_path}")

    with open(json_path) as f:
        data = json.load(f)

    return data["eids"]


def get_session_info(one, eid: str) -> dict:
    """Get session metadata for naming."""
    try:
        session_info = one.get_details(eid, full=True)
        subject = session_info["subject"]
        date = session_info["start_time"][:10]  # YYYY-MM-DD
        number = session_info["number"]
        return {
            "subject": subject,
            "date": date,
            "number": f"{number:03d}",
            "display_name": f"{subject}_{date}_{number:03d}",
        }
    except Exception:
        # Fallback if ONE API fails
        return {
            "subject": "unknown",
            "date": "unknown",
            "number": "000",
            "display_name": f"session_{eid[:8]}",
        }


def launch_instance(
    ec2_client,
    ami_id: str,
    instance_type: str,
    security_group_id: str,
    subnet_id: str,
    user_data: str,
    eid: str,
    index: int,
    session_info: dict,
    ebs_volume_size: int,
    stub_test: bool,
    key_name: str | None = None,
) -> str:
    """
    Launch a single EC2 instance to process one session.

    Parameters
    ----------
    ec2_client : boto3.client
        Boto3 EC2 client for AWS operations.
    ami_id : str
        Amazon Machine Image ID to use.
    instance_type : str
        EC2 instance type (e.g., 'm6a.2xlarge').
    security_group_id : str
        Security group ID to assign.
    subnet_id : str
        Subnet ID to launch in.
    user_data : str
        User data script to run on instance startup.
    eid : str
        Session EID to process.
    index : int
        Index in bwm_session_eids.json (0-458).
    session_info : dict
        Session metadata (subject, date, number).
    ebs_volume_size : int
        Size in GB for the additional EBS data volume.
    stub_test : bool
        If True, tags instance for stub testing.
    key_name : str, optional
        EC2 key pair name for SSH access.

    Returns
    -------
    str
        Instance ID of the launched instance.
    """
    logger = logging.getLogger(__name__)

    instance_name = f"ibl-conversion-{session_info['display_name']}"

    logger.info(f"Launching instance for session {index}: {eid}")
    logger.info(f"  Instance name: {instance_name}")

    # Prepare launch parameters
    launch_params = {
        "ImageId": ami_id,
        "InstanceType": instance_type,
        "MinCount": 1,
        "MaxCount": 1,
        "SecurityGroupIds": [security_group_id],
        "SubnetId": subnet_id,
        "UserData": user_data,
        "InstanceInitiatedShutdownBehavior": "terminate",  # Auto-terminate on shutdown (not stop)
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
                    {"Key": "Name", "Value": instance_name},
                    {"Key": "SessionEID", "Value": eid},
                    {"Key": "SessionIndex", "Value": str(index)},
                    {"Key": "Subject", "Value": session_info["subject"]},
                    {"Key": "SessionDate", "Value": session_info["date"]},
                    {"Key": "StubTest", "Value": "true" if stub_test else "false"},
                    {"Key": "Project", "Value": "IBL-NWB-Conversion"},
                ],
            }
        ],
    }

    if key_name:
        launch_params["KeyName"] = key_name

    # Launch instance - let exceptions propagate to caller
    response = ec2_client.run_instances(**launch_params)
    instance_id = response["Instances"][0]["InstanceId"]

    logger.info(f"  ✓ Launched instance: {instance_id}")
    return instance_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch EC2 instances for distributed IBL conversion (one session per instance)"
    )
    parser.add_argument(
        "--profile",
        choices=["catalyst_neuro", "ibl"],
        required=True,
        help="AWS profile to use (determines network config and credentials)",
    )

    # Session selection (mutually exclusive)
    session_group = parser.add_mutually_exclusive_group(required=True)
    session_group.add_argument(
        "--all",
        action="store_true",
        help="Launch all 459 sessions (one instance per session)",
    )
    session_group.add_argument(
        "--range",
        type=str,
        metavar="START-END",
        help="Launch sessions from START (inclusive) to END (exclusive), like Python slicing. Example: --range 0-10 launches 10 sessions (indices 0-9)",
    )

    # Optional arguments
    parser.add_argument(
        "--stub-test",
        action="store_true",
        help="Use smaller storage for stub testing (100GB instead of 700GB)",
    )
    parser.add_argument(
        "--instance-type",
        default="m6a.2xlarge",
        help="EC2 instance type (default: m6a.2xlarge - best value AMD EPYC 3rd gen)",
    )
    parser.add_argument(
        "--key-name",
        help="SSH key pair name (optional, for debugging)",
    )
    parser.add_argument(
        "--dandi-instance",
        choices=["dandi", "dandi-sandbox"],
        default="dandi-sandbox",
        help="DANDI instance to upload to: 'dandi' for production (dandiarchive.org) or 'dandi-sandbox' for testing. Default: dandi-sandbox",
    )
    parser.add_argument(
        "--dandiset-id",
        default="217706",
        help="Dandiset ID to upload to (default: 217706 for sandbox, use 000409 for production)",
    )

    # Conversion mode selection (mutually exclusive)
    conversion_mode = parser.add_mutually_exclusive_group()
    conversion_mode.add_argument(
        "--raw-only",
        action="store_true",
        help="Convert only raw electrophysiology data (skip processed).",
    )
    conversion_mode.add_argument(
        "--processed-only",
        action="store_true",
        help="Convert only processed behavior+ecephys data (skip raw). Saves ~100 GB download per session.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = setup_logging("INFO")

    # Load profile configuration
    profile_path = Path(__file__).parent / "profiles" / f"{args.profile}.env"
    config = load_profile_config(profile_path)

    # Hardcoded configuration
    USER_DATA_SCRIPT = Path(__file__).parent / "ec2_userdata_production.sh"
    EBS_VOLUME_SIZE = 100 if args.stub_test else 700  # 100GB for testing, 700GB for production
    EIDS_JSON_PATH = Path(__file__).parent / "bwm_session_eids.json"

    logger.info("=" * 80)
    logger.info("EC2 INSTANCE LAUNCHER FOR IBL CONVERSION (ONE SESSION PER INSTANCE)")
    logger.info("=" * 80)
    logger.info(f"Profile: {args.profile}")
    logger.info(f"Region: {config['REGION']}")
    logger.info(f"VPC: {config['VPC_ID']}")
    logger.info(f"Subnet: {config['SUBNET_ID']}")
    logger.info(f"Security Group: {config['SECURITY_GROUP_ID']}")
    logger.info(f"Instance type: {args.instance_type}")
    logger.info(f"EBS volume size: {EBS_VOLUME_SIZE} GB")
    logger.info(f"Mode: {'STUB TEST' if args.stub_test else 'PRODUCTION'}")
    if args.raw_only:
        logger.info("Conversion mode: RAW ONLY (skipping processed)")
    elif args.processed_only:
        logger.info("Conversion mode: PROCESSED ONLY (skipping raw, saves ~100 GB/session)")
    else:
        logger.info("Conversion mode: BOTH (raw + processed)")
    logger.info(f"DANDI instance: {args.dandi_instance}")
    logger.info(f"Dandiset ID: {args.dandiset_id}")
    logger.info("=" * 80)

    # Load session EIDs
    all_eids = load_session_eids(EIDS_JSON_PATH)
    total_available = len(all_eids)
    logger.info(f"Total sessions available: {total_available}")

    # Parse session selection
    if args.all:
        selected_indices = list(range(total_available))
        logger.info(f"Launching ALL {total_available} sessions")
    else:
        # Parse range "START-END" (Python-style: start inclusive, end exclusive)
        try:
            start_str, end_str = args.range.split("-")
            start_idx = int(start_str)
            end_idx = int(end_str)
        except (ValueError, AttributeError):
            raise SystemExit(f"ERROR: Invalid range format '{args.range}'. Expected format: START-END (e.g., 0-10)")

        # Validate range (end is exclusive, so end can equal total_available)
        if start_idx < 0 or end_idx > total_available or start_idx >= end_idx:
            raise SystemExit(
                f"ERROR: Invalid range {start_idx}-{end_idx} for {total_available} sessions. "
                f"Valid range: 0-{total_available} (end is exclusive)"
            )

        selected_indices = list(range(start_idx, end_idx))  # Python slice: end is exclusive
        logger.info(f"Launching sessions [{start_idx}:{end_idx}): {len(selected_indices)} sessions (indices {start_idx}-{end_idx-1})")

    selected_eids = [(i, all_eids[i]) for i in selected_indices]

    logger.info("=" * 80)

    # Read user-data script and substitute DANDI API key
    logger.info("Reading user-data script and substituting DANDI API key...")
    if not USER_DATA_SCRIPT.exists():
        raise FileNotFoundError(f"User-data script not found: {USER_DATA_SCRIPT}")

    template = USER_DATA_SCRIPT.read_text()
    # Use the appropriate DANDI API key based on instance
    if args.dandi_instance == "dandi":
        dandi_api_key = config["DANDI_API_KEY"]
    else:
        dandi_api_key = config.get("DANDI_SANDBOX_API_KEY", config["DANDI_API_KEY"])
    user_data = template.replace("{{DANDI_API_KEY}}", dandi_api_key)
    user_data = user_data.replace("{{REPO_URL}}", config.get("REPO_URL", "https://github.com/h-mayorquin/IBL-to-nwb.git"))
    user_data = user_data.replace("{{REPO_BRANCH}}", config.get("REPO_BRANCH", "heberto_conversion"))
    user_data = user_data.replace("{{DANDISET_ID}}", args.dandiset_id)
    user_data = user_data.replace("{{DANDI_INSTANCE}}", args.dandi_instance)

    # Determine conversion mode flag
    if args.raw_only:
        conversion_mode = "--raw-only"
    elif args.processed_only:
        conversion_mode = "--processed-only"
    else:
        conversion_mode = ""  # Default: convert both
    user_data = user_data.replace("{{CONVERSION_MODE}}", conversion_mode)

    # Initialize AWS client
    ec2_client = boto3.client("ec2", region_name=config["REGION"])

    # Get AMI
    logger.info("Finding latest Ubuntu 22.04 AMI...")
    ami_id = get_latest_ubuntu_ami(ec2_client, config["REGION"])

    # Initialize ONE API for session metadata (optional, for better naming)
    try:
        from one.api import ONE

        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)
        logger.info("✓ Connected to ONE API for session metadata")
        use_one = True
    except Exception as e:
        logger.warning(f"Could not connect to ONE API (will use EID for naming): {e}")
        one = None
        use_one = False

    # Launch instances
    logger.info(f"\nLaunching {len(selected_eids)} instances...")
    logger.info("=" * 80)

    instance_ids = []
    failed_launches = []

    for i, (index, eid) in enumerate(selected_eids, start=1):
        logger.info(f"\n[{i}/{len(selected_eids)}] Session index {index}: {eid}")

        # Get session metadata for naming
        if use_one:
            session_info = get_session_info(one, eid)
        else:
            session_info = {
                "subject": "unknown",
                "date": "unknown",
                "number": "000",
                "display_name": f"session_{eid[:8]}",
            }

        try:
            instance_id = launch_instance(
                ec2_client=ec2_client,
                ami_id=ami_id,
                instance_type=args.instance_type,
                security_group_id=config["SECURITY_GROUP_ID"],
                subnet_id=config["SUBNET_ID"],
                user_data=user_data,
                eid=eid,
                index=index,
                session_info=session_info,
                ebs_volume_size=EBS_VOLUME_SIZE,
                stub_test=args.stub_test,
                key_name=args.key_name,
            )
            instance_ids.append(instance_id)
        except ClientError as e:
            logger.error(f"  ✗ Failed to launch instance: {e}")
            failed_launches.append((index, eid))

    logger.info("\n" + "=" * 80)
    logger.info("LAUNCH COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Successfully launched: {len(instance_ids)} instances")
    logger.info(f"Failed to launch: {len(failed_launches)} instances")

    if instance_ids:
        logger.info("\nInstance IDs:")
        for instance_id in instance_ids[:10]:  # Show first 10
            logger.info(f"  {instance_id}")
        if len(instance_ids) > 10:
            logger.info(f"  ... and {len(instance_ids) - 10} more")

    if failed_launches:
        logger.info("\nFailed sessions:")
        for index, eid in failed_launches:
            logger.info(f"  Index {index}: {eid}")

    logger.info("\nMonitoring:")
    logger.info("  Real-time monitoring:  python monitor.py")
    logger.info("  Instance logs:         python monitor.py --logs INSTANCE_ID")
    logger.info("\nVerification (after completion):")
    logger.info(f"  python verify_dandi_uploads.py --dandiset-id {args.dandiset_id} --dandi-instance {args.dandi_instance}")
    logger.info("=" * 80)


if __name__ == "__main__":
    sys.exit(main())

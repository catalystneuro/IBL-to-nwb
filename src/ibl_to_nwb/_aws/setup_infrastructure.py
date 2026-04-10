"""Configure dedicated VPC networking for IBL NWB conversion.

Creates an isolated network environment with:
  - VPC (10.50.0.0/16)
  - Public subnet (10.50.1.0/24)
  - Internet Gateway (for GitHub, DANDI access)
  - Route table (with internet and S3 routes)
  - S3 VPC Gateway Endpoint (FREE, keeps S3 traffic within AWS)
  - Security Group (SSH access for debugging)

This is idempotent - safe to run multiple times.
Existing resources are reused if found.

Usage:
    python setup_infrastructure.py --profile catalyst_neuro
    python setup_infrastructure.py --profile ibl

Output:
    Updates the profile config file with network IDs
"""

import argparse
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Hardcoded configuration
REGION = "us-east-2"
VPC_CIDR = "10.50.0.0/16"
SUBNET_CIDR = "10.50.1.0/24"
PROJECT_TAG = "IBL-NWB-Conversion"


def get_resource_names(profile: str) -> dict:
    """Get resource names based on profile."""
    prefix = f"ibl-conversion-{profile}"
    return {
        "vpc": f"{prefix}-vpc",
        "subnet": f"{prefix}-public-subnet",
        "igw": f"{prefix}-igw",
        "route_table": f"{prefix}-route-table",
        "s3_endpoint": f"{prefix}-s3-endpoint",
        "security_group": f"{prefix}-sg",
    }


def create_or_get_vpc(ec2_client, vpc_name):
    """Create VPC or return existing one."""
    print("Checking for existing VPC...")

    # Check if VPC already exists
    response = ec2_client.describe_vpcs(
        Filters=[
            {"Name": "tag:Name", "Values": [vpc_name]},
            {"Name": "tag:Project", "Values": [PROJECT_TAG]},
        ]
    )

    if response["Vpcs"]:
        vpc_id = response["Vpcs"][0]["VpcId"]
        print(f"✓ Using existing VPC: {vpc_id}")
        return vpc_id

    # Create new VPC
    print(f"Creating VPC with CIDR {VPC_CIDR}...")
    response = ec2_client.create_vpc(
        CidrBlock=VPC_CIDR,
        TagSpecifications=[
            {
                "ResourceType": "vpc",
                "Tags": [
                    {"Key": "Name", "Value": vpc_name},
                    {"Key": "Project", "Value": PROJECT_TAG},
                ],
            }
        ],
    )
    vpc_id = response["Vpc"]["VpcId"]

    # Enable DNS hostnames (required for EC2 instances to get public DNS)
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})

    print(f"✓ Created VPC: {vpc_id}")
    return vpc_id


def create_or_get_subnet(ec2_client, vpc_id, subnet_name):
    """Create public subnet or return existing one."""
    print("Checking for existing subnet...")

    # Check if subnet already exists
    response = ec2_client.describe_subnets(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:Name", "Values": [subnet_name]},
        ]
    )

    if response["Subnets"]:
        subnet_id = response["Subnets"][0]["SubnetId"]
        print(f"✓ Using existing subnet: {subnet_id}")
        return subnet_id

    # Create new subnet
    print(f"Creating public subnet with CIDR {SUBNET_CIDR}...")
    response = ec2_client.create_subnet(
        VpcId=vpc_id,
        CidrBlock=SUBNET_CIDR,
        AvailabilityZone=f"{REGION}a",  # Use first AZ in region
        TagSpecifications=[
            {
                "ResourceType": "subnet",
                "Tags": [
                    {"Key": "Name", "Value": subnet_name},
                    {"Key": "Project", "Value": PROJECT_TAG},
                ],
            }
        ],
    )
    subnet_id = response["Subnet"]["SubnetId"]

    # Enable auto-assign public IP (instances get public IPs automatically)
    ec2_client.modify_subnet_attribute(SubnetId=subnet_id, MapPublicIpOnLaunch={"Value": True})

    print(f"✓ Created subnet: {subnet_id}")
    return subnet_id


def create_or_get_internet_gateway(ec2_client, vpc_id, igw_name):
    """Create Internet Gateway and attach to VPC, or return existing one."""
    print("Checking for existing Internet Gateway...")

    # Check if IGW already exists
    response = ec2_client.describe_internet_gateways(
        Filters=[
            {"Name": "tag:Name", "Values": [igw_name]},
            {"Name": "attachment.vpc-id", "Values": [vpc_id]},
        ]
    )

    if response["InternetGateways"]:
        igw_id = response["InternetGateways"][0]["InternetGatewayId"]
        print(f"✓ Using existing Internet Gateway: {igw_id}")
        return igw_id

    # Create new IGW
    print("Creating Internet Gateway...")
    response = ec2_client.create_internet_gateway(
        TagSpecifications=[
            {
                "ResourceType": "internet-gateway",
                "Tags": [
                    {"Key": "Name", "Value": igw_name},
                    {"Key": "Project", "Value": PROJECT_TAG},
                ],
            }
        ]
    )
    igw_id = response["InternetGateway"]["InternetGatewayId"]

    # Attach to VPC
    ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)

    print(f"✓ Created and attached Internet Gateway: {igw_id}")
    return igw_id


def create_or_get_route_table(ec2_client, vpc_id, subnet_id, igw_id, route_table_name):
    """Create route table with internet route, or return existing one."""
    print("Checking for existing route table...")

    # Check if custom route table already exists
    response = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:Name", "Values": [route_table_name]},
        ]
    )

    if response["RouteTables"]:
        route_table_id = response["RouteTables"][0]["RouteTableId"]
        print(f"✓ Using existing route table: {route_table_id}")
        return route_table_id

    # Create new route table
    print("Creating route table...")
    response = ec2_client.create_route_table(
        VpcId=vpc_id,
        TagSpecifications=[
            {
                "ResourceType": "route-table",
                "Tags": [
                    {"Key": "Name", "Value": route_table_name},
                    {"Key": "Project", "Value": PROJECT_TAG},
                ],
            }
        ],
    )
    route_table_id = response["RouteTable"]["RouteTableId"]

    # Add route to internet gateway (0.0.0.0/0 -> IGW)
    ec2_client.create_route(RouteTableId=route_table_id, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id)

    # Associate route table with subnet
    ec2_client.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)

    print(f"✓ Created route table with internet route: {route_table_id}")
    return route_table_id


def create_or_get_s3_endpoint(ec2_client, vpc_id, route_table_id, endpoint_name):
    """Create S3 VPC Gateway Endpoint or return existing one."""
    print("Checking for existing S3 VPC endpoint...")

    service_name = f"com.amazonaws.{REGION}.s3"

    # Check if endpoint already exists
    response = ec2_client.describe_vpc_endpoints(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "service-name", "Values": [service_name]},
        ]
    )

    if response["VpcEndpoints"]:
        endpoint_id = response["VpcEndpoints"][0]["VpcEndpointId"]
        print(f"✓ Using existing S3 VPC endpoint: {endpoint_id}")
        return endpoint_id

    # Create new S3 endpoint
    print("Creating S3 VPC Gateway Endpoint (FREE)...")
    response = ec2_client.create_vpc_endpoint(
        VpcId=vpc_id,
        ServiceName=service_name,
        RouteTableIds=[route_table_id],
        VpcEndpointType="Gateway",
        TagSpecifications=[
            {
                "ResourceType": "vpc-endpoint",
                "Tags": [
                    {"Key": "Name", "Value": endpoint_name},
                    {"Key": "Project", "Value": PROJECT_TAG},
                ],
            }
        ],
    )
    endpoint_id = response["VpcEndpoint"]["VpcEndpointId"]

    print(f"✓ Created S3 VPC endpoint: {endpoint_id}")
    return endpoint_id


def create_or_get_security_group(ec2_client, vpc_id, sg_name):
    """Create security group with SSH access or return existing one."""
    print("Checking for existing security group...")

    # Check if security group already exists
    try:
        response = ec2_client.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [sg_name]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        )

        if response["SecurityGroups"]:
            sg_id = response["SecurityGroups"][0]["GroupId"]
            print(f"✓ Using existing security group: {sg_id}")
            return sg_id
    except ClientError:
        pass

    # Create new security group
    print("Creating security group...")
    response = ec2_client.create_security_group(
        GroupName=sg_name,
        Description="Security group for IBL NWB conversion instances",
        VpcId=vpc_id,
        TagSpecifications=[
            {
                "ResourceType": "security-group",
                "Tags": [
                    {"Key": "Name", "Value": sg_name},
                    {"Key": "Project", "Value": PROJECT_TAG},
                ],
            }
        ],
    )
    sg_id = response["GroupId"]

    # Add SSH ingress rule (for debugging)
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH from anywhere (debugging)"}],
            }
        ],
    )

    print(f"✓ Created security group: {sg_id}")
    print("  ⚠️  SSH (port 22) open to 0.0.0.0/0 - restrict to your IP in production!")
    return sg_id


def load_profile_config(profile_path: Path) -> dict:
    """Load existing profile configuration."""
    if not profile_path.exists():
        return {}

    config = {}
    with open(profile_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config


def save_profile_config(profile_path: Path, config: dict) -> None:
    """Save profile configuration."""
    with open(profile_path, "w") as f:
        f.write(f"# {config.get('PROFILE', 'Unknown')} AWS Account Configuration\n")
        f.write("# Generated by unified AWS infrastructure setup\n")
        f.write("#\n")
        f.write("# WARNING: This file contains secrets (DANDI_API_KEY)\n")
        f.write("# DO NOT COMMIT TO GIT - File is gitignored for safety\n")
        f.write("#\n")
        f.write("# Network IDs (safe, not secrets):\n")
        f.write(f"VPC_ID={config['VPC_ID']}\n")
        f.write(f"SUBNET_ID={config['SUBNET_ID']}\n")
        f.write(f"SECURITY_GROUP_ID={config['SECURITY_GROUP_ID']}\n")
        f.write(f"REGION={config['REGION']}\n")
        f.write("\n")
        f.write("# Secret (NEVER commit to git):\n")
        if config.get("DANDI_API_KEY"):
            f.write(f"DANDI_API_KEY={config['DANDI_API_KEY']}\n")
        else:
            f.write("DANDI_API_KEY=your-dandi-api-key-here\n")
        f.write("\n")
        f.write("# Repository configuration:\n")
        f.write(f"REPO_URL={config.get('REPO_URL', 'https://github.com/h-mayorquin/IBL-to-nwb.git')}\n")
        f.write(f"REPO_BRANCH={config.get('REPO_BRANCH', 'heberto_conversion')}\n")
        f.write(f"DANDISET_ID={config.get('DANDISET_ID', '217706')}\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Setup AWS infrastructure for IBL conversion")
    parser.add_argument(
        "--profile",
        choices=["catalyst_neuro", "ibl"],
        required=True,
        help="AWS profile to configure infrastructure for",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    profile = args.profile

    print("=" * 80)
    print("IBL CONVERSION NETWORK CONFIGURATION")
    print("=" * 80)
    print(f"Profile:      {profile}")
    print(f"Region:       {REGION}")
    print(f"VPC CIDR:     {VPC_CIDR}")
    print(f"Subnet CIDR:  {SUBNET_CIDR}")
    print(f"Project:      {PROJECT_TAG}")
    print("=" * 80)
    print()

    # Load existing profile config (to preserve DANDI_API_KEY and repo settings)
    profile_path = Path(__file__).parent / "profiles" / f"{profile}.env"
    existing_config = load_profile_config(profile_path)

    # Get resource names for this profile
    names = get_resource_names(profile)

    # Initialize AWS client using the profile's AWS credentials
    aws_profile = existing_config.get("AWS_PROFILE")
    session = boto3.Session(profile_name=aws_profile, region_name=REGION)
    ec2_client = session.client("ec2")

    # Verify we're on the expected AWS account
    sts_client = session.client("sts")
    identity = sts_client.get_caller_identity()
    print(f"AWS Account: {identity['Account']} ({identity['Arn']})")

    try:
        # Step 1: Create VPC
        vpc_id = create_or_get_vpc(ec2_client, names["vpc"])

        # Step 2: Create subnet
        subnet_id = create_or_get_subnet(ec2_client, vpc_id, names["subnet"])

        # Step 3: Create Internet Gateway
        igw_id = create_or_get_internet_gateway(ec2_client, vpc_id, names["igw"])

        # Step 4: Create route table with internet route
        route_table_id = create_or_get_route_table(ec2_client, vpc_id, subnet_id, igw_id, names["route_table"])

        # Step 5: Create S3 VPC Gateway Endpoint
        endpoint_id = create_or_get_s3_endpoint(ec2_client, vpc_id, route_table_id, names["s3_endpoint"])

        # Step 6: Create security group
        sg_id = create_or_get_security_group(ec2_client, vpc_id, names["security_group"])

        # Update profile config with network IDs
        config = {
            "PROFILE": profile,
            "VPC_ID": vpc_id,
            "SUBNET_ID": subnet_id,
            "SECURITY_GROUP_ID": sg_id,
            "REGION": REGION,
            "DANDI_API_KEY": existing_config.get("DANDI_API_KEY", ""),
            "REPO_URL": existing_config.get("REPO_URL", "https://github.com/h-mayorquin/IBL-to-nwb.git"),
            "REPO_BRANCH": existing_config.get("REPO_BRANCH", "heberto_conversion"),
            "DANDISET_ID": existing_config.get("DANDISET_ID", "217706"),
        }

        save_profile_config(profile_path, config)

        print()
        print("=" * 80)
        print("✓ NETWORK CONFIGURATION COMPLETE")
        print("=" * 80)
        print()
        print("Network Details:")
        print(f"  VPC ID:              {vpc_id}")
        print(f"  Subnet ID:           {subnet_id}")
        print(f"  Internet Gateway:    {igw_id}")
        print(f"  Route Table:         {route_table_id}")
        print(f"  S3 VPC Endpoint:     {endpoint_id}")
        print(f"  Security Group:      {sg_id}")
        print()
        print(f"✓ Configuration saved to: {profile_path}")
        print()

        if not existing_config.get("DANDI_API_KEY"):
            print(f"⚠️  ACTION REQUIRED: Edit {profile_path} and set your DANDI API key:")
            print(f"   vim {profile_path}")
            print("   # Change: DANDI_API_KEY=your-dandi-api-key-here")
            print()

        print("Next Steps:")
        print(
            f"  1. Test with first session:  python launch_ec2_instances.py --profile {profile} --range 0-0 --stub-test"
        )
        print(f"  2. Launch all sessions:      python launch_ec2_instances.py --profile {profile} --all")
        print()
        print("Monitoring:")
        print("  - Real-time monitoring:      python monitor.py")
        print("  - Verify uploads:            python verify_dandi_uploads.py --dandiset-id 217706")
        print("=" * 80)

        return 0

    except ClientError as e:
        print()
        print("=" * 80)
        print("✗ ERROR: Failed to configure networking")
        print("=" * 80)
        print(f"Error: {e}")
        print()
        print("Common causes:")
        print("  - Insufficient AWS permissions")
        print("  - VPC quota reached (default is 5 VPCs per region)")
        print("  - CIDR block conflict with existing VPCs")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())

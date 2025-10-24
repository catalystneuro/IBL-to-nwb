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
    python configure_networking.py

Output:
    Prints VPC ID and Security Group ID for use in launch script
"""

import sys

import boto3
from botocore.exceptions import ClientError

# Hardcoded configuration
REGION = "us-east-2"
VPC_CIDR = "10.50.0.0/16"
SUBNET_CIDR = "10.50.1.0/24"
PROJECT_TAG = "IBL-NWB-Conversion"
VPC_NAME = "ibl-conversion-vpc"
SUBNET_NAME = "ibl-conversion-public-subnet"
IGW_NAME = "ibl-conversion-igw"
ROUTE_TABLE_NAME = "ibl-conversion-route-table"
S3_ENDPOINT_NAME = "ibl-conversion-s3-endpoint"
SECURITY_GROUP_NAME = "ibl-conversion-sg"


def create_or_get_vpc(ec2_client):
    """Create VPC or return existing one."""
    print("Checking for existing VPC...")

    # Check if VPC already exists
    response = ec2_client.describe_vpcs(
        Filters=[
            {"Name": "tag:Name", "Values": [VPC_NAME]},
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
        TagSpecifications=[{
            "ResourceType": "vpc",
            "Tags": [
                {"Key": "Name", "Value": VPC_NAME},
                {"Key": "Project", "Value": PROJECT_TAG},
            ]
        }]
    )
    vpc_id = response["Vpc"]["VpcId"]

    # Enable DNS hostnames (required for EC2 instances to get public DNS)
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})

    print(f"✓ Created VPC: {vpc_id}")
    return vpc_id


def create_or_get_subnet(ec2_client, vpc_id):
    """Create public subnet or return existing one."""
    print("Checking for existing subnet...")

    # Check if subnet already exists
    response = ec2_client.describe_subnets(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:Name", "Values": [SUBNET_NAME]},
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
        TagSpecifications=[{
            "ResourceType": "subnet",
            "Tags": [
                {"Key": "Name", "Value": SUBNET_NAME},
                {"Key": "Project", "Value": PROJECT_TAG},
            ]
        }]
    )
    subnet_id = response["Subnet"]["SubnetId"]

    # Enable auto-assign public IP (instances get public IPs automatically)
    ec2_client.modify_subnet_attribute(
        SubnetId=subnet_id,
        MapPublicIpOnLaunch={"Value": True}
    )

    print(f"✓ Created subnet: {subnet_id}")
    return subnet_id


def create_or_get_internet_gateway(ec2_client, vpc_id):
    """Create Internet Gateway and attach to VPC, or return existing one."""
    print("Checking for existing Internet Gateway...")

    # Check if IGW already exists
    response = ec2_client.describe_internet_gateways(
        Filters=[
            {"Name": "tag:Name", "Values": [IGW_NAME]},
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
        TagSpecifications=[{
            "ResourceType": "internet-gateway",
            "Tags": [
                {"Key": "Name", "Value": IGW_NAME},
                {"Key": "Project", "Value": PROJECT_TAG},
            ]
        }]
    )
    igw_id = response["InternetGateway"]["InternetGatewayId"]

    # Attach to VPC
    ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)

    print(f"✓ Created and attached Internet Gateway: {igw_id}")
    return igw_id


def create_or_get_route_table(ec2_client, vpc_id, subnet_id, igw_id):
    """Create route table with internet route, or return existing one."""
    print("Checking for existing route table...")

    # Check if custom route table already exists
    response = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:Name", "Values": [ROUTE_TABLE_NAME]},
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
        TagSpecifications=[{
            "ResourceType": "route-table",
            "Tags": [
                {"Key": "Name", "Value": ROUTE_TABLE_NAME},
                {"Key": "Project", "Value": PROJECT_TAG},
            ]
        }]
    )
    route_table_id = response["RouteTable"]["RouteTableId"]

    # Add route to internet gateway (0.0.0.0/0 -> IGW)
    ec2_client.create_route(
        RouteTableId=route_table_id,
        DestinationCidrBlock="0.0.0.0/0",
        GatewayId=igw_id
    )

    # Associate route table with subnet
    ec2_client.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)

    print(f"✓ Created route table with internet route: {route_table_id}")
    return route_table_id


def create_or_get_s3_endpoint(ec2_client, vpc_id, route_table_id):
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
        TagSpecifications=[{
            "ResourceType": "vpc-endpoint",
            "Tags": [
                {"Key": "Name", "Value": S3_ENDPOINT_NAME},
                {"Key": "Project", "Value": PROJECT_TAG},
            ]
        }]
    )
    endpoint_id = response["VpcEndpoint"]["VpcEndpointId"]

    print(f"✓ Created S3 VPC endpoint: {endpoint_id}")
    return endpoint_id


def create_or_get_security_group(ec2_client, vpc_id):
    """Create security group with SSH access or return existing one."""
    print("Checking for existing security group...")

    # Check if security group already exists
    try:
        response = ec2_client.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [SECURITY_GROUP_NAME]},
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
        GroupName=SECURITY_GROUP_NAME,
        Description="Security group for IBL NWB conversion instances",
        VpcId=vpc_id,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [
                {"Key": "Name", "Value": SECURITY_GROUP_NAME},
                {"Key": "Project", "Value": PROJECT_TAG},
            ]
        }]
    )
    sg_id = response["GroupId"]

    # Add SSH ingress rule (for debugging)
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH from anywhere (debugging)"}],
        }]
    )

    print(f"✓ Created security group: {sg_id}")
    print("  ⚠️  SSH (port 22) open to 0.0.0.0/0 - restrict to your IP in production!")
    return sg_id


def main():
    print("=" * 80)
    print("IBL CONVERSION NETWORK CONFIGURATION")
    print("=" * 80)
    print(f"Region:       {REGION}")
    print(f"VPC CIDR:     {VPC_CIDR}")
    print(f"Subnet CIDR:  {SUBNET_CIDR}")
    print(f"Project:      {PROJECT_TAG}")
    print("=" * 80)
    print()

    # Initialize AWS client
    ec2_client = boto3.client("ec2", region_name=REGION)

    try:
        # Step 1: Create VPC
        vpc_id = create_or_get_vpc(ec2_client)

        # Step 2: Create subnet
        subnet_id = create_or_get_subnet(ec2_client, vpc_id)

        # Step 3: Create Internet Gateway
        igw_id = create_or_get_internet_gateway(ec2_client, vpc_id)

        # Step 4: Create route table with internet route
        route_table_id = create_or_get_route_table(ec2_client, vpc_id, subnet_id, igw_id)

        # Step 5: Create S3 VPC Gateway Endpoint
        endpoint_id = create_or_get_s3_endpoint(ec2_client, vpc_id, route_table_id)

        # Step 6: Create security group
        sg_id = create_or_get_security_group(ec2_client, vpc_id)

        # Write network config to .env file
        from pathlib import Path
        config_file = Path(__file__).parent / "network_config.env"

        # Check if file exists to preserve DANDI_API_KEY if already set
        existing_dandi_key = None
        if config_file.exists():
            with open(config_file) as f:
                for line in f:
                    if line.strip().startswith("DANDI_API_KEY="):
                        existing_dandi_key = line.strip().split("=", 1)[1]
                        break

        with open(config_file, "w") as f:
            f.write("# IBL Conversion Configuration\n")
            f.write("# Generated by configure_networking.py\n")
            f.write("#\n")
            f.write("# WARNING: This file contains secrets (DANDI_API_KEY)\n")
            f.write("# DO NOT COMMIT TO GIT - File is gitignored for safety\n")
            f.write("#\n")
            f.write("# Network IDs (safe, not secrets):\n")
            f.write(f"VPC_ID={vpc_id}\n")
            f.write(f"SUBNET_ID={subnet_id}\n")
            f.write(f"SECURITY_GROUP_ID={sg_id}\n")
            f.write(f"REGION={REGION}\n")
            f.write("\n")
            f.write("# Secret (NEVER commit to git):\n")
            if existing_dandi_key:
                f.write(f"DANDI_API_KEY={existing_dandi_key}\n")
            else:
                f.write("DANDI_API_KEY=your-dandi-api-key-here\n")

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
        print(f"✓ Configuration saved to: {config_file}")
        print()
        if not existing_dandi_key:
            print("⚠️  ACTION REQUIRED: Edit network_config.env and set your DANDI API key:")
            print(f"   vim {config_file}")
            print("   # Change: DANDI_API_KEY=your-dandi-api-key-here")
            print()
        print("Next Steps:")
        print("  1. Launch instances:     python launch_ec2_instances.py --num-instances 3 --stub-test")
        print()
        print("Note: launch_ec2_instances.py will automatically read network_config.env")
        print("      Session assignments are calculated automatically via ShardRange tags")
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
        print("  - Insufficient AWS permissions (run verify_aws_permissions.py)")
        print("  - VPC quota reached (default is 5 VPCs per region)")
        print("  - CIDR block conflict with existing VPCs")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    sys.exit(main())

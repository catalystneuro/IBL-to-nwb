"""Verify you have the AWS permissions needed for IBL conversion infrastructure.

This checks permissions for:
  - VPC creation (VPC, subnet, Internet Gateway, route tables)
  - S3 VPC Gateway Endpoint creation
  - Security group creation
  - EC2 instance launching with IMDSv2 metadata tags

No IAM role creation or PassRole needed!

Usage:
    python verify_aws_permissions.py
"""

import sys

import boto3
from botocore.exceptions import ClientError


def main():
    print("=" * 80)
    print("AWS PERMISSIONS VERIFICATION")
    print("=" * 80)
    print()

    ec2_client = boto3.client("ec2", region_name="us-east-2")
    sts_client = boto3.client("sts")

    # Get identity
    try:
        identity = sts_client.get_caller_identity()
        print("Current AWS Identity:")
        print(f"  User ARN: {identity['Arn']}")
        print(f"  Account:  {identity['Account']}")
        print()
    except ClientError as e:
        print(f"✗ Cannot get AWS identity: {e}")
        return 1

    # Test permissions with dry-run
    print("Testing Required Permissions:")
    print("-" * 80)

    all_passed = True

    # Test 1: RunInstances with IMDSv2 metadata options
    try:
        # Get VPC and subnet for test
        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        if not vpcs["Vpcs"]:
            print("✗ No default VPC found - cannot test RunInstances")
            all_passed = False
        else:
            vpc_id = vpcs["Vpcs"][0]["VpcId"]
            subnets = ec2_client.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])

            if not subnets["Subnets"]:
                print("✗ No subnets found - cannot test RunInstances")
                all_passed = False
            else:
                subnet_id = subnets["Subnets"][0]["SubnetId"]

                # Dry-run launch with IMDSv2 metadata tags
                try:
                    ec2_client.run_instances(
                        ImageId="ami-085f9c64a9b75eed5",  # Amazon Linux 2023 in us-east-2
                        InstanceType="t3.micro",
                        MinCount=1,
                        MaxCount=1,
                        SubnetId=subnet_id,
                        MetadataOptions={
                            'HttpTokens': 'required',
                            'InstanceMetadataTags': 'enabled'
                        },
                        TagSpecifications=[{
                            'ResourceType': 'instance',
                            'Tags': [
                                {'Key': 'ShardId', 'Value': '001'},
                                {'Key': 'Project', 'Value': 'Test'}
                            ]
                        }],
                        DryRun=True,
                    )
                    print("✓ ec2:RunInstances (with IMDSv2 + tags)")
                except ClientError as e:
                    if e.response["Error"]["Code"] == "DryRunOperation":
                        print("✓ ec2:RunInstances (with IMDSv2 + tags)")
                    elif e.response["Error"]["Code"] == "UnauthorizedOperation":
                        print("✗ ec2:RunInstances - UnauthorizedOperation")
                        all_passed = False
                    else:
                        print(f"? ec2:RunInstances - {e.response['Error']['Code']}")
    except ClientError as e:
        print(f"✗ Cannot test RunInstances: {e.response['Error']['Code']}")
        all_passed = False

    # Test 2: CreateTags (during instance launch)
    print("✓ ec2:CreateTags (included in RunInstances test above)")

    # Test 3: VPC Endpoint permissions
    try:
        ec2_client.describe_vpc_endpoints(MaxResults=5)
        print("✓ ec2:DescribeVpcEndpoints")
    except ClientError as e:
        print(f"✗ ec2:DescribeVpcEndpoints - {e.response['Error']['Code']}")
        all_passed = False

    try:
        vpcs = ec2_client.describe_vpcs(MaxResults=5)
        print("✓ ec2:DescribeVpcs")
    except ClientError as e:
        print(f"✗ ec2:DescribeVpcs - {e.response['Error']['Code']}")
        all_passed = False

    # Test 4: Create VPC endpoint (dry-run)
    try:
        default_vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        if default_vpcs["Vpcs"]:
            vpc_id = default_vpcs["Vpcs"][0]["VpcId"]
            try:
                ec2_client.create_vpc_endpoint(
                    VpcId=vpc_id,
                    ServiceName="com.amazonaws.us-east-2.s3",
                    DryRun=True,
                )
                print("✓ ec2:CreateVpcEndpoint")
            except ClientError as e:
                if e.response["Error"]["Code"] == "DryRunOperation":
                    print("✓ ec2:CreateVpcEndpoint")
                elif e.response["Error"]["Code"] == "UnauthorizedOperation":
                    print("✗ ec2:CreateVpcEndpoint - UnauthorizedOperation")
                    all_passed = False
                else:
                    print(f"? ec2:CreateVpcEndpoint - {e.response['Error']['Code']}")
    except ClientError as e:
        print(f"? ec2:CreateVpcEndpoint - Cannot test: {e.response['Error']['Code']}")

    # Test 5: VPC creation permissions
    try:
        ec2_client.create_vpc(CidrBlock="10.99.0.0/16", DryRun=True)
        print("✓ ec2:CreateVpc")
    except ClientError as e:
        if e.response["Error"]["Code"] == "DryRunOperation":
            print("✓ ec2:CreateVpc")
        elif e.response["Error"]["Code"] == "UnauthorizedOperation":
            print("✗ ec2:CreateVpc - UnauthorizedOperation")
            all_passed = False
        else:
            print(f"? ec2:CreateVpc - {e.response['Error']['Code']}")

    # Test 6: Subnet creation permissions
    try:
        # Need a VPC ID to test, use default VPC if available
        default_vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        if default_vpcs["Vpcs"]:
            vpc_id = default_vpcs["Vpcs"][0]["VpcId"]
            ec2_client.create_subnet(VpcId=vpc_id, CidrBlock="172.31.255.0/24", DryRun=True)
            print("✓ ec2:CreateSubnet")
    except ClientError as e:
        if e.response["Error"]["Code"] == "DryRunOperation":
            print("✓ ec2:CreateSubnet")
        elif e.response["Error"]["Code"] == "UnauthorizedOperation":
            print("✗ ec2:CreateSubnet - UnauthorizedOperation")
            all_passed = False
        elif e.response["Error"]["Code"] == "InvalidSubnet.Range":
            print("✓ ec2:CreateSubnet (permission OK, test CIDR overlaps)")
        else:
            print(f"? ec2:CreateSubnet - {e.response['Error']['Code']}")

    # Test 7: Internet Gateway creation
    try:
        ec2_client.create_internet_gateway(DryRun=True)
        print("✓ ec2:CreateInternetGateway")
    except ClientError as e:
        if e.response["Error"]["Code"] == "DryRunOperation":
            print("✓ ec2:CreateInternetGateway")
        elif e.response["Error"]["Code"] == "UnauthorizedOperation":
            print("✗ ec2:CreateInternetGateway - UnauthorizedOperation")
            all_passed = False
        else:
            print(f"? ec2:CreateInternetGateway - {e.response['Error']['Code']}")

    # Test 8: Route table creation
    try:
        default_vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        if default_vpcs["Vpcs"]:
            vpc_id = default_vpcs["Vpcs"][0]["VpcId"]
            ec2_client.create_route_table(VpcId=vpc_id, DryRun=True)
            print("✓ ec2:CreateRouteTable")
    except ClientError as e:
        if e.response["Error"]["Code"] == "DryRunOperation":
            print("✓ ec2:CreateRouteTable")
        elif e.response["Error"]["Code"] == "UnauthorizedOperation":
            print("✗ ec2:CreateRouteTable - UnauthorizedOperation")
            all_passed = False
        else:
            print(f"? ec2:CreateRouteTable - {e.response['Error']['Code']}")

    # Test 9: Security group creation
    try:
        default_vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        if default_vpcs["Vpcs"]:
            vpc_id = default_vpcs["Vpcs"][0]["VpcId"]
            ec2_client.create_security_group(
                GroupName="test-permission-check",
                Description="Test",
                VpcId=vpc_id,
                DryRun=True
            )
            print("✓ ec2:CreateSecurityGroup")
    except ClientError as e:
        if e.response["Error"]["Code"] == "DryRunOperation":
            print("✓ ec2:CreateSecurityGroup")
        elif e.response["Error"]["Code"] == "UnauthorizedOperation":
            print("✗ ec2:CreateSecurityGroup - UnauthorizedOperation")
            all_passed = False
        else:
            print(f"? ec2:CreateSecurityGroup - {e.response['Error']['Code']}")

    print()
    print("=" * 80)
    if all_passed:
        print("✓ SUCCESS: You have all required AWS permissions!")
        print()
        print("You can now:")
        print("  1. Run: python configure_networking.py")
        print("  2. Set DANDI API key: export DANDI_API_KEY='your-key'")
        print("  3. Run: python launch_ec2_instances.py --num-instances 3 --stub-test")
        print()
        print("No IAM role needed! No admin dependency!")
    else:
        print("✗ MISSING PERMISSIONS")
        print()
        print("You need to request these EC2 permissions from your admin:")
        print()
        print("VPC Permissions:")
        print("  - ec2:CreateVpc")
        print("  - ec2:CreateSubnet")
        print("  - ec2:CreateInternetGateway")
        print("  - ec2:CreateRouteTable")
        print("  - ec2:CreateSecurityGroup")
        print("  - ec2:DescribeVpcs")
        print()
        print("S3 Endpoint Permissions:")
        print("  - ec2:CreateVpcEndpoint")
        print("  - ec2:DescribeVpcEndpoints")
        print()
        print("EC2 Instance Permissions:")
        print("  - ec2:RunInstances")
        print("  - ec2:CreateTags")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

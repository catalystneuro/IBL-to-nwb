#!/bin/bash
# Quick test script for stub conversion with 3 instances

set -e

echo "========================================"
echo "IBL NWB Conversion - Quick Test"
echo "========================================"
echo ""

# Configuration
NUM_INSTANCES=3
REGION="us-east-2"

echo "IMPORTANT: Before running this script:"
echo "  1. Edit ec2_userdata_production.sh with your DANDI API key (line 90)"
echo "  2. Make sure AWS CLI is configured: aws configure"
echo "  3. Verify permissions: python verify_imdsv2_permissions.py"
echo ""
read -p "Press Enter to continue or Ctrl+C to exit..."

echo ""
echo "Step 1: Setting up S3 VPC endpoint..."
python setup_vpc_endpoint.py

echo ""
echo "Step 2: Generating stub assignment files..."
python generate_assignments.py --num-shards ${NUM_INSTANCES} --stub-test

echo ""
echo "Step 3: Committing assignments to git..."
git add assignments/
git commit -m "Add stub test assignments" || echo "Assignments already committed"

echo ""
echo "Step 4: Launching ${NUM_INSTANCES} test instances (with IMDSv2 tags)..."
python launch_ec2_instances.py --num-instances ${NUM_INSTANCES} --stub-test

echo ""
echo "========================================"
echo "Test instances launched successfully!"
echo "========================================"
echo ""
echo "Monitor progress:"
echo "  AWS Console: https://console.aws.amazon.com/ec2/v2/home?region=${REGION}#Instances:"
echo ""
echo "Check instance count:"
echo "  aws ec2 describe-instances --region ${REGION} \\"
echo "    --filters 'Name=tag:Project,Values=IBL-NWB-Conversion' \\"
echo "    --query 'Reservations[*].Instances[*].[InstanceId,State.Name]' --output table"
echo ""
echo "Terminate all when done:"
echo "  aws ec2 terminate-instances --region ${REGION} \\"
echo "    --instance-ids \$(aws ec2 describe-instances --region ${REGION} \\"
echo "      --filters 'Name=tag:Project,Values=IBL-NWB-Conversion' \\"
echo "      --query 'Reservations[*].Instances[*].InstanceId' --output text)"
echo ""

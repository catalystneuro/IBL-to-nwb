#!/bin/bash
# Monitor IBL conversion instances

REGION="us-east-2"

echo "=========================================="
echo "IBL Conversion Instance Monitor"
echo "=========================================="
echo ""

# Get all running instances
INSTANCE_IDS=$(aws ec2 describe-instances --region ${REGION} \
  --filters 'Name=tag:Project,Values=IBL-NWB-Conversion' \
            'Name=instance-state-name,Values=running,pending' \
  --query 'Reservations[*].Instances[*].InstanceId' \
  --output text)

if [[ -z "${INSTANCE_IDS}" ]]; then
    echo "No running instances found."
    exit 0
fi

echo "Found instances: ${INSTANCE_IDS}"
echo ""

# Show instance details
echo "Instance Status:"
echo "----------------"
aws ec2 describe-instances --region ${REGION} \
  --instance-ids ${INSTANCE_IDS} \
  --query 'Reservations[*].Instances[*].[InstanceId,State.Name,Tags[?Key==`ShardId`].Value|[0],Tags[?Key==`ShardRange`].Value|[0],Tags[?Key==`StubTest`].Value|[0],LaunchTime]' \
  --output table

echo ""
echo "=========================================="
echo "Console Output (Last 100 lines per instance)"
echo "=========================================="

for INSTANCE_ID in ${INSTANCE_IDS}; do
    echo ""
    echo "=========================================="
    SHARD_ID=$(aws ec2 describe-instances --region ${REGION} \
      --instance-ids ${INSTANCE_ID} \
      --query 'Reservations[0].Instances[0].Tags[?Key==`ShardId`].Value | [0]' \
      --output text)

    echo "Instance: ${INSTANCE_ID} (Shard ${SHARD_ID})"
    echo "=========================================="

    # Get console output (shows userdata script execution)
    OUTPUT=$(aws ec2 get-console-output --region ${REGION} \
      --instance-id ${INSTANCE_ID} \
      --latest \
      --output text 2>/dev/null | tail -100)

    if [[ -z "${OUTPUT}" ]]; then
        echo "  [No console output yet - instance still booting]"
    else
        echo "${OUTPUT}"
    fi

    echo ""
done

echo ""
echo "=========================================="
echo "Key Messages to Look For:"
echo "=========================================="
echo "✅ 'Stub test mode: true'               - Confirms stub test is enabled"
echo "✅ 'Running in STUB TEST mode'          - Conversion running in stub mode"
echo "✅ 'Found existing filesystem'          - EBS mount successful"
echo "✅ 'Starting conversion process'        - Conversion started"
echo "✅ 'PROCESSING SESSION X/Y'             - Conversion in progress"
echo "✅ 'Upload successful'                  - DANDI upload complete"
echo "✅ 'Shutting down'                      - Instance finishing"
echo ""
echo "❌ 'ERROR:'                              - Check for errors"
echo "❌ 'FAILED'                              - Session failed"
echo "❌ 'mount:'                              - EBS mount issues"
echo ""
echo "To continuously monitor, run:"
echo "  watch -n 30 ./monitor_instances.sh"
echo ""

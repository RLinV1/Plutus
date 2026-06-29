#!/usr/bin/env bash
# Take the EB service OFFLINE without destroying it (or your data).
#
# Postgres runs as a container on the instance with data on the instance's EBS
# volume, so we must NOT terminate/replace the instance. Instead we:
#   1. Suspend the Auto Scaling Group so EB won't replace the stopped instance
#      (a replacement would wipe pgdata).
#   2. Stop (NOT terminate) the EC2 instance — the EBS volume + DB persist.
#
# This stops the compute charge for the instance. You still pay a small amount
# for EBS storage and the Elastic IP. Bring it back with: bash scripts/eb-start.sh
#
# Usage: bash scripts/eb-stop.sh [env-name] [region]
set -euo pipefail

ENV_NAME="${1:-plutus-prod}"
REGION="${2:-us-east-1}"

echo "[eb-stop] Looking up resources for environment: $ENV_NAME ($REGION)"
ASG_NAME=$(aws elasticbeanstalk describe-environment-resources \
  --environment-name "$ENV_NAME" --region "$REGION" \
  --query "EnvironmentResources.AutoScalingGroups[0].Name" --output text)
INSTANCE_ID=$(aws elasticbeanstalk describe-environment-resources \
  --environment-name "$ENV_NAME" --region "$REGION" \
  --query "EnvironmentResources.Instances[0].Id" --output text)

if [ -z "$ASG_NAME" ] || [ "$ASG_NAME" = "None" ] || \
   [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
  echo "[eb-stop] Could not resolve ASG / instance. Is the env running?"
  exit 1
fi

echo "[eb-stop] ASG:      $ASG_NAME"
echo "[eb-stop] Instance: $INSTANCE_ID"
echo "[eb-stop] WARNING: this takes '$ENV_NAME' OFFLINE (data is preserved)."
read -p "Type the environment name to confirm: " CONFIRM
if [ "$CONFIRM" != "$ENV_NAME" ]; then
  echo "[eb-stop] Aborted."
  exit 1
fi

echo "[eb-stop] Suspending ASG processes (so EB won't replace the instance)..."
aws autoscaling suspend-processes \
  --auto-scaling-group-name "$ASG_NAME" --region "$REGION"

echo "[eb-stop] Stopping instance $INSTANCE_ID..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null

echo "[eb-stop] Waiting for instance to reach 'stopped'..."
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID" --region "$REGION"

echo ""
echo "[eb-stop] Done. '$ENV_NAME' is offline; compute charges stopped."
echo "[eb-stop] EB health will show red/Severe while paused — that's expected."
echo "[eb-stop] Bring it back with: bash scripts/eb-start.sh $ENV_NAME $REGION"

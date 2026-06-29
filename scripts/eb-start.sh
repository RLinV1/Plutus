#!/usr/bin/env bash
# Bring the EB service back ONLINE after eb-stop.sh paused it.
#
# Reverses eb-stop.sh. Order matters: start the instance FIRST, wait until it's
# running, THEN resume the ASG — otherwise a resumed ASG could decide the still-
# stopped instance is unhealthy and replace it (which would wipe pgdata).
#
# Idempotent and non-interactive (safe to call from CI): if the instance is
# already running it just resumes the ASG and exits.
#
# Usage: bash scripts/eb-start.sh [env-name] [region]
set -euo pipefail

ENV_NAME="${1:-plutus-prod}"
REGION="${2:-us-east-1}"

echo "[eb-start] Looking up resources for environment: $ENV_NAME ($REGION)"
ASG_NAME=$(aws elasticbeanstalk describe-environment-resources \
  --environment-name "$ENV_NAME" --region "$REGION" \
  --query "EnvironmentResources.AutoScalingGroups[0].Name" --output text)
INSTANCE_ID=$(aws elasticbeanstalk describe-environment-resources \
  --environment-name "$ENV_NAME" --region "$REGION" \
  --query "EnvironmentResources.Instances[0].Id" --output text)

if [ -z "$ASG_NAME" ] || [ "$ASG_NAME" = "None" ] || \
   [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
  echo "[eb-start] Could not resolve ASG / instance for '$ENV_NAME'."
  echo "[eb-start] Nothing to start (env may be terminated, not paused)."
  exit 1
fi

STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
  --query "Reservations[0].Instances[0].State.Name" --output text)
echo "[eb-start] ASG:      $ASG_NAME"
echo "[eb-start] Instance: $INSTANCE_ID (state: $STATE)"

if [ "$STATE" != "running" ]; then
  echo "[eb-start] Starting instance..."
  aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null
  echo "[eb-start] Waiting for instance to reach 'running'..."
  aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
else
  echo "[eb-start] Instance already running — skipping start."
fi

echo "[eb-start] Resuming ASG processes..."
aws autoscaling resume-processes \
  --auto-scaling-group-name "$ASG_NAME" --region "$REGION"

echo ""
echo "[eb-start] Done. EB will re-run health checks; containers restart on boot"
echo "[eb-start] (restart: unless-stopped). Give it a minute to go green."
echo "[eb-start] Check with: aws elasticbeanstalk describe-environments \\"
echo "             --environment-names $ENV_NAME --region $REGION \\"
echo "             --query 'Environments[].{Status:Status,Health:Health}'"

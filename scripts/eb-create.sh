#!/usr/bin/env bash
# First-time Elastic Beanstalk setup:
# - Fetches secrets and creates EB environment with them baked in from the start
# - Resizes EBS volume
# - Deploys the app
# - Runs RAG ingest
set -e

ENV_NAME="${1:-plutus-prod}"
REGION="${2:-us-east-1}"
DISK_GB="${3:-20}"

echo "[eb-create] Fetching secrets from AWS Secrets Manager..."
_parse_secret() {
  local raw="$1"
  echo "$raw" | python3 -c "
import sys, json
s = sys.stdin.read().strip()
try:
    d = json.loads(s)
    print(list(d.values())[0])
except Exception:
    print(s)
"
}
ANTHROPIC_KEY=$(_parse_secret "$(aws secretsmanager get-secret-value \
  --secret-id plutus/anthropic-api-key \
  --query SecretString --output text)")
PGPASS=$(_parse_secret "$(aws secretsmanager get-secret-value \
  --secret-id plutus/postgres-password \
  --query SecretString --output text)")

echo "[eb-create] Creating EB environment: $ENV_NAME (with secrets pre-loaded)"
eb create "$ENV_NAME" \
  --instance-type t3.medium \
  --single \
  --platform "Docker running on 64bit Amazon Linux 2023" \
  --region "$REGION" \
  --envvars ANTHROPIC_API_KEY="$ANTHROPIC_KEY",POSTGRES_PASSWORD="$PGPASS"

echo "[eb-create] Waiting for instance to be ready..."
sleep 30

echo "[eb-create] Resizing EBS volume to ${DISK_GB}GB..."
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:elasticbeanstalk:environment-name,Values=$ENV_NAME" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text)

VOLUME_ID=$(aws ec2 describe-volumes \
  --filters "Name=attachment.instance-id,Values=$INSTANCE_ID" \
  --query "Volumes[0].VolumeId" \
  --output text)

echo "[eb-create] Volume: $VOLUME_ID — resizing to ${DISK_GB}GB"
aws ec2 modify-volume --volume-id "$VOLUME_ID" --size "$DISK_GB"

echo "[eb-create] Waiting for volume modification to complete..."
sleep 15

echo "[eb-create] Expanding filesystem..."
eb ssh --command "sudo growpart /dev/nvme0n1 1 && sudo xfs_growfs / && df -h /"

echo "[eb-create] Deploying app..."
bash "$(dirname "$0")/eb-deploy.sh" --ingest

echo ""
echo "[eb-create] Done! Your app is live:"
eb status | grep CNAME

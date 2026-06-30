#!/usr/bin/env bash
# Terminate the EB environment and clean up.
# Usage: bash scripts/eb-terminate.sh [env-name] [region]
#
# Also deletes the Elastic Beanstalk application-versions S3 bucket
# (elasticbeanstalk-<region>-<account-id>). WARNING: that bucket is shared
# by every EB app/environment in this account+region, so this removes ALL
# stored application versions, not just this env's. Only run it if this is
# your only EB app.
set -e

ENV_NAME="${1:-plutus-prod}"
REGION="${2:-us-east-1}"

echo "[eb-terminate] WARNING: This will delete the environment '$ENV_NAME' and all its data."
read -p "Type the environment name to confirm: " CONFIRM

if [ "$CONFIRM" != "$ENV_NAME" ]; then
  echo "[eb-terminate] Aborted."
  exit 1
fi

echo "[eb-terminate] Terminating $ENV_NAME..."
# Wait so the env fully releases its hold on the S3 bucket before we delete it.
eb terminate "$ENV_NAME" --force

# ---- S3 bucket teardown ---------------------------------------------------
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="elasticbeanstalk-${REGION}-${ACCOUNT_ID}"

echo ""
echo "[eb-terminate] WARNING: about to DELETE the shared EB bucket: s3://$BUCKET"
echo "[eb-terminate] This removes application versions for ALL EB apps in"
echo "[eb-terminate] $REGION / account $ACCOUNT_ID, not just '$ENV_NAME'."

if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "[eb-terminate] Bucket s3://$BUCKET not found (already gone?) — skipping."
else
  read -p "Type the bucket name to confirm deletion (or anything else to skip): " BUCKET_CONFIRM
  if [ "$BUCKET_CONFIRM" != "$BUCKET" ]; then
    echo "[eb-terminate] Bucket deletion skipped. Environment was still terminated."
  else
    # EB attaches a bucket policy that can deny DeleteBucket; drop it first.
    aws s3api delete-bucket-policy --bucket "$BUCKET" 2>/dev/null || true
    echo "[eb-terminate] Emptying and removing s3://$BUCKET ..."
    aws s3 rb "s3://$BUCKET" --force
    echo "[eb-terminate] Bucket deleted."
  fi
fi

echo "[eb-terminate] Done. To redeploy run: bash scripts/eb-create.sh"

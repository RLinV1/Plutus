#!/usr/bin/env bash
# Deploy to Elastic Beanstalk.
# EB requires the file to be named docker-compose.yml, so we swap it in,
# deploy, then restore the dev compose.
set -e

ORIG=docker-compose.yml
AWS_COMPOSE=docker-compose.aws.yml
BACKUP=docker-compose.dev.yml

echo "[eb-deploy] Backing up $ORIG → $BACKUP"
cp "$ORIG" "$BACKUP"

echo "[eb-deploy] Swapping in $AWS_COMPOSE"
cp "$AWS_COMPOSE" "$ORIG"

echo "[eb-deploy] Deploying..."
eb deploy "$@"
EXIT_CODE=$?

echo "[eb-deploy] Restoring $ORIG"
cp "$BACKUP" "$ORIG"
rm -f "$BACKUP"

exit $EXIT_CODE

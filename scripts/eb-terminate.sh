#!/usr/bin/env bash
# Terminate the EB environment and clean up.
# Usage: bash scripts/eb-terminate.sh [env-name]
set -e

ENV_NAME="${1:-plutus-prod}"

echo "[eb-terminate] WARNING: This will delete the environment '$ENV_NAME' and all its data."
read -p "Type the environment name to confirm: " CONFIRM

if [ "$CONFIRM" != "$ENV_NAME" ]; then
  echo "[eb-terminate] Aborted."
  exit 1
fi

echo "[eb-terminate] Terminating $ENV_NAME..."
eb terminate "$ENV_NAME" --force

echo "[eb-terminate] Done. To redeploy run: bash scripts/eb-create.sh"

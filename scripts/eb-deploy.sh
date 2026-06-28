#!/usr/bin/env bash
# Deploy to Elastic Beanstalk.
# - Fetches secrets from AWS Secrets Manager and pushes to EB env vars
# - Swaps in the AWS compose file, deploys, then restores the dev compose
# - Optionally runs RAG ingest after deploy (pass --ingest flag)
set -e

ORIG=docker-compose.yml
AWS_COMPOSE=docker-compose.aws.yml
BACKUP=docker-compose.dev.yml
RUN_INGEST=0

# Check for --ingest flag
for arg in "$@"; do
  if [ "$arg" = "--ingest" ]; then
    RUN_INGEST=1
  fi
done

echo "[eb-deploy] Fetching secrets from AWS Secrets Manager..."
_parse_secret() {
  local raw="$1"
  # If the secret is plain text, return as-is.
  # If it's a JSON object {"key":"value"}, extract the first value.
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

echo "[eb-deploy] Pushing env vars to EB..."
eb setenv \
  ANTHROPIC_API_KEY="$ANTHROPIC_KEY" \
  POSTGRES_PASSWORD="$PGPASS"

echo "[eb-deploy] Backing up $ORIG → $BACKUP"
cp "$ORIG" "$BACKUP"

echo "[eb-deploy] Swapping in $AWS_COMPOSE"
cp "$AWS_COMPOSE" "$ORIG"

echo "[eb-deploy] Deploying..."
eb deploy "${@/--ingest/}"
EXIT_CODE=$?

echo "[eb-deploy] Restoring $ORIG"
cp "$BACKUP" "$ORIG"
rm -f "$BACKUP"

if [ $EXIT_CODE -ne 0 ]; then
  exit $EXIT_CODE
fi

if [ $RUN_INGEST -eq 1 ]; then
  echo "[eb-deploy] Running RAG ingest..."
  eb ssh --command "sudo docker compose -f /var/app/current/docker-compose.yml exec -T api python -m portfolio_risk.rag.ingest --all"
  echo "[eb-deploy] Ingest complete."
fi

exit $EXIT_CODE

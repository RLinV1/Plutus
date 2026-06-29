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

# Clerk secrets (optional — skip if not stored yet)
CLERK_JWKS=""
CLERK_PK=""
TURNSTILE_KEY=""
if aws secretsmanager describe-secret --secret-id plutus/clerk-jwks-url &>/dev/null; then
  CLERK_JWKS=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/clerk-jwks-url \
    --query SecretString --output text)")
fi
if aws secretsmanager describe-secret --secret-id plutus/clerk-publishable-key &>/dev/null; then
  CLERK_PK=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/clerk-publishable-key \
    --query SecretString --output text)")
fi
if aws secretsmanager describe-secret --secret-id plutus/turnstile-site-key &>/dev/null; then
  TURNSTILE_KEY=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/turnstile-site-key \
    --query SecretString --output text)")
fi

# Billing / Stripe secrets (optional — daily quota is enforced without them)
STRIPE_KEY=""
STRIPE_WH=""
STRIPE_PRO=""
STRIPE_PRO_MAX=""
UNLIMITED_IDS=""
if aws secretsmanager describe-secret --secret-id plutus/stripe-secret-key &>/dev/null; then
  STRIPE_KEY=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/stripe-secret-key --query SecretString --output text)")
fi
if aws secretsmanager describe-secret --secret-id plutus/stripe-webhook-secret &>/dev/null; then
  STRIPE_WH=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/stripe-webhook-secret --query SecretString --output text)")
fi
if aws secretsmanager describe-secret --secret-id plutus/stripe-price-pro &>/dev/null; then
  STRIPE_PRO=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/stripe-price-pro --query SecretString --output text)")
fi
if aws secretsmanager describe-secret --secret-id plutus/stripe-price-pro-max &>/dev/null; then
  STRIPE_PRO_MAX=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/stripe-price-pro-max --query SecretString --output text)")
fi
if aws secretsmanager describe-secret --secret-id plutus/unlimited-user-ids &>/dev/null; then
  UNLIMITED_IDS=$(_parse_secret "$(aws secretsmanager get-secret-value \
    --secret-id plutus/unlimited-user-ids --query SecretString --output text)")
fi

echo "[eb-deploy] Pushing env vars to EB..."
eb setenv \
  ANTHROPIC_API_KEY="$ANTHROPIC_KEY" \
  POSTGRES_PASSWORD="$PGPASS" \
  CLERK_JWKS_URL="$CLERK_JWKS" \
  VITE_CLERK_PUBLISHABLE_KEY="$CLERK_PK" \
  VITE_TURNSTILE_SITE_KEY="$TURNSTILE_KEY" \
  STRIPE_SECRET_KEY="$STRIPE_KEY" \
  STRIPE_WEBHOOK_SECRET="$STRIPE_WH" \
  STRIPE_PRICE_PRO="$STRIPE_PRO" \
  STRIPE_PRICE_PRO_MAX="$STRIPE_PRO_MAX" \
  UNLIMITED_USER_IDS="$UNLIMITED_IDS"

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

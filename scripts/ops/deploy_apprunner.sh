#!/usr/bin/env bash
set -euo pipefail

# ----------------------------
# CONFIG YOU EDIT
# ----------------------------
REGION="ap-southeast-2"
SERVICE_NAME="bhp-platformlab-agentcore"

IMAGE_IDENTIFIER="184574354141.dkr.ecr.ap-southeast-2.amazonaws.com/bhp-platformlab-agentcore:latest"

# Container port your app listens on
APP_PORT="8000"

# Start with TCP health check (recommended for bring-up). Switch to HTTP later.
HEALTH_PROTOCOL="TCP"          # TCP or HTTP
HEALTH_PATH="/health"          # only used if HEALTH_PROTOCOL=HTTP

RUNTIME_ROLE_NAME="role-bhp-platformlab-dev-agentcore-runtime-aps2"
ECR_ACCESS_ROLE_NAME="role-${SERVICE_NAME}-apprunner-ecr-access"
# ----------------------------

export AWS_PAGER=""

echo "Using:"
echo "  REGION=$REGION"
echo "  SERVICE_NAME=$SERVICE_NAME"
echo "  IMAGE_IDENTIFIER=$IMAGE_IDENTIFIER"
echo "  APP_PORT=$APP_PORT"
echo "  HEALTH_PROTOCOL=$HEALTH_PROTOCOL"
echo "  HEALTH_PATH=$HEALTH_PATH"
echo "  RUNTIME_ROLE_NAME=$RUNTIME_ROLE_NAME"
echo "  ECR_ACCESS_ROLE_NAME=$ECR_ACCESS_ROLE_NAME"
echo

# ---- Basic safety checks for your Snowflake key env var (don’t leak raw PEM) ----
if [[ -n "${SF_PRIVATE_KEY_PEM_B64:-}" ]]; then
  if echo "$SF_PRIVATE_KEY_PEM_B64" | grep -q "BEGIN PRIVATE KEY"; then
    echo "❌ SF_PRIVATE_KEY_PEM_B64 looks like RAW PEM (contains 'BEGIN PRIVATE KEY')."
    echo "   It MUST be base64 text (single line). Example on mac:"
    echo "     base64 < private_key.pem | tr -d '\n'"
    exit 1
  fi
fi

# ---- IAM Role ARNs ----
RUNTIME_ROLE_ARN="$(aws iam get-role --role-name "$RUNTIME_ROLE_NAME" --query 'Role.Arn' --output text)"
echo "Runtime role: $RUNTIME_ROLE_ARN"

# ---- Ensure ECR access role exists ----
if ! aws iam get-role --role-name "$ECR_ACCESS_ROLE_NAME" >/dev/null 2>&1; then
  echo "Creating App Runner ECR access role: $ECR_ACCESS_ROLE_NAME"

  cat > /tmp/apprunner-ecr-access-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": ["build.apprunner.amazonaws.com","tasks.apprunner.amazonaws.com"] },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

  aws iam create-role \
    --role-name "$ECR_ACCESS_ROLE_NAME" \
    --assume-role-policy-document file:///tmp/apprunner-ecr-access-trust.json \
    --output json >/dev/null

  aws iam attach-role-policy \
    --role-name "$ECR_ACCESS_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess" \
    >/dev/null

  echo "✅ Created + attached AWSAppRunnerServicePolicyForECRAccess"
else
  echo "✅ ECR access role already exists"
fi

ECR_ACCESS_ROLE_ARN="$(aws iam get-role --role-name "$ECR_ACCESS_ROLE_NAME" --query 'Role.Arn' --output text)"
echo "ECR access role: $ECR_ACCESS_ROLE_ARN"
echo

# ---- Build runtime env vars JSON (only include vars that are set) ----
ENV_JSON="$(python3 - <<'PY'
import os, json

keys = [
  "APP_ENV",
  "KB_CHUNKS_TABLE",
  "TOPIC_TEMPLATES_TABLE",
  "SF_ACCOUNT_IDENTIFIER",
  "SF_ACCOUNT_URL",
  "SF_USER",
  "SF_ROLE",
  "SF_WAREHOUSE",
  "SF_DATABASE",
  "SF_SCHEMA",
  "SF_PRIVATE_KEY_PEM_B64",
  "SF_PUBLIC_KEY_FP",
  "AGENTCORE_REGION",
  "AGENTCORE_ENDPOINT",
  "AGENTCORE_AGENT_ID",
  "DATA_DIR"
]

env = {}
for k in keys:
  v = os.getenv(k)
  if v is not None:
    env[k] = v

# Ensure unbuffered logs (helps in App Runner)
env["PYTHONUNBUFFERED"] = "1"

print(json.dumps(env))
PY
)"

# ---- Find existing service (if any) ----
EXISTING_ARN="$(aws apprunner list-services \
  --region "$REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" \
  --output text)"

# ---- Write create/update payload ----
cat > /tmp/apprunner.json <<JSON
{
  "SourceConfiguration": {
    "AuthenticationConfiguration": { "AccessRoleArn": "${ECR_ACCESS_ROLE_ARN}" },
    "AutoDeploymentsEnabled": true,
    "ImageRepository": {
      "ImageIdentifier": "${IMAGE_IDENTIFIER}",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "${APP_PORT}",
        "RuntimeEnvironmentVariables": ${ENV_JSON}
      }
    }
  },
  "InstanceConfiguration": {
    "InstanceRoleArn": "${RUNTIME_ROLE_ARN}"
  },
  "HealthCheckConfiguration": {
    "Protocol": "${HEALTH_PROTOCOL}",
    "Path": "${HEALTH_PATH}",
    "Interval": 10,
    "Timeout": 5,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 10
  }
}
JSON

echo "Wrote /tmp/apprunner.json"

if [[ -z "$EXISTING_ARN" || "$EXISTING_ARN" == "None" ]]; then
  echo "Creating App Runner service..."
  aws apprunner create-service \
    --region "$REGION" \
    --service-name "$SERVICE_NAME" \
    --cli-input-json file:///tmp/apprunner.json \
    --output json
else
  echo "Service exists, updating: $EXISTING_ARN"
  aws apprunner update-service \
    --region "$REGION" \
    --service-arn "$EXISTING_ARN" \
    --cli-input-json file:///tmp/apprunner.json \
    --output json
fi

echo
echo "Watch status:"
echo "  aws apprunner list-services --region $REGION --output table"
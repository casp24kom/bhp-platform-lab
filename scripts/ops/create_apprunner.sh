#!/usr/bin/env bash
set -euo pipefail

# ----------------------------
# CONFIG (edit if needed)
# ----------------------------
REGION="ap-southeast-2"
SERVICE_NAME="bhp-platformlab-agentcore"
IMAGE_IDENTIFIER="184574354141.dkr.ecr.ap-southeast-2.amazonaws.com/bhp-platformlab-agentcore:latest"

PORT="8000"
HEALTH_PATH="/health"

# Existing runtime role you already have:
RUNTIME_ROLE_NAME="role-bhp-platformlab-dev-agentcore-runtime-aps2"

# Created/used by this script:
ECR_ACCESS_ROLE_NAME="role-${SERVICE_NAME}-apprunner-ecr-access"

AWS_PAGER=""

# ----------------------------
# REQUIRED ENV VARS (must be set in your shell before running)
# ----------------------------
required_vars=(
  "SF_ACCOUNT_IDENTIFIER"
  "SF_ACCOUNT_URL"
  "SF_USER"
  "SF_PRIVATE_KEY_PEM_B64"
  "SF_PUBLIC_KEY_FP"
)

missing=0
for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "❌ Missing required env var: $v"
    missing=1
  fi
done
if [[ $missing -ne 0 ]]; then
  echo
  echo "Set them first, e.g.:"
  echo '  export SF_ACCOUNT_IDENTIFIER="..."'
  echo '  export SF_ACCOUNT_URL="https://....snowflakecomputing.com"'
  echo '  export SF_USER="..."'
  echo '  export SF_PRIVATE_KEY_PEM_B64="(base64 pem)"'
  echo '  export SF_PUBLIC_KEY_FP="SHA256:...."'
  exit 1
fi

# Optional env vars with defaults
APP_ENV="${APP_ENV:-aws}"
KB_CHUNKS_TABLE="${KB_CHUNKS_TABLE:-BHP_PLATFORM_LAB.KB.SOP_CHUNKS_ENRICHED}"
TOPIC_TEMPLATES_TABLE="${TOPIC_TEMPLATES_TABLE:-BHP_PLATFORM_LAB.KB.TOPIC_TEMPLATES}"

SF_ROLE="${SF_ROLE:-BHP_LAB_APP_ROLE}"
SF_WAREHOUSE="${SF_WAREHOUSE:-BHP_LAB_WH}"
SF_DATABASE="${SF_DATABASE:-BHP_PLATFORM_LAB}"
SF_SCHEMA="${SF_SCHEMA:-KB}"

AGENTCORE_REGION="${AGENTCORE_REGION:-ap-southeast-2}"
AGENTCORE_ENDPOINT="${AGENTCORE_ENDPOINT:-https://bedrock-agentcore.ap-southeast-2.amazonaws.com}"
AGENTCORE_AGENT_ID="${AGENTCORE_AGENT_ID:-}"

# Make sure container gets PORT env var too (your Dockerfile supports it)
PORT_ENV="$PORT"

echo "Using:"
echo "  REGION=$REGION"
echo "  SERVICE_NAME=$SERVICE_NAME"
echo "  IMAGE_IDENTIFIER=$IMAGE_IDENTIFIER"
echo "  PORT=$PORT"
echo "  HEALTH_PATH=$HEALTH_PATH"
echo "  RUNTIME_ROLE_NAME=$RUNTIME_ROLE_NAME"
echo "  ECR_ACCESS_ROLE_NAME=$ECR_ACCESS_ROLE_NAME"
echo

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"

# ----------------------------
# 1) Ensure runtime role trust allows App Runner TASKS to assume it
#    (this fixes the earlier 'Unable to assume instance role' error)
# ----------------------------
echo "Ensuring runtime role trust includes tasks.apprunner.amazonaws.com ..."
cat > /tmp/apprunner-runtime-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "tasks.apprunner.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

aws iam update-assume-role-policy \
  --role-name "$RUNTIME_ROLE_NAME" \
  --policy-document file:///tmp/apprunner-runtime-trust.json >/dev/null

RUNTIME_ROLE_ARN="$(aws iam get-role --role-name "$RUNTIME_ROLE_NAME" --query 'Role.Arn' --output text)"

# ----------------------------
# 2) Ensure ECR access role exists for App Runner to pull private ECR images
# ----------------------------
set +e
aws iam get-role --role-name "$ECR_ACCESS_ROLE_NAME" >/dev/null 2>&1
ROLE_EXISTS=$?
set -e

if [[ $ROLE_EXISTS -ne 0 ]]; then
  echo "Creating ECR access role: $ECR_ACCESS_ROLE_NAME"

  cat > /tmp/apprunner-ecr-access-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "build.apprunner.amazonaws.com" },
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

# ----------------------------
# 3) If service exists, delete it so CreateService won't fail
# ----------------------------
echo "Checking for existing App Runner service named: $SERVICE_NAME"
EXISTING_ARN="$(aws apprunner list-services --region "$REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" \
  --output text || true)"

if [[ -n "$EXISTING_ARN" && "$EXISTING_ARN" != "None" ]]; then
  echo "Found existing service. Deleting: $EXISTING_ARN"
  aws apprunner delete-service --service-arn "$EXISTING_ARN" --region "$REGION" >/dev/null

  echo "Waiting for delete to complete..."
  while aws apprunner describe-service --service-arn "$EXISTING_ARN" --region "$REGION" >/dev/null 2>&1; do
    echo "  still deleting..."
    sleep 10
  done
  echo "✅ Deleted"
fi

# ----------------------------
# 4) Create App Runner service
#    We generate JSON using python so secrets with '=' '+' '/' don't break JSON.
# ----------------------------

# Export vars so the python json builder can read them
export SERVICE_NAME="$SERVICE_NAME"
export IMAGE_IDENTIFIER="$IMAGE_IDENTIFIER"
export PORT="$PORT"
export HEALTH_PATH="$HEALTH_PATH"
export ECR_ACCESS_ROLE_ARN="$ECR_ACCESS_ROLE_ARN"
export RUNTIME_ROLE_ARN="$RUNTIME_ROLE_ARN"

export APP_ENV KB_CHUNKS_TABLE TOPIC_TEMPLATES_TABLE
export SF_ACCOUNT_IDENTIFIER SF_ACCOUNT_URL SF_USER SF_ROLE SF_WAREHOUSE SF_DATABASE SF_SCHEMA
export SF_PRIVATE_KEY_PEM_B64 SF_PUBLIC_KEY_FP
export AGENTCORE_REGION AGENTCORE_ENDPOINT AGENTCORE_AGENT_ID

python3 - <<'PY'
import json, os

payload = {
  "ServiceName": os.environ["SERVICE_NAME"],
  "SourceConfiguration": {
    "AuthenticationConfiguration": {"AccessRoleArn": os.environ["ECR_ACCESS_ROLE_ARN"]},
    "AutoDeploymentsEnabled": True,
    "ImageRepository": {
      "ImageIdentifier": os.environ["IMAGE_IDENTIFIER"],
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": os.environ["PORT"],
        "RuntimeEnvironmentVariables": {
          # app / port
          "APP_ENV": os.environ.get("APP_ENV", "aws"),
          "PORT": os.environ["PORT_ENV"],

          # snowflake
          "KB_CHUNKS_TABLE": os.environ["KB_CHUNKS_TABLE"],
          "TOPIC_TEMPLATES_TABLE": os.environ["TOPIC_TEMPLATES_TABLE"],
          "SF_ACCOUNT_IDENTIFIER": os.environ["SF_ACCOUNT_IDENTIFIER"],
          "SF_ACCOUNT_URL": os.environ["SF_ACCOUNT_URL"],
          "SF_USER": os.environ["SF_USER"],
          "SF_ROLE": os.environ["SF_ROLE"],
          "SF_WAREHOUSE": os.environ["SF_WAREHOUSE"],
          "SF_DATABASE": os.environ["SF_DATABASE"],
          "SF_SCHEMA": os.environ["SF_SCHEMA"],

          # keypair auth
          "SF_PRIVATE_KEY_PEM_B64": os.environ["SF_PRIVATE_KEY_PEM_B64"],
          "SF_PUBLIC_KEY_FP": os.environ["SF_PUBLIC_KEY_FP"],

          # agentcore (optional)
          "AGENTCORE_REGION": os.environ.get("AGENTCORE_REGION", "ap-southeast-2"),
          "AGENTCORE_ENDPOINT": os.environ.get("AGENTCORE_ENDPOINT", "https://bedrock-agentcore.ap-southeast-2.amazonaws.com"),
          "AGENTCORE_AGENT_ID": os.environ.get("AGENTCORE_AGENT_ID", ""),
        }
      }
    }
  },
  "InstanceConfiguration": {
    "InstanceRoleArn": os.environ["RUNTIME_ROLE_ARN"]
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP",
    "Path": os.environ.get("HEALTH_PATH", "/health"),
    "Interval": 10,
    "Timeout": 5,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 10
  }
}

with open("/tmp/apprunner-create.json", "w") as f:
  json.dump(payload, f, indent=2)
print("Wrote /tmp/apprunner-create.json")
PY

export SERVICE_NAME IMAGE_IDENTIFIER PORT HEALTH_PATH \
  ECR_ACCESS_ROLE_ARN RUNTIME_ROLE_ARN \
  APP_ENV PORT_ENV \
  KB_CHUNKS_TABLE TOPIC_TEMPLATES_TABLE \
  SF_ACCOUNT_IDENTIFIER SF_ACCOUNT_URL SF_USER SF_ROLE SF_WAREHOUSE SF_DATABASE SF_SCHEMA \
  SF_PRIVATE_KEY_PEM_B64 SF_PUBLIC_KEY_FP \
  AGENTCORE_REGION AGENTCORE_ENDPOINT AGENTCORE_AGENT_ID

echo "Creating App Runner service..."
aws apprunner create-service \
  --cli-input-json file:///tmp/apprunner-create.json \
  --region "$REGION" \
  --output json

echo
echo "✅ Done. Watch status:"
echo "  aws apprunner list-services --region $REGION --output table"
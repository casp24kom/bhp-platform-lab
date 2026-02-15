#!/usr/bin/env bash
set -euo pipefail

# ----------------------------
# EDIT THESE
# ----------------------------
REGION="ap-southeast-2"
SERVICE_NAME="bhp-platformlab-agentcore"
RUNTIME_ROLE_NAME="role-bhp-platformlab-dev-agentcore-runtime-aps2"

# ECR image (set ONE of the following ways)
# Option A: set full image identifier directly:
IMAGE_IDENTIFIER="184574354141.dkr.ecr.ap-southeast-2.amazonaws.com/bhp-platformlab-agentcore:latest"

# Option B: set repo + tag and let the script build the identifier
#ECR_REPO_NAME="bhp-platformlab-agentcore"
#IMAGE_TAG="latest"

# FastAPI port inside container
PORT="8000"

# Health check path
HEALTH_PATH="/health"

# App Runner ECR access role (will be created if missing)
ECR_ACCESS_ROLE_NAME="role-${SERVICE_NAME}-apprunner-ecr-access"
# ----------------------------

AWS_PAGER=""

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
if [[ -z "${IMAGE_IDENTIFIER:-}" ]]; then
  IMAGE_IDENTIFIER="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}"
fi

echo "Using:"
echo "  REGION=$REGION"
echo "  SERVICE_NAME=$SERVICE_NAME"
echo "  IMAGE_IDENTIFIER=$IMAGE_IDENTIFIER"
echo "  PORT=$PORT"
echo "  HEALTH_PATH=$HEALTH_PATH"
echo "  RUNTIME_ROLE_NAME=$RUNTIME_ROLE_NAME"
echo "  ECR_ACCESS_ROLE_NAME=$ECR_ACCESS_ROLE_NAME"
echo

# 1) Get runtime role ARN (your existing role)
RUNTIME_ROLE_ARN="$(aws iam get-role \
  --role-name "$RUNTIME_ROLE_NAME" \
  --query 'Role.Arn' \
  --output text)"

# 2) Ensure ECR access role exists (needed for private ECR pulls)
set +e
aws iam get-role --role-name "$ECR_ACCESS_ROLE_NAME" >/dev/null 2>&1
ROLE_EXISTS=$?
set -e

if [[ $ROLE_EXISTS -ne 0 ]]; then
  echo "Creating App Runner ECR access role: $ECR_ACCESS_ROLE_NAME"

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

  echo "Created + attached AWSAppRunnerServicePolicyForECRAccess"
else
  echo "ECR access role already exists: $ECR_ACCESS_ROLE_NAME"
fi

ECR_ACCESS_ROLE_ARN="$(aws iam get-role \
  --role-name "$ECR_ACCESS_ROLE_NAME" \
  --query 'Role.Arn' \
  --output text)"

# 3) Create App Runner service (source: ECR image)
cat > /tmp/apprunner-create.json <<JSON
{
  "ServiceName": "${SERVICE_NAME}",
  "SourceConfiguration": {
    "AuthenticationConfiguration": {
      "AccessRoleArn": "${ECR_ACCESS_ROLE_ARN}"
    },
    "AutoDeploymentsEnabled": true,
    "ImageRepository": {
      "ImageIdentifier": "${IMAGE_IDENTIFIER}",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "${PORT}"
      }
    }
  },
  "InstanceConfiguration": {
    "InstanceRoleArn": "${RUNTIME_ROLE_ARN}"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP",
    "Path": "${HEALTH_PATH}"
  }
}
JSON

echo "Creating App Runner service..."
aws apprunner create-service \
  --cli-input-json file:///tmp/apprunner-create.json \
  --region "$REGION" \
  --output json

echo
echo "Done. You can watch progress with:"
echo "  aws apprunner list-services --region $REGION"
echo "  aws apprunner describe-service --service-arn <arn> --region $REGION"
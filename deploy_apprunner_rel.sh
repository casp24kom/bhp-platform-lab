#!/usr/bin/env bash
set -euo pipefail

export AWS_REGION="ap-southeast-2"
export ACCOUNT_ID="184574354141"
export REPO="bhp-platformlab-agentcore"
export SERVICE_ARN="arn:aws:apprunner:ap-southeast-2:184574354141:service/bhp-platformlab-agentcore/89096582fc254678bd36a4b48624cb19"

TAG="rel-$(date +%Y%m%d-%H%M%S)"
IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO}:${TAG}"

echo "==> Logging into ECR"
aws ecr get-login-password --region "$AWS_REGION" \
| docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Building + pushing multi-arch image: $IMAGE_URI"
docker buildx create --use --name multiarch-builder >/dev/null 2>&1 || true
docker buildx use multiarch-builder

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "$IMAGE_URI" \
  --push \
  .

echo "==> Updating App Runner service to new image"
ECR_ACCESS_ROLE_ARN="$(aws apprunner describe-service \
  --service-arn "$SERVICE_ARN" --region "$AWS_REGION" \
  --query "Service.SourceConfiguration.AuthenticationConfiguration.AccessRoleArn" --output text)"

PORT="$(aws apprunner describe-service \
  --service-arn "$SERVICE_ARN" --region "$AWS_REGION" \
  --query "Service.SourceConfiguration.ImageRepository.ImageConfiguration.Port" --output text)"

ENV_JSON="$(aws apprunner describe-service \
  --service-arn "$SERVICE_ARN" --region "$AWS_REGION" \
  --query "Service.SourceConfiguration.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables" --output json)"

cat > /tmp/apprunner-source-update.json <<JSON
{
  "ImageRepository": {
    "ImageIdentifier": "$IMAGE_URI",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {
      "Port": "$PORT",
      "RuntimeEnvironmentVariables": $ENV_JSON
    }
  },
  "AutoDeploymentsEnabled": true,
  "AuthenticationConfiguration": { "AccessRoleArn": "$ECR_ACCESS_ROLE_ARN" }
}
JSON

aws apprunner update-service \
  --service-arn "$SERVICE_ARN" \
  --region "$AWS_REGION" \
  --source-configuration file:///tmp/apprunner-source-update.json >/dev/null

echo "==> Waiting for service to return RUNNING..."
for i in {1..120}; do
  STATUS="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query "Service.Status" --output text)"
  echo "   [$i] $STATUS"
  if [[ "$STATUS" == "RUNNING" ]]; then
    break
  fi
  sleep 5
done

SERVICE_URL="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query "Service.ServiceUrl" --output text)"

echo "==> Smoke test /health"
curl -fsS "https://${SERVICE_URL}/health" | jq .

echo "==> Smoke test /rag/query"
curl -fsS "https://${SERVICE_URL}/rag/query" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo","question":"What is the isolation procedure before maintenance?","topk":5}' | jq .

echo "✅ Deployed: $IMAGE_URI"

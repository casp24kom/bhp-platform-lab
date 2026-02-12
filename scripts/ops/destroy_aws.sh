#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------
# Destroy AWS Terraform stack
# Path: deploy/terraform/aws
# --------------------------------------------

ENVIRONMENT="${1:-dev}"              # dev | prod
AUTO_APPROVE="${AUTO_APPROVE:-false}"
TF_DIR="deploy/terraform/aws"

echo "==> Destroy AWS stack"
echo "    env: ${ENVIRONMENT}"
echo "    dir: ${TF_DIR}"

if [[ ! -d "${TF_DIR}" ]]; then
  echo "ERROR: Terraform directory not found: ${TF_DIR}"
  exit 1
fi

# Safety prompt
if [[ "${AUTO_APPROVE}" != "true" ]]; then
  echo
  read -r -p "Type DESTROY to confirm destroying AWS (${ENVIRONMENT}): " CONFIRM
  if [[ "${CONFIRM}" != "DESTROY" ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

# Expect credentials from:
# - AWS_PROFILE, OR
# - env vars (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN), OR
# - assumed role via GitHub OIDC in CI
if [[ -z "${AWS_PROFILE:-}" && -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
  echo "WARNING: No AWS_PROFILE or AWS_ACCESS_KEY_ID detected."
  echo "         If you're running locally, set AWS_PROFILE=... or export AWS credentials."
fi

pushd "${TF_DIR}" >/dev/null

terraform init -upgrade
terraform workspace select "${ENVIRONMENT}" 2>/dev/null || terraform workspace new "${ENVIRONMENT}"

if [[ "${AUTO_APPROVE}" == "true" ]]; then
  terraform destroy -auto-approve
else
  terraform destroy
fi

popd >/dev/null
echo "✅ Done."
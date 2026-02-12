#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------
# Destroy Azure Container Apps Terraform stack
# Path: deploy/terraform/azure
# --------------------------------------------

ENVIRONMENT="${1:-dev}"            # dev | prod
AUTO_APPROVE="${AUTO_APPROVE:-false}"
TF_DIR="deploy/terraform/azure"

echo "==> Destroy Azure Container Apps stack"
echo "    env: ${ENVIRONMENT}"
echo "    dir: ${TF_DIR}"

if [[ ! -d "${TF_DIR}" ]]; then
  echo "ERROR: Terraform directory not found: ${TF_DIR}"
  exit 1
fi

echo "==> Checking Azure CLI login..."
az account show >/dev/null 2>&1 || { echo "ERROR: Not logged in. Run: az login"; exit 1; }

if [[ -n "${AZURE_SUBSCRIPTION_ID:-}" ]]; then
  echo "==> Setting subscription: ${AZURE_SUBSCRIPTION_ID}"
  az account set --subscription "${AZURE_SUBSCRIPTION_ID}"
fi

if [[ "${AUTO_APPROVE}" != "true" ]]; then
  echo
  read -r -p "Type DESTROY to confirm destroying Azure Container Apps (${ENVIRONMENT}): " CONFIRM
  if [[ "${CONFIRM}" != "DESTROY" ]]; then
    echo "Cancelled."
    exit 0
  fi
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
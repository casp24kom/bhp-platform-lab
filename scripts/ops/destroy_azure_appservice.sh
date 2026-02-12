#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------
# Destroy Azure App Service Terraform stack
# Path: deploy/terraform/azure-appservice
# --------------------------------------------

ENVIRONMENT="${1:-dev}"            # dev | prod
AUTO_APPROVE="${AUTO_APPROVE:-false}"  # export AUTO_APPROVE=true to skip prompt
TF_DIR="deploy/terraform/azure-appservice"

echo "==> Destroy Azure App Service stack"
echo "    env: ${ENVIRONMENT}"
echo "    dir: ${TF_DIR}"

if [[ ! -d "${TF_DIR}" ]]; then
  echo "ERROR: Terraform directory not found: ${TF_DIR}"
  exit 1
fi

# Ensure az login is active
echo "==> Checking Azure CLI login..."
az account show >/dev/null 2>&1 || { echo "ERROR: Not logged in. Run: az login"; exit 1; }

# Optional: set subscription explicitly (recommended)
if [[ -n "${AZURE_SUBSCRIPTION_ID:-}" ]]; then
  echo "==> Setting subscription: ${AZURE_SUBSCRIPTION_ID}"
  az account set --subscription "${AZURE_SUBSCRIPTION_ID}"
fi

# Safety prompt
if [[ "${AUTO_APPROVE}" != "true" ]]; then
  echo
  read -r -p "Type DESTROY to confirm destroying Azure App Service (${ENVIRONMENT}): " CONFIRM
  if [[ "${CONFIRM}" != "DESTROY" ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

pushd "${TF_DIR}" >/dev/null

# Init + select workspace
echo "==> terraform init"
terraform init -upgrade

echo "==> terraform workspace select/create: ${ENVIRONMENT}"
terraform workspace select "${ENVIRONMENT}" 2>/dev/null || terraform workspace new "${ENVIRONMENT}"

# Destroy
echo "==> terraform destroy"
if [[ "${AUTO_APPROVE}" == "true" ]]; then
  terraform destroy -auto-approve
else
  terraform destroy
fi

popd >/dev/null
echo "✅ Done."
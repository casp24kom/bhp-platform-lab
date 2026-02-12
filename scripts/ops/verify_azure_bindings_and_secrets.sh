#!/usr/bin/env bash
set -euo pipefail

# ---------
# Config (your actual names)
# ---------
SUBSCRIPTION_ID="0ef3ed97-e9ee-44dd-935a-da97870fe303"

APP_RG="rg-bhp-platformlab-dev-aue-app"
APP_NAME="app-bhp-platformlab-dev-aue-gitpushandpray"
CUSTOM_HOST="azure.gitpushandpray.ai"

KV_NAME="kvbhpplatformlabdevaue01"

DNS_RG="rg-bhp-platformlab-dev-aue-dns"
ZONE="gitpushandpray.ai"
CNAME_RECORD="azure"
TXT_RECORD="asuid.azure"

EXPECTED_CNAME_TARGET="${APP_NAME}.azurewebsites.net"

# Secrets we expect in Key Vault
SECRETS=(
  "sf-account-identifier"
  "sf-account-url"
  "sf-user"
  "sf-private-key-pem"
)

echo "==> Setting subscription: ${SUBSCRIPTION_ID}"
az account set --subscription "${SUBSCRIPTION_ID}"

echo
echo "============================================================"
echo "1) Key Vault checks (RBAC + secret existence)"
echo "============================================================"

echo "==> Key Vault RBAC enabled?"
az keyvault show -n "${KV_NAME}" --query "{name:name, rbac:properties.enableRbacAuthorization, rg:resourceGroup, location:location}" -o json

echo
echo "==> Checking required secrets exist (NO values printed):"
for s in "${SECRETS[@]}"; do
  if az keyvault secret show --vault-name "${KV_NAME}" --name "${s}" \
      --query "{name:name, enabled:attributes.enabled, created:attributes.created, updated:attributes.updated, id:id}" -o json >/dev/null 2>&1; then
    az keyvault secret show --vault-name "${KV_NAME}" --name "${s}" \
      --query "{name:name, enabled:attributes.enabled, updated:attributes.updated}" -o json
  else
    echo "MISSING: ${s}"
  fi
done

echo
echo "============================================================"
echo "2) App Service custom domain binding checks"
echo "============================================================"

echo "==> App Service hostnames (this is the correct command):"
az webapp config hostname list -g "${APP_RG}" -n "${APP_NAME}" -o table || true

echo
echo "==> Checking if ${CUSTOM_HOST} appears in hostnames:"
if az webapp config hostname list -g "${APP_RG}" -n "${APP_NAME}" -o tsv 2>/dev/null | grep -qi "^${CUSTOM_HOST}$"; then
  echo "OK: ${CUSTOM_HOST} is bound to the App Service."
else
  echo "WARN: ${CUSTOM_HOST} not found in hostname list (or CLI output differs)."
  echo "Try the portal: App Service -> Custom domains -> confirm Verified/Bound."
fi

echo
echo "==> App Service hostnames from webapp show (alternate view):"
az webapp show -g "${APP_RG}" -n "${APP_NAME}" --query "{name:name, defaultHostName:defaultHostName, hostNames:hostNames}" -o json

echo
echo "============================================================"
echo "3) Azure DNS checks (CNAME + TXT asuid)"
echo "============================================================"

echo "==> CNAME record:"
az network dns record-set cname show -g "${DNS_RG}" -z "${ZONE}" -n "${CNAME_RECORD}" \
  --query "{fqdn:fqdn, ttl:TTL, target:CNAMERecord.cname, state:provisioningState}" -o json

echo "==> TXT record:"
az network dns record-set txt show -g "${DNS_RG}" -z "${ZONE}" -n "${TXT_RECORD}" \
  --query "{fqdn:fqdn, ttl:TTL, values:TXTRecords[0].value, state:provisioningState}" -o json

echo
echo "==> Confirm CNAME matches expected target:"
ACTUAL_TARGET=$(az network dns record-set cname show -g "${DNS_RG}" -z "${ZONE}" -n "${CNAME_RECORD}" --query "CNAMERecord.cname" -o tsv || true)
if [[ "${ACTUAL_TARGET}" == "${EXPECTED_CNAME_TARGET}" ]]; then
  echo "OK: CNAME target matches ${EXPECTED_CNAME_TARGET}"
else
  echo "WARN: CNAME target is '${ACTUAL_TARGET}', expected '${EXPECTED_CNAME_TARGET}'"
fi

echo
echo "============================================================"
echo "4) Live DNS + HTTP checks (local machine)"
echo "============================================================"

echo "==> dig CNAME:"
dig "${CUSTOM_HOST}" CNAME +short || true

echo "==> dig TXT asuid:"
dig "asuid.${CUSTOM_HOST}" TXT +short || true

echo
echo "==> curl HTTPS:"
curl -I "https://${CUSTOM_HOST}" || true

echo
echo "✅ Verification script finished."
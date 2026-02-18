#!/usr/bin/env bash
set -euo pipefail
: "${AZ_RG:?set AZ_RG}"
: "${AZ_WEBAPP:?set AZ_WEBAPP}"

echo "== Azure subscription =="
az account show --query "{name:name, id:id}" -o json

echo "== WebApp status =="
az webapp show -g "$AZ_RG" -n "$AZ_WEBAPP" --query "{name:name, state:state, httpsOnly:httpsOnly, hostNames:hostNames}" -o json

echo "== App settings present (names only) =="
az webapp config appsettings list -g "$AZ_RG" -n "$AZ_WEBAPP" --query "[].name" -o tsv | sort

echo "== Latest 50 log lines (if enabled) =="
# Note: log tail requires app logging to be enabled
az webapp log tail -g "$AZ_RG" -n "$AZ_WEBAPP" --provider ApplicationLogs --timeout 15 || true

echo "DONE"

#!/usr/bin/env bash
set -euo pipefail

# ===== Azure =====
export AZ_RG="${AZ_RG:-rg-bhp-platformlab-dev-aue-app}"
export AZ_WEBAPP="${AZ_WEBAPP:-app-bhp-platformlab-dev-aue-gitpushandpray}"
# Optional (if you have more than one subscription)
export AZ_SUBSCRIPTION="${AZ_SUBSCRIPTION:-sub-bhp-platformlab-dev}"

# ===== Public URLs =====
export URL_AZURE="${URL_AZURE:-https://azure.gitpushandpray.ai}"
export URL_AWS="${URL_AWS:-https://aws.gitpushandpray.ai}"

# ===== AWS =====
export AWS_REGION="${AWS_REGION:-ap-southeast-2}"
export AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)}"

# Bedrock Agent ids (fill these in when you want to run invoke tests)
export AGENT_ID="${AGENT_ID:-WXRWRBZ0Q9}"
export AGENT_ALIAS_ID="${AGENT_ALIAS_ID:-GQPZDNAJQY}"
export SESSION_ID="${SESSION_ID:-demo-$(date +%s)}"

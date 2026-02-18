#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-gitpushandpray.ai}"

echo "== NS for root =="
dig NS "$DOMAIN" +short

echo "== Azure subdomain =="
dig CNAME azure."$DOMAIN" +short || true
dig NS azure."$DOMAIN" +short || true

echo "== AWS subdomain =="
dig CNAME aws."$DOMAIN" +short || true
dig NS aws."$DOMAIN" +short || true

echo "== ACM/Cert validation record checks (fill in actual record names) =="
echo "Example:"
echo "  dig CNAME _xxxxxxxx.aws.$DOMAIN +short"
echo "  dig TXT _acme-challenge.azure.$DOMAIN +short"

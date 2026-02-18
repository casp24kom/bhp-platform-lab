#!/usr/bin/env bash
set -euo pipefail
: "${URL_AZURE:?set URL_AZURE}"

echo "== Health =="
curl -fsS "$URL_AZURE/health" | jq .

echo "== Debug env (secrets should be masked/omitted) =="
curl -fsS "$URL_AZURE/debug/env" | jq .

echo "== Snowflake connectivity =="
curl -fsS "$URL_AZURE/debug/sql" | jq .

echo "== Topics metadata (if implemented) =="
curl -fsS "$URL_AZURE/meta/topics" | jq . >/dev/null && echo "OK /meta/topics" || echo "WARN: /meta/topics not available"

echo "== RAG query – strong query (expected to retrieve sources) =="
curl -fsS -X POST "$URL_AZURE/rag/query"   -H "Content-Type: application/json"   -d '{"user_id":"demo","topic":"isolation_loto","topk":5,"question":"What is the lockout tagout procedure before maintenance?"}'   | jq .

echo "== Injection test (if implemented) =="
curl -fsS -X POST "$URL_AZURE/rag/injection_test"   -H "Content-Type: application/json"   | jq . >/dev/null && echo "OK /rag/injection_test" || echo "WARN: /rag/injection_test not available"

echo "== Metrics (if implemented) =="
curl -fsS "$URL_AZURE/metrics" | jq . >/dev/null && echo "OK /metrics" || echo "WARN: /metrics not available"

echo "== Run eval (if implemented) =="
curl -fsS -X POST "$URL_AZURE/eval/run" -H "Content-Type: application/json" | jq . >/dev/null && echo "OK /eval/run" || echo "WARN: /eval/run not available"

echo "DONE"

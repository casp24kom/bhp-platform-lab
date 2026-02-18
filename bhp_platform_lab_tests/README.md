# BHP Platform Lab – Deployment Test Pack

This pack gives you repeatable **smoke tests** for:
- Azure Web App (azure.gitpushandpray.ai)
- Your FastAPI endpoints (/health, /debug/env, /debug/sql, /rag/query, /metrics, /eval/run, /rag/injection_test)
- Snowflake Cortex Search validation (SQL)
- AWS identity + Bedrock Agent invocation via **Boto3** (since AWS CLI may not expose InvokeAgent)
- DNS / certificate validation sanity checks

## 1) Configure environment
Edit and source:

    source ./00_env.sh

## 2) Run tests
Azure + app endpoints:

    ./20_app_smoke.sh

Azure resource sanity:

    ./10_azure_check.sh

AWS identity + agent invoke (Boto3):

    python3 ./31_invoke_agent_boto3.py

DNS checks:

    ./40_dns_check.sh

## Notes
- Scripts use **placeholders** for anything sensitive.
- If Bedrock shows `Too many tokens per day`, you're quota/throttled — try later, request quota, or use a smaller model.

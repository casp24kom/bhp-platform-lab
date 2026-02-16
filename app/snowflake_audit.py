import json
from app.snowflake_conn import get_sf_connection

def audit_dq(
    run_id: str,
    user_id: str,
    verdict: str,
    reasons,
    signals,
    ticket,
    runbook,
    latency_ms: int
):
    sql = """
    INSERT INTO BHP_PLATFORM_LAB.AUDIT.DQ_GATE_RUNS
      (RUN_ID, TS, USER_ID, VERDICT, REASONS, TOOL_SIGNALS, TICKET_DRAFT, RUNBOOK_DRAFT, LATENCY_MS)
    SELECT
      %s,
      CURRENT_TIMESTAMP(),
      %s,
      %s,
      PARSE_JSON(%s),
      PARSE_JSON(%s),
      PARSE_JSON(%s),
      PARSE_JSON(%s),
      %s
    """

    params = (
        run_id,
        user_id,
        verdict,
        json.dumps(reasons or [], ensure_ascii=False),
        json.dumps(signals or [], ensure_ascii=False),
        json.dumps(ticket or {}, ensure_ascii=False),
        json.dumps(runbook or {}, ensure_ascii=False),
        latency_ms,
    )

    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
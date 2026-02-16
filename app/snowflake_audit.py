import json
from app.snowflake_conn import get_sf_connection

def audit_dq(run_id: str, user_id: str, verdict: str, reasons, signals, ticket, runbook, latency_ms: int):
    sql = (
        "INSERT INTO BHP_PLATFORM_LAB.AUDIT.DQ_GATE_RUNS "
        "(RUN_ID, TS, USER_ID, VERDICT, REASONS, TOOL_SIGNALS, TICKET_DRAFT, RUNBOOK_DRAFT, LATENCY_MS) "
        "SELECT ?, CURRENT_TIMESTAMP(), ?, ?, PARSE_JSON(?), PARSE_JSON(?), PARSE_JSON(?), PARSE_JSON(?), ?"
    )

    params = (
        run_id,
        user_id,
        verdict,
        json.dumps(reasons),
        json.dumps(signals),
        json.dumps(ticket),
        json.dumps(runbook),
        latency_ms,
    )

    with get_sf_connection() as conn:
        # Force autocommit for demo inserts (prevents “silent rollback on close”)
        try:
            conn.autocommit(True)
        except Exception:
            pass

        with conn.cursor() as cur:
            cur.execute(sql, params)

        # Belt-and-suspenders in case autocommit isn't supported by your wrapper
        try:
            conn.commit()
        except Exception:
            pass
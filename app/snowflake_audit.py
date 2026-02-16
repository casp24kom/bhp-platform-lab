import json
from app.snowflake_conn import get_sf_connection

import json
from app.snowflake_conn import get_sf_connection

import json
from typing import Any, Mapping, Sequence
from app.snowflake_conn import get_sf_connection

def audit_dq(
    run_id: str,
    user_id: str,
    verdict: str,
    reasons: Any,
    signals: Any,
    ticket: Any,
    runbook: Any,
    latency_ms: int
) -> None:
    insert_sql = (
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
        with conn.cursor() as cur:
            # Context (guard fetchone() possibly returning None)
            cur.execute(
                "SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_DATABASE(), "
                "CURRENT_SCHEMA(), CURRENT_ROLE(), CURRENT_USER()"
            )
            row = cur.fetchone()
            if row is None:
                print("DQ_AUDIT_CONTEXT: <no row returned>")
            else:
                acct, region, db, schema, role, user = row
                print("DQ_AUDIT_CONTEXT:", (acct, region, db, schema, role, user))

            # Do the insert
            cur.execute(insert_sql, params)

            # Verify write (guard fetchone() possibly returning None)
            cur.execute(
                "SELECT COUNT(*) FROM BHP_PLATFORM_LAB.AUDIT.DQ_GATE_RUNS WHERE RUN_ID = ?",
                (run_id,),
            )
            row2 = cur.fetchone()
            wrote = int(row2[0]) if row2 is not None else 0
            print("DQ_AUDIT_WROTE_ROWS_FOR_RUN_ID:", wrote)

        # Safety commit (won't hurt even if autocommit=True)
        try:
            conn.commit()
        except Exception:
            pass
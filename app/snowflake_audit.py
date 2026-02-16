import json
from app.snowflake_conn import get_sf_connection

import json
from app.snowflake_conn import get_sf_connection

import json
from typing import Any, Mapping, Sequence
from app.snowflake_conn import get_sf_connection

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
    latency_ms: int,
):
    sql = """
    INSERT INTO BHP_PLATFORM_LAB.AUDIT.DQ_GATE_RUNS
      (RUN_ID, TS, USER_ID, VERDICT, REASONS, TOOL_SIGNALS, TICKET_DRAFT, RUNBOOK_DRAFT, LATENCY_MS)
    VALUES
      (?, CURRENT_TIMESTAMP(), ?, ?, PARSE_JSON(?), PARSE_JSON(?), PARSE_JSON(?), PARSE_JSON(?), ?)
    """

    params = (
        run_id,
        user_id,
        verdict,
        json.dumps(reasons or []),
        json.dumps(signals or []),
        json.dumps(ticket or {}),
        json.dumps(runbook or {}),
        int(latency_ms),
    )

    with get_sf_connection() as conn:
        # make persistence deterministic
        try:
            conn.autocommit(True)
        except Exception:
            # connector versions differ; ignore if not supported
            pass

        with conn.cursor() as cur:
            cur.execute(sql, params)

        # if autocommit isn't actually on, this ensures data persists
        try:
            conn.commit()
        except Exception:
            pass
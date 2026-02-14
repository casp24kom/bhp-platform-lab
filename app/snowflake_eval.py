import json
from typing import Any, Dict, Optional
from app.snowflake_conn import get_sf_connection
from app.config import settings

EVAL_TABLE = "BHP_PLATFORM_LAB.AUDIT.EVAL_RUNS"

def insert_eval_run(
    run_id: str,
    app_env: str,
    base_url: str,
    n_cases: int,
    metrics: Dict[str, Any],
    extra: Dict[str, Any],
    failures: Any,
) -> None:
    sql = f"""
    INSERT INTO {EVAL_TABLE}
      (RUN_ID, APP_ENV, BASE_URL, N_CASES, METRICS, EXTRA, FAILURES)
    SELECT
      %s, %s, %s, %s,
      PARSE_JSON(%s),
      PARSE_JSON(%s),
      PARSE_JSON(%s)
    """
    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run_id,
                    app_env,
                    base_url,
                    int(n_cases),
                    json.dumps(metrics),
                    json.dumps(extra),
                    json.dumps(failures),
                ),
            )

def get_latest_eval_run() -> Optional[Dict[str, Any]]:
    sql = f"""
    SELECT RUN_ID, RUN_TS, APP_ENV, BASE_URL, N_CASES, METRICS, EXTRA, FAILURES
    FROM {EVAL_TABLE}
    ORDER BY RUN_TS DESC
    LIMIT 1
    """
    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

    if not row:
        return None

    run_id, run_ts, app_env, base_url, n_cases, metrics, extra, failures = row

    # Snowflake connector returns VARIANT as python dict already in many cases,
    # but it can also return JSON string depending on driver settings.
    def _coerce(x):
        if isinstance(x, str):
            try:
                return json.loads(x)
            except Exception:
                return x
        return x

    return {
        "run_id": run_id,
        "run_ts": str(run_ts),
        "app_env": app_env,
        "base_url": base_url,
        "n_cases": int(n_cases) if n_cases is not None else None,
        "metrics": _coerce(metrics) or {},
        "extra": _coerce(extra) or {},
        "failures": _coerce(failures) or [],
    }
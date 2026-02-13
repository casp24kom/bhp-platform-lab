import json
from typing import Any, Dict, List

from app.config import settings
from app.snowflake_conn import get_sf_connection


def get_topics_from_snowflake(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Returns list of topics + label/template/examples + chunk counts by risk tier.
    Source of truth:
      - topics/counts from KB_CHUNKS_TABLE (your SOP_CHUNKS_ENRICHED view)
      - label/template/examples from TOPIC_TEMPLATES_TABLE
    """
    chunks_tbl = settings.kb_chunks_table
    tmpl_tbl = settings.topic_templates_table

    sql = f"""
    WITH topic_counts AS (
      SELECT
        DOC_TOPIC AS TOPIC,
        SUM(IFF(UPPER(DOC_RISK_TIER)='CRITICAL',1,0)) AS CRITICAL,
        SUM(IFF(UPPER(DOC_RISK_TIER)='MEDIUM',1,0))   AS MEDIUM,
        SUM(IFF(UPPER(DOC_RISK_TIER)='LOW',1,0))      AS LOW,
        COUNT(*) AS TOTAL
      FROM {chunks_tbl}
      WHERE DOC_TOPIC IS NOT NULL AND DOC_TOPIC <> ''
      GROUP BY DOC_TOPIC
    )
    SELECT
      c.TOPIC,
      COALESCE(t.LABEL, c.TOPIC) AS LABEL,
      COALESCE(t.TEMPLATE_QUESTION, '') AS TEMPLATE_QUESTION,
      COALESCE(t.EXAMPLES_JSON, '[]') AS EXAMPLES_JSON,
      COALESCE(t.SORT_ORDER, 9999) AS SORT_ORDER,
      c.CRITICAL, c.MEDIUM, c.LOW, c.TOTAL
    FROM topic_counts c
    LEFT JOIN {tmpl_tbl} t
      ON LOWER(t.TOPIC) = LOWER(c.TOPIC)
    ORDER BY SORT_ORDER ASC, LABEL ASC
    LIMIT {int(limit)}
    """

    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    topics: List[Dict[str, Any]] = []
    for (topic, label, template_q, examples_json, sort_order, critical, medium, low, total) in rows:
        try:
            examples = json.loads(examples_json or "[]")
            if not isinstance(examples, list):
                examples = []
        except Exception:
            examples = []

        topics.append({
            "topic": topic,
            "label": label,
            "template": template_q,
            "examples": examples,
            "counts": {
                "CRITICAL": int(critical or 0),
                "MEDIUM": int(medium or 0),
                "LOW": int(low or 0),
                "TOTAL": int(total or 0),
            }
        })

    return topics
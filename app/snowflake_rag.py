import json
import re
from typing import Any, Dict, List, Tuple

from app.snowflake_conn import get_sf_connection
from app.cortex_search_rest import cortex_search_rest

# Pick a model you know is enabled in your Snowflake account/region.
AI_MODEL = "snowflake-arctic"

# -----------------------------
# Helpers
# -----------------------------

def _strip_wrapping_quotes(s: str) -> str:
    """
    Snowflake sometimes returns a JSON-ish quoted string (e.g. "\" answer ... \"").
    This normalizes it to a plain string.
    """
    if not s:
        return s
    s = s.strip()
    # Remove one layer of surrounding quotes if present
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    # Unescape common sequences
    s = s.replace("\\n", "\n").replace('\\"', '"')
    return s.strip()


def _safe_int(x: Any) -> int | None:
    try:
        return int(x)
    except Exception:
        return None


def _normalize_chunk(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Cortex Search results regardless of whether fields come back upper/lower case.
    """
    doc_id = r.get("DOC_ID") or r.get("doc_id")
    doc_name = r.get("DOC_NAME") or r.get("doc_name") or "UnknownDoc"
    chunk_id = _safe_int(r.get("CHUNK_ID") or r.get("chunk_id"))
    chunk_text = r.get("CHUNK_TEXT") or r.get("chunk_text") or ""
    classification = r.get("CLASSIFICATION") or r.get("classification")
    owner = r.get("OWNER") or r.get("owner")
    updated_at = r.get("UPDATED_AT") or r.get("updated_at")
    score = r.get("score") or r.get("_score") or (r.get("@scores") or {}).get("cosine_similarity")

    return {
        "DOC_ID": doc_id,
        "DOC_NAME": doc_name,
        "CHUNK_ID": chunk_id,
        "CHUNK_TEXT": chunk_text,
        "CLASSIFICATION": classification,
        "OWNER": owner,
        "UPDATED_AT": updated_at,
        "SCORE": score,
    }


def _build_sources(chunks: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    lines: List[str] = []
    allowed_tags: List[str] = []

    for c in chunks:
        doc_id = c.get("DOC_ID") or "UNKNOWN"
        doc = c.get("DOC_NAME") or "UnknownDoc"
        cid = c.get("CHUNK_ID")
        text = (c.get("CHUNK_TEXT") or "").strip()

        tag = f"[{doc_id}|{doc}#chunk{cid}]"
        allowed_tags.append(tag)
        lines.append(f"{tag} {text}")

    return "\n".join(lines), allowed_tags

def _answer_contains_any_citation(answer: str, allowed_tags: List[str]) -> bool:
    """
    Deterministic check: answer must include at least one of the allowed tags.
    """
    if not answer:
        return False
    for t in allowed_tags:
        if t in answer:
            return True
    return False


# -----------------------------
# Public API
# -----------------------------

def cortex_search(question: str, topk: int) -> List[Dict[str, Any]]:
    cols = ["DOC_ID", "DOC_NAME", "CHUNK_ID", "CHUNK_TEXT", "CLASSIFICATION", "OWNER", "UPDATED_AT"]
    filter_obj = {"@eq": {"CLASSIFICATION": "PUBLIC"}}

    data = cortex_search_rest(
        database="BHP_PLATFORM_LAB",
        schema="KB",
        service_name="SOP_SEARCH",
        query=question,
        limit=topk,
        columns=cols,
        filter_obj=filter_obj,
    )

    results = data.get("results") or data.get("data") or []
    out = [_normalize_chunk(r) for r in results]

    # Drop empty text rows (rare, but keeps prompt clean)
    out = [c for c in out if (c.get("CHUNK_TEXT") or "").strip()]

    return out


def generate_answer_in_snowflake(question: str, chunks: List[Dict[str, Any]]) -> str:
    """
    Calls Snowflake AI_COMPLETE with strict grounding instructions.
    Enforces that the answer must cite at least one allowed source tag.
    """
    # sources_block, allowed_tags = _build_sources(chunks)
    chunks_for_prompt = chunks[:3]
    sources_block, allowed_tags = _build_sources(chunks_for_prompt)
    
    prompt = (
        "You are an operational mining SOP assistant.\n"
        "Hard rules:\n"
        "1) Use ONLY the SOURCES below.\n"
        "2) Every bullet MUST end with a citation tag exactly as shown in SOURCES.\n"
        "3) If SOURCES are insufficient, reply exactly: CANNOT_ANSWER_FROM_SOURCES\n"
        "4) No generic safety advice beyond SOURCES.\n\n"
        f"QUESTION:\n{question}\n\n"
        f"SOURCES:\n{sources_block}\n\n"
        "OUTPUT FORMAT:\n"
        "- Bullet list of controls/steps.\n"
        "- Each bullet ends with one citation tag.\n"
    )

    sql = "SELECT AI_COMPLETE(%s, %s) AS answer"

    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (AI_MODEL, prompt))
            row = cur.fetchone()
            ans = (row[0] if row else "") or ""

    ans = _strip_wrapping_quotes(ans)

    # Deterministic enforcement: must cite at least one allowed tag unless refusing
    if ans.strip() == "CANNOT_ANSWER_FROM_SOURCES":
        return "Cannot answer from approved sources."

    if not _answer_contains_any_citation(ans, allowed_tags):
        # If the model didn't follow the rules, fail closed.
        return "Cannot answer from approved sources. (Model did not provide grounded citations.)"

    # Optional: remove accidental duplicate "Sources:" sections
    ans = re.sub(r"\n+Sources:\n.*$", "", ans, flags=re.IGNORECASE | re.DOTALL).strip()

    return ans


def audit_rag(
    request_id: str,
    user_id: str,
    question: str,
    topk: int,
    citations: List[Dict[str, Any]],
    answer: str,
    latency_ms: int,
    policy: Dict[str, Any] | None = None,
) -> None:
    """
    Store policy + chunks inside CITATIONS (VARIANT) without changing schema.
    """
    sql = (
        "INSERT INTO BHP_PLATFORM_LAB.AUDIT.RAG_QUERIES "
        "(REQUEST_ID, TS, USER_ID, QUESTION, TOPK, CITATIONS, ANSWER, MODEL, LATENCY_MS) "
        "SELECT %s, CURRENT_TIMESTAMP(), %s, %s, %s, PARSE_JSON(%s), %s, %s, %s"
    )

    payload = {"policy": policy or {}, "chunks": citations}

    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    request_id,
                    user_id,
                    question,
                    topk,
                    json.dumps(payload, ensure_ascii=False),
                    answer,
                    AI_MODEL,
                    latency_ms,
                ),
            )
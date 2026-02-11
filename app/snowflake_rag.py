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
    doc_id = r.get("DOC_ID") or r.get("doc_id")
    doc_name = r.get("DOC_NAME") or r.get("doc_name") or "UnknownDoc"
    chunk_id = _safe_int(r.get("CHUNK_ID") or r.get("chunk_id"))
    chunk_text = r.get("CHUNK_TEXT") or r.get("chunk_text") or ""
    classification = r.get("CLASSIFICATION") or r.get("classification")
    owner = r.get("OWNER") or r.get("owner")
    updated_at = r.get("UPDATED_AT") or r.get("updated_at")
    score = r.get("score") or r.get("_score") or (r.get("@scores") or {}).get("cosine_similarity")

    doc_topic = (r.get("DOC_TOPIC") or r.get("doc_topic") or "general")
    doc_risk_tier = (r.get("DOC_RISK_TIER") or r.get("doc_risk_tier") or "LOW")

    return {
        "DOC_ID": doc_id,
        "DOC_NAME": doc_name,
        "CHUNK_ID": chunk_id,
        "CHUNK_TEXT": chunk_text,
        "CLASSIFICATION": classification,
        "OWNER": owner,
        "UPDATED_AT": updated_at,
        "DOC_TOPIC": doc_topic,
        "DOC_RISK_TIER": doc_risk_tier,
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


def _dedup_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedup by (DOC_ID, CHUNK_ID)."""
    seen: set[Tuple[str, int]] = set()
    out: List[Dict[str, Any]] = []
    for c in chunks:
        doc_id = str(c.get("DOC_ID") or "")
        chunk_id = int(c.get("CHUNK_ID") or -1)
        key = (doc_id, chunk_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _diversify_by_doc(chunks: List[Dict[str, Any]], topk: int) -> List[Dict[str, Any]]:
    """
    Prefer 1 chunk per DOC_ID first. If still need more, fill with remaining chunks.
    Assumes chunks are already sorted best->worst.
    """
    picked: List[Dict[str, Any]] = []
    seen_docs: set[str] = set()

    # Pass 1: one per doc
    for c in chunks:
        doc_id = str(c.get("DOC_ID") or "")
        if doc_id and doc_id not in seen_docs:
            picked.append(c)
            seen_docs.add(doc_id)
            if len(picked) >= topk:
                return picked

    # Pass 2: fill remainder (allows repeat docs)
    for c in chunks:
        if c not in picked:
            picked.append(c)
            if len(picked) >= topk:
                break

    return picked

# -----------------------------
# Public API
# -----------------------------



from typing import Any, Dict, List

def cortex_search(question: str, topk: int, topic_filter: str | None = None) -> List[Dict[str, Any]]:
    cols = [
        "DOC_ID", "DOC_NAME", "CHUNK_ID", "CHUNK_TEXT",
        "CLASSIFICATION", "OWNER", "UPDATED_AT",
        "DOC_TOPIC", "DOC_RISK_TIER",
    ]

    base = {"@eq": {"CLASSIFICATION": "PUBLIC"}}

    if topic_filter and topic_filter != "general":
        filter_obj = {"@and": [base, {"@eq": {"DOC_TOPIC": topic_filter}}]}
    else:
        filter_obj = base

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
    out = [c for c in out if (c.get("CHUNK_TEXT") or "").strip()]

    if not out:
        return []

    # sort best first
    out = sorted(out, key=lambda x: (x.get("SCORE") or 0), reverse=True)

    # de-dup exact duplicates
    out = _dedup_chunks(out)

    # (optional) prefer tiers: CRITICAL > MEDIUM > LOW
    critical = [c for c in out if (c.get("DOC_RISK_TIER") or "").upper() == "CRITICAL"]
    if critical:
        critical = _diversify_by_doc(critical, topk)
        return critical[:topk]

    medium = [c for c in out if (c.get("DOC_RISK_TIER") or "").upper() == "MEDIUM"]
    if medium:
        medium = _diversify_by_doc(medium, topk)
        return medium[:topk]

    # low/general
    out = _diversify_by_doc(out, topk)
    return out[:topk]

def _max_risk_tier(chunks: List[Dict[str, Any]]) -> str:
    order = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}
    best = "LOW"
    for c in chunks or []:
        t = (c.get("DOC_RISK_TIER") or "LOW").upper()
        if t not in order:
            t = "LOW"
        if order[t] > order[best]:
            best = t
    return best


def _select_chunks_for_prompt(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort, dedup, then select a tier-appropriate number of chunks.
    CRITICAL: include more evidence to reduce refusals and improve grounding.
    """
    chunks = sorted(chunks or [], key=lambda x: (x.get("SCORE") or 0), reverse=True)
    chunks = _dedup_chunks(chunks)

    tier = _max_risk_tier(chunks)
    if tier == "CRITICAL":
        return chunks[:8]   # give model more SOP evidence
    if tier == "MEDIUM":
        return chunks[:5]
    return chunks[:3]


def _all_bullets_end_with_allowed_tag(answer: str, allowed_tags: List[str]) -> bool:
    """
    Stronger deterministic enforcement:
    - For each bullet line starting with '-', require it ends with one allowed tag.
    """
    if not answer:
        return False
    lines = [ln.strip() for ln in answer.splitlines() if ln.strip()]
    bullets = [ln for ln in lines if ln.startswith("-")]
    if not bullets:
        return False
    for b in bullets:
        if not any(b.endswith(tag) for tag in allowed_tags):
            return False
    return True


def generate_answer_in_snowflake(question: str, chunks: List[Dict[str, Any]]) -> str:
    """
    Calls Snowflake AI_COMPLETE with strict grounding instructions.
    Enforces that every bullet ends with an allowed citation tag.
    """
    chunks_for_prompt = _select_chunks_for_prompt(chunks)
    sources_block, allowed_tags = _build_sources(chunks_for_prompt)
    risk_tier = _max_risk_tier(chunks_for_prompt)

    prompt = (
        "You are an operational mining SOP assistant.\n"
        "Hard rules:\n"
        "1) Use ONLY the SOURCES below.\n"
        "2) Every bullet MUST end with a citation tag exactly as shown in SOURCES.\n"
        "3) If SOURCES are insufficient, reply exactly: CANNOT_ANSWER_FROM_SOURCES\n"
        "4) Do not add generic advice beyond SOURCES.\n\n"
        f"RISK_TIER: {risk_tier}\n\n"
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

    if ans.strip() == "CANNOT_ANSWER_FROM_SOURCES":
        return "Cannot answer from approved sources."

    # Strong enforcement: EVERY bullet must end with an allowed tag.
    if not _all_bullets_end_with_allowed_tag(ans, allowed_tags):
        return "Cannot answer from approved sources. (Model did not provide fully grounded citations.)"

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
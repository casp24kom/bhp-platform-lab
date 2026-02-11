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

def _max_risk_tier(chunks: List[Dict[str, Any]]) -> str:
    """Highest tier wins: CRITICAL > MEDIUM > LOW."""
    order = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}
    best = "LOW"
    for c in chunks or []:
        t = (c.get("DOC_RISK_TIER") or "LOW").upper()
        if t not in order:
            t = "LOW"
        if order[t] > order[best]:
            best = t
    return best
# -----------------------------
# Public API
# -----------------------------

def cortex_search(question: str, topk: int, topic_filter: str | None = None) -> List[Dict[str, Any]]:
    cols = [
        "DOC_ID", "DOC_NAME", "CHUNK_ID", "CHUNK_TEXT",
        "CLASSIFICATION", "OWNER", "UPDATED_AT",
        "DOC_TOPIC", "DOC_RISK_TIER",
    ]

    base = {"@eq": {"CLASSIFICATION": "PUBLIC"}}

    # Pull more than topk so we can dedup/diversify locally
    retrieve_k = min(max(topk * 10, 50), 200)

    def _run(filter_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = cortex_search_rest(
            database="BHP_PLATFORM_LAB",
            schema="KB",
            service_name="SOP_SEARCH",
            query=question,
            limit=retrieve_k,
            columns=cols,
            filter_obj=filter_obj,
        )
        results = data.get("results") or data.get("data") or []
        out = [_normalize_chunk(r) for r in results]
        out = [c for c in out if (c.get("CHUNK_TEXT") or "").strip()]
        out = sorted(out, key=lambda x: (x.get("SCORE") or 0), reverse=True)
        return _dedup_chunks(out)

    # -----------------------
    # Pass 1: topic-filtered
    # -----------------------
    out: List[Dict[str, Any]] = []
    topic_mode = bool(topic_filter and topic_filter != "general")

    if topic_mode:
        filter_obj_1 = {"@and": [base, {"@eq": {"DOC_TOPIC": topic_filter}}]}
        out = _run(filter_obj_1)
    else:
        out = _run(base)

    # Decide whether to fall back to broader retrieval.
    # IMPORTANT: do NOT fall back just because you have <5 unique docs —
    # some topics legitimately only have a few SOPs (like your confined_space = 4 docs).
    if topic_mode:
        unique_topic_docs = {c.get("DOC_ID") for c in out if c.get("DOC_ID")}
        # Only broaden if we basically got nothing / too little coverage
        need_fallback = (len(out) == 0) or (len(unique_topic_docs) < 2)
        if need_fallback:
            out2 = _run(base)
            out = _dedup_chunks(out + out2)

    # Prefer CRITICAL > MEDIUM > LOW
    critical = [c for c in out if (c.get("DOC_RISK_TIER") or "").upper() == "CRITICAL"]
    if critical:
        return _diversify_by_doc(critical, topk)[:topk]

    medium = [c for c in out if (c.get("DOC_RISK_TIER") or "").upper() == "MEDIUM"]
    if medium:
        return _diversify_by_doc(medium, topk)[:topk]

    return _diversify_by_doc(out, topk)[:topk]

def _select_chunks_for_prompt(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    chunks = sorted(chunks or [], key=lambda x: (x.get("SCORE") or 0), reverse=True)
    chunks = _dedup_chunks(chunks)

    tier = _max_risk_tier(chunks)

    # Infer dominant topic (excluding 'general')
    topics = [
        (c.get("DOC_TOPIC") or "").lower()
        for c in chunks
        if (c.get("DOC_TOPIC") or "").lower() not in ("", "general")
    ]
    preferred_topic: str | None = None
    if topics:
        preferred_topic = max(set(topics), key=topics.count)

    def pick(n: int) -> List[Dict[str, Any]]:
        # Use preferred topic pool if we have it, otherwise use full set
        pool = chunks
        if preferred_topic:
            pool = [c for c in chunks if (c.get("DOC_TOPIC") or "").lower() == preferred_topic]
            if not pool:
                pool = chunks

        # Group by DOC_ID preserving score order
        by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for c in pool:
            doc = str(c.get("DOC_ID") or "")
            by_doc.setdefault(doc, []).append(c)

        # Round-robin selection across docs
        out: List[Dict[str, Any]] = []
        while len(out) < n:
            progressed = False
            for doc_id in list(by_doc.keys()):
                if by_doc[doc_id]:
                    cand = by_doc[doc_id].pop(0)
                    out.append(cand)
                    progressed = True
                    if len(out) >= n:
                        break
            if not progressed:
                break

        # If still short, fill from original chunks (any topic) without duplicates
        if len(out) < n:
            for c in chunks:
                if c not in out:
                    out.append(c)
                if len(out) >= n:
                    break
                # Guard: if we have a preferred_topic, keep at least 70% from it (when possible)
        if preferred_topic:
            in_topic = [c for c in out if (c.get("DOC_TOPIC") or "").lower() == preferred_topic]
            if len(in_topic) >= int(n * 0.7):
                # keep as-is
                return out[:n]
        return out[:n]

    if tier == "CRITICAL":
        return pick(8)
    if tier == "MEDIUM":
        return pick(5)
    return pick(3)

import re
from typing import List

def _bullets_fully_grounded(answer: str, allowed_tags: List[str]) -> bool:
    """
    Robust grounding check.

    Accepts bullets that:
    - start with '-', '*', '•', or '1.' / '1)' numbering
    - may wrap onto following lines
    - must have the final non-empty line of each bullet end with an allowed tag
      (optionally followed by trailing punctuation like '.' or ')')

    This prevents false failures due to formatting differences.
    """
    if not answer or not allowed_tags:
        return False

    # Normalize line endings
    lines = [ln.rstrip() for ln in answer.splitlines()]

    # Build bullet blocks (a bullet can span multiple lines)
    bullet_starts = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
    bullets: List[List[str]] = []
    current: List[str] = []

    for ln in lines:
        if not ln.strip():
            continue

        if bullet_starts.match(ln):
            # start a new bullet
            if current:
                bullets.append(current)
            current = [ln.strip()]
        else:
            # continuation line
            if current:
                current.append(ln.strip())
            else:
                # text before first bullet -> ignore
                continue

    if current:
        bullets.append(current)

    if not bullets:
        return False

    # A regex that matches: ...<allowed_tag><optional trailing punctuation>
    # We escape tags to avoid regex metachar issues.
    tag_patterns = [re.escape(t) for t in allowed_tags]
    tag_re = re.compile(rf"(?:{'|'.join(tag_patterns)})(?:[).,;:]?)\s*$")

    for b in bullets:
        last_line = b[-1]
        if not tag_re.search(last_line):
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
    "Hard rules (the output is automatically rejected if you break these):\n"
    "1) Use ONLY the SOURCES below.\n"
    "2) Write ONLY '-' bullet points (no numbering).\n"
    "3) Every bullet MUST end with exactly ONE citation tag exactly as shown in SOURCES.\n"
    "4) Do NOT put anything after the citation tag (no extra words).\n"
    "5) If SOURCES are insufficient, reply exactly: CANNOT_ANSWER_FROM_SOURCES\n\n"
    "Example format (use the real tags from SOURCES):\n"
    "- Do the thing. [DOC_ID|DOC_NAME#chunkN]\n\n"
    f"RISK_TIER: {risk_tier}\n\n"
    f"QUESTION:\n{question}\n\n"
    f"SOURCES:\n{sources_block}\n\n"
    "OUTPUT:\n"
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

    # Strong enforcement: every bullet block must end with an allowed tag (robust to formatting)
    if not _bullets_fully_grounded(ans, allowed_tags):
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
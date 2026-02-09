import json
from typing import List, Dict
from app.snowflake_conn import get_sf_connection
from app.cortex_search_rest import cortex_search_rest

AI_MODEL = "snowflake-arctic"

def cortex_search(question: str, topk: int) -> List[Dict]:
    cols = ["DOC_ID","DOC_NAME","CHUNK_ID","CHUNK_TEXT","CLASSIFICATION","OWNER","UPDATED_AT"]
    filter_obj = {"@eq": {"CLASSIFICATION": "PUBLIC"}}

    data = cortex_search_rest(
        database="BHP_PLATFORM_LAB",
        schema="KB",
        service_name="SOP_SEARCH",
        query=question,
        limit=topk,
        columns=cols,
        filter_obj=filter_obj
    )

    results = data.get("results") or data.get("data") or []
    out = []
    for r in results:
        out.append({
            "DOC_ID": r.get("DOC_ID"),
            "DOC_NAME": r.get("DOC_NAME"),
            "CHUNK_ID": r.get("CHUNK_ID"),
            "CHUNK_TEXT": r.get("CHUNK_TEXT") or r.get("chunk_text"),
            "CLASSIFICATION": r.get("CLASSIFICATION"),
            "OWNER": r.get("OWNER"),
            "UPDATED_AT": r.get("UPDATED_AT"),
            "SCORE": r.get("score") or r.get("_score"),
        })
    return out

def generate_answer_in_snowflake(question: str, chunks: List[Dict]) -> str:
    sources = []
    for c in chunks:
        sources.append(f"[{c['DOC_NAME']}#chunk{c['CHUNK_ID']}]: {c['CHUNK_TEXT']}")
    context = "\n".join(sources)

    prompt = (
        "You are an SOP assistant.\n"
        "Rules: Use ONLY the provided SOURCES. If insufficient, say you cannot answer.\n"
        "Provide a concise operational answer and cite sources like [Doc#chunk].\n\n"
        f"Question: {question}\n\n"
        f"SOURCES:\n{context}"
    )

    sql = "SELECT AI_COMPLETE(?, ?) AS answer"
    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (AI_MODEL, prompt))
            row = cur.fetchone()
            return row[0] if row else ""

def audit_rag(request_id: str, user_id: str, question: str, topk: int,
              citations: List[Dict], answer: str, latency_ms: int):
    sql = (
        "INSERT INTO BHP_PLATFORM_LAB.AUDIT.RAG_QUERIES "
        "(REQUEST_ID, TS, USER_ID, QUESTION, TOPK, CITATIONS, ANSWER, MODEL, LATENCY_MS) "
        "SELECT ?, CURRENT_TIMESTAMP(), ?, ?, ?, PARSE_JSON(?), ?, ?, ?"
    )
    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                request_id, user_id, question, topk,
                json.dumps(citations), answer, AI_MODEL, latency_ms
            ))

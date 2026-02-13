import os
import time, uuid

from app.refusal import build_helpful_refusal
from app.topics import get_topics_from_snowflake
from typing import Optional, Literal
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from app.policy_gate import enforce_policy, decision_to_dict, _topic_from_question
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.config import settings
from app.snowflake_conn import get_sf_connection
from app.snowflake_rag import cortex_search, generate_answer_in_snowflake, audit_rag
from app.dq_gate import parse_dbt, parse_ge, decide
from app.agentcore_client import call_agentcore
from app.snowflake_audit import audit_dq

app = FastAPI(title="Data & AI Platform Lab", version="1.0")


app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---- UI handling: serve static index if present, else redirect to /docs
@app.get("/", include_in_schema=False)
def root():
    # adjust if your static path differs
    index_path = Path(__file__).resolve().parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return RedirectResponse(url="/docs")


@app.post("/debug/ai")
def debug_ai():
    chunks = [{
        "DOC_NAME": "Synthetic SOP: Isolation",
        "CHUNK_ID": 1,
        "CHUNK_TEXT": "Apply lockout/tagout before maintenance. Verify zero energy state."
    }]
    ans = generate_answer_in_snowflake("What do I do before maintenance?", chunks)
    return {"answer": ans}

@app.get("/debug/env")
def debug_env():
    return {
        "SF_ACCOUNT_IDENTIFIER": os.getenv("SF_ACCOUNT_IDENTIFIER"),
        "SF_ACCOUNT_URL": os.getenv("SF_ACCOUNT_URL"),
        "SF_USER": os.getenv("SF_USER"),
        "settings.sf_account_identifier": settings.sf_account_identifier,
        "settings.sf_account_url": settings.sf_account_url,
        "settings.sf_user": settings.sf_user,
    }
@app.get("/debug/sql")
def debug_sql():
    with get_sf_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_VERSION()")
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="Snowflake returned no rows for debug query")

    a, r, v = row
    return {"account": a, "region": r, "version": v}

AllowedTopic = Literal[
    "general",
    "isolation_loto",
    "confined_space",
    "hot_work",
    "working_at_heights",
    "ppe",
]

class RagRequest(BaseModel):
    user_id: str = "demo"
    question: str
    topk: int = 5
    topic: Optional[str] = Field(default=None, max_length=64)  # allow dynamic topics

class DqRequest(BaseModel):
    user_id: str = "demo"
    dbt_run_results: dict
    ge_validation: dict

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}

@app.get("/meta/topics")
def meta_topics():
    try:
        topics = get_topics_from_snowflake()
        return {"topics": topics}
    except Exception as e:
        # soft-fail so UI can fall back if needed
        return {"topics": [], "error": str(e)}


@app.post("/rag/query")
def rag_query(req: RagRequest):
    request_id = str(uuid.uuid4())
    t0 = time.time()
    try:
        topic = (req.topic or _topic_from_question(req.question) or "general")

        # retrieval filtered by topic
        chunks = cortex_search(req.question, req.topk, topic_filter=topic)

        # NEW: policy uses same topic
        policy_decision = enforce_policy(req.question, chunks, topic_override=topic)
        policy = decision_to_dict(policy_decision)

        def _filter_chunks_for_generation(chs):
            tier = (policy_decision.risk_tier or "LOW").upper()
            if tier == "CRITICAL":
                return [c for c in chs if (c.get("DOC_RISK_TIER") or "").upper() == "CRITICAL"]
            if tier == "MEDIUM":
                return [c for c in chs if (c.get("DOC_RISK_TIER") or "").upper() in ("MEDIUM", "CRITICAL")]
            return chs

        gen_chunks = _filter_chunks_for_generation(chunks)

        # If no chunks OR policy refuses, return helpful refusal (still fail-closed)
        if not chunks or not policy_decision.allow_generation:
            latency_ms = int((time.time() - t0) * 1000)

            help_payload = build_helpful_refusal(
                question=req.question,
                topic=policy_decision.topic or topic,
                risk_tier=(policy_decision.risk_tier or "LOW"),
                reason=(policy_decision.reason or "[REFUSED]"),
                chunks=chunks,
            )

            audit_rag(
                request_id, req.user_id, req.question, req.topk,
                chunks, help_payload["answer"], latency_ms,
                policy=policy
            )

            return {
                "request_id": request_id,
                "answer": help_payload["answer"],
                "policy": policy,
                "citations": help_payload.get("citations", []),
                "latency_ms": latency_ms,
                "refusal": help_payload["refusal"],  # NEW structured details
            }

        # Advice mode: treat as "not supported by SOP excerpts" (fail closed, but helpful)
        if policy_decision.mode == "advice":
            latency_ms = int((time.time() - t0) * 1000)

            help_payload = build_helpful_refusal(
                question=req.question,
                topic=policy_decision.topic or topic,
                risk_tier=(policy_decision.risk_tier or "LOW"),
                reason=("Not explicitly covered by retrieved SOP chunks. " + (policy_decision.reason or "")).strip(),
                chunks=chunks,
            )

            audit_rag(
                request_id, req.user_id, req.question, req.topk,
                chunks, help_payload["answer"], latency_ms,
                policy=policy
            )

            return {
                "request_id": request_id,
                "answer": help_payload["answer"],
                "policy": policy,
                "citations": help_payload.get("citations", []),
                "latency_ms": latency_ms,
                "refusal": help_payload["refusal"],
            }

        # Grounded mode -> generate using tier-filtered chunks
        answer = generate_answer_in_snowflake(req.question, gen_chunks)
        if answer.strip().lower().startswith("cannot answer from approved sources"):
            bullets = []
            for c in gen_chunks[:3]:
                txt = (c.get("CHUNK_TEXT") or "").strip()
                if txt:
                    bullets.append(f"- {txt} [{c.get('DOC_ID')}|{c.get('DOC_NAME')}#chunk{c.get('CHUNK_ID')}]")
            answer = "\n".join(bullets) if bullets else answer
        latency_ms = int((time.time() - t0) * 1000)
        audit_rag(request_id, req.user_id, req.question, req.topk, gen_chunks, answer, latency_ms, policy=policy)

        return {
            "request_id": request_id,
            "answer": answer,
            "policy": policy,
            "citations": gen_chunks,
            "latency_ms": latency_ms,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rag/self_test")
def rag_self_test():
    request_id = str(uuid.uuid4())
    t0 = time.time()
    try:
        with get_sf_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT CURRENT_VERSION()")
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("Snowflake returned no rows for CURRENT_VERSION()")
                sf_version = row[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Snowflake SQL auth failed: {e}")

    test_question = "What is the isolation procedure before maintenance?"
    try:
        chunks = cortex_search(test_question, topk=3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cortex Search REST failed: {e}")

    if not chunks:
        return {"request_id": request_id, "answer": "Cannot answer from approved sources.", "citations": [], "latency_ms": int((time.time()-t0)*1000)}
    
   
    try:
        answer = generate_answer_in_snowflake(test_question, chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI_COMPLETE failed: {e}")

    if answer.strip().lower().startswith("cannot answer from approved sources"):
        answer = "\n".join([
            "Cannot answer from approved sources.",
            "The retrieved SOP excerpts did not specify PPE for conveyor start-up checks.",
            "Add/ingest a PPE-specific SOP section to enable an approved answer.",
        ])

    latency_ms = int((time.time() - t0) * 1000)
    try:
        audit_rag(request_id, "self_test", test_question, 3, chunks, answer, latency_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit insert failed: {e}")

    return {"status": "ok", "request_id": request_id, "snowflake_version": sf_version, "answer_preview": answer[:240], "latency_ms": latency_ms}

@app.post("/dq/evaluate")
def dq_evaluate(req: DqRequest):
    run_id = str(uuid.uuid4())
    t0 = time.time()
    try:
        signals = [parse_dbt(req.dbt_run_results), parse_ge(req.ge_validation)]
        decision = decide(signals)
        agent_out = call_agentcore(decision)
        latency_ms = int((time.time()-t0)*1000)
        audit_dq(run_id, req.user_id, decision["verdict"], decision["reasons"], decision["signals"], agent_out.get("ticket", {}), agent_out.get("runbook", {}), latency_ms)
        return {"run_id": run_id, "verdict": decision["verdict"], "reasons": decision["reasons"], "signals": decision["signals"], "ticket_draft": agent_out.get("ticket", {}), "runbook_draft": agent_out.get("runbook", {}), "latency_ms": latency_ms}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

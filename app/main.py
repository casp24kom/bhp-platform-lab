import os
import time, uuid


from app.policy_gate import policy_gate
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.snowflake_conn import get_sf_connection
from app.snowflake_rag import cortex_search, generate_answer_in_snowflake, audit_rag
from app.dq_gate import parse_dbt, parse_ge, decide
from app.agentcore_client import call_agentcore
from app.snowflake_audit import audit_dq

app = FastAPI(title="Data & AI Platform Lab", version="1.0")

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

class RagRequest(BaseModel):
    user_id: str = "demo"
    question: str
    topk: int = 5

class DqRequest(BaseModel):
    user_id: str = "demo"
    dbt_run_results: dict
    ge_validation: dict

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}

@app.post("/rag/query")
def rag_query(req: RagRequest):
    request_id = str(uuid.uuid4())
    t0 = time.time()
    try:
        chunks = cortex_search(req.question, req.topk)

        policy = policy_gate(req.question, chunks)

        # If no chunks OR policy refuses, return deterministic refusal
        if not chunks or not policy.get("allow_generation", False):
            latency_ms = int((time.time() - t0) * 1000)
            refusal = (
                "Cannot answer from approved sources. "
                + (" " + policy.get("reason", "") if policy.get("reason") else "")
            ).strip()
            audit_rag(request_id, req.user_id, req.question, req.topk, chunks, refusal, latency_ms, policy=policy)
            return {
                "request_id": request_id,
                "answer": refusal,
                "policy": policy,
                "citations": chunks,
                "latency_ms": latency_ms,
            }

        # Allowed -> generate
        answer = generate_answer_in_snowflake(req.question, chunks)
        latency_ms = int((time.time() - t0) * 1000)
        audit_rag(request_id, req.user_id, req.question, req.topk, chunks, answer, latency_ms, policy=policy)

        return {"request_id": request_id, "answer": answer, "policy": policy, "citations": chunks, "latency_ms": latency_ms}

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

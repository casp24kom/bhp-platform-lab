import json
import os
import re
import statistics
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import requests

DEFAULT_BASE_URL = os.getenv("EVAL_BASE_URL", "https://azure.gitpushandpray.ai")
DEFAULT_TOPK = int(os.getenv("EVAL_TOPK", "5"))

CASES_PATH = os.getenv("EVAL_CASES_PATH", "scripts/eval/eval_cases.json")
OUT_PATH = os.getenv("EVAL_OUT_PATH", "app/static/metrics_latest.json")

# --- simple grounding validator for your current answer style ---
CITATION_TAG_RE = re.compile(r"\[[A-Z0-9\-]+?\|.+?#chunk\d+\]")

def safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def extract_doc_ids(citations: List[Dict[str, Any]]) -> List[str]:
    out = []
    for c in citations or []:
        doc_id = c.get("DOC_ID")
        if doc_id:
            out.append(str(doc_id))
    return out

def recall_at_k(expected_any: List[str], retrieved_doc_ids: List[str], k: int) -> int:
    if not expected_any:
        return 1  # if you expected none, count as trivially satisfied
    topk = retrieved_doc_ids[:k]
    return 1 if any(x in topk for x in expected_any) else 0

def mrr_at_k(expected_any: List[str], retrieved_doc_ids: List[str], k: int) -> float:
    if not expected_any:
        return 1.0  # trivial
    topk = retrieved_doc_ids[:k]
    for i, doc in enumerate(topk, start=1):
        if doc in expected_any:
            return 1.0 / i
    return 0.0

def topic_match(expected_topic: str, policy: Dict[str, Any]) -> bool:
    actual = (policy.get("topic") or "general").strip()
    suggested = (policy.get("suggested_topic") or "").strip()
    # count as correct if actual matches OR (actual is general and suggested matches)
    if actual == expected_topic:
        return True
    if actual == "general" and suggested and suggested == expected_topic:
        return True
    return False

def is_grounded_response(resp: Dict[str, Any]) -> bool:
    policy = resp.get("policy") or {}
    allow = bool(policy.get("allow_generation", False))
    mode = (policy.get("mode") or "").strip().lower()
    citations = resp.get("citations") or []
    answer = (resp.get("answer") or "").strip()

    # minimal definition of "grounded" for your current app:
    # - allow_generation true
    # - mode == "grounded"
    # - has citations
    # - answer contains at least one citation tag
    if not allow:
        return False
    if mode != "grounded":
        return False
    if not citations:
        return False
    if not CITATION_TAG_RE.search(answer):
        return False
    return True

def is_hallucination(resp: Dict[str, Any]) -> bool:
    policy = resp.get("policy") or {}
    allow = bool(policy.get("allow_generation", False))
    answer = (resp.get("answer") or "").strip().lower()
    citations = resp.get("citations") or []
    # hallucination = allows generation + answer looks substantive + missing grounding signals
    if not allow:
        return False
    if not answer:
        return False
    # if they explicitly say cannot answer from approved sources, that's not hallucination
    if "cannot answer from approved sources" in answer:
        return False
    # missing citations or missing citation tags is a fail
    if (not citations) or (not CITATION_TAG_RE.search(resp.get("answer") or "")):
        return True
    return False

def p95(values: List[float]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = int(round(0.95 * (len(vals) - 1)))
    return float(vals[idx])

@dataclass
class CaseResult:
    id: str
    pass_allow: bool
    pass_topic: bool
    recall5: int
    mrr5: float
    grounded: bool
    hallucination: bool
    latency_ms: Optional[float]
    expected: Dict[str, Any]
    observed: Dict[str, Any]

def call_rag_query(base_url: str, question: str, topk: int) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/rag/query"
    payload = {"user_id": "eval", "question": question, "topk": topk}
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def call_injection_suite(base_url: str) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/rag/injection_test"
    r = requests.post(url, json={}, timeout=60)
    r.raise_for_status()
    return r.json()

def main():
    base_url = DEFAULT_BASE_URL
    topk = DEFAULT_TOPK

    with open(CASES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results: List[CaseResult] = []
    latencies: List[float] = []

    t_run = time.time()

    for case in cases:
        cid = case["id"]
        q = case["question"]
        expected_topic = (case.get("expected_topic") or "general").strip()
        expected_allow = bool(case.get("expected_allow", False))
        expected_doc_ids_any = case.get("expected_doc_ids_any") or []

        try:
            resp = call_rag_query(base_url, q, topk=topk)
        except Exception as e:
            # treat failures as a bad result
            results.append(CaseResult(
                id=cid,
                pass_allow=False,
                pass_topic=False,
                recall5=0,
                mrr5=0.0,
                grounded=False,
                hallucination=False,
                latency_ms=None,
                expected=case,
                observed={"error": str(e)},
            ))
            continue

        policy = resp.get("policy") or {}
        allow = bool(policy.get("allow_generation", False))
        doc_ids = extract_doc_ids(resp.get("citations") or [])

        r5 = recall_at_k(expected_doc_ids_any, doc_ids, 5)
        mrr5v = mrr_at_k(expected_doc_ids_any, doc_ids, 5)

        grounded = is_grounded_response(resp)
        hallu = is_hallucination(resp)

        lat = resp.get("latency_ms")
        if isinstance(lat, (int, float)):
            latencies.append(float(lat))

        pass_allow = (allow == expected_allow)
        pass_topic = topic_match(expected_topic, policy)

        results.append(CaseResult(
            id=cid,
            pass_allow=pass_allow,
            pass_topic=pass_topic,
            recall5=r5,
            mrr5=mrr5v,
            grounded=grounded,
            hallucination=hallu,
            latency_ms=float(lat) if isinstance(lat, (int, float)) else None,
            expected=case,
            observed={
                "policy": policy,
                "doc_ids": doc_ids[:topk],
            },
        ))

    # Aggregate metrics
    n = len(results)
    allow_acc = sum(1 for r in results if r.pass_allow) / n if n else 0.0
    topic_acc = sum(1 for r in results if r.pass_topic) / n if n else 0.0
    recall5_avg = sum(r.recall5 for r in results) / n if n else 0.0
    mrr5_avg = sum(r.mrr5 for r in results) / n if n else 0.0
    grounded_rate = sum(1 for r in results if r.grounded) / n if n else 0.0
    halluc_rate = sum(1 for r in results if r.hallucination) / n if n else 0.0
    p95_latency = p95(latencies)

    # Injection suite metric
    inj = {"pass_rate": None}
    try:
        inj = call_injection_suite(base_url)
    except Exception as e:
        inj = {"error": str(e), "pass_rate": None}

    run_id = f"eval-{int(t_run)}"
    out = {
        "run_id": run_id,
        "run_ts_unix": int(t_run),
        "base_url": base_url,
        "n_cases": n,
        # 8 metrics:
        "metrics": {
            "recall_at_5": round(recall5_avg, 4),
            "mrr_at_5": round(mrr5_avg, 4),
            "grounded_answer_rate": round(grounded_rate, 4),
            "hallucination_rate": round(halluc_rate, 4),
            "allow_deny_accuracy": round(allow_acc, 4),
            "prompt_injection_pass_rate": inj.get("pass_rate"),
            "p95_latency_ms": int(p95_latency) if p95_latency else None,
            "tool_call_success_rate": None  # N/A unless you add tracking
        },
        # extra helpful breakdowns:
        "extra": {
            "topic_accuracy": round(topic_acc, 4),
            "latency_ms_count": len(latencies),
            "injection_suite": inj,
        },
        "failures": [
            {
                "id": r.id,
                "expected": r.expected,
                "observed": r.observed,
                "flags": {
                    "pass_allow": r.pass_allow,
                    "pass_topic": r.pass_topic,
                    "recall5": r.recall5,
                    "mrr5": r.mrr5,
                    "grounded": r.grounded,
                    "hallucination": r.hallucination,
                }
            }
            for r in results
            if (not r.pass_allow) or (not r.pass_topic) or (r.recall5 == 0) or r.hallucination
        ]
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote metrics to: {OUT_PATH}")
    print(json.dumps(out["metrics"], indent=2))


if __name__ == "__main__":
    main()
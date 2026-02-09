from typing import Dict, Any, List

def parse_dbt(run_results: Dict[str, Any]) -> Dict[str, Any]:
    results = run_results.get("results", []) or []
    failed_tests = 0
    status_counts = {}

    for r in results:
        status = r.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        uid = r.get("unique_id", "")
        if uid.startswith("test.") and status in ["fail", "error"]:
            failed_tests += 1

    overall = "success"
    if status_counts.get("error", 0) > 0:
        overall = "error"
    elif status_counts.get("fail", 0) > 0:
        overall = "fail"

    return {"tool":"dbt","status":overall,"failed_tests":failed_tests,"status_counts":status_counts}

def parse_ge(validation: Dict[str, Any]) -> Dict[str, Any]:
    return {"tool":"great_expectations","success":bool(validation.get("success", False)),
            "statistics":validation.get("statistics", {}), "meta":validation.get("meta", {})}

def decide(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    verdict = "PASS"
    reasons = []
    for s in signals:
        if s["tool"] == "dbt":
            if s["status"] in ["error","fail"]:
                verdict = "FAIL"
                reasons.append(f"dbt status: {s['status']}")
            if s.get("failed_tests", 0) > 0:
                verdict = "FAIL"
                reasons.append(f"dbt failed tests: {s['failed_tests']}")
        if s["tool"] == "great_expectations":
            if s.get("success") is False:
                verdict = "FAIL"
                reasons.append("GE validation failed")
    return {"verdict": verdict, "reasons": reasons, "signals": signals}

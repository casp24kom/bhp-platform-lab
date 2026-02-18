import json, os, urllib.request

AGENTCORE_BASE = os.environ["AGENTCORE_BASE"].rstrip("/")
AGENTCORE_PATH = os.environ.get("AGENTCORE_PATH", "/agentcore/invoke")
TIMEOUT_S = int(os.environ.get("TIMEOUT_S", "20"))

def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}

def _get_prop(event: dict, name: str):
    rb = (event.get("requestBody") or {}).get("content") or {}
    aj = rb.get("application/json") or {}
    props = aj.get("properties") or {}
    # Bedrock commonly puts values under properties
    return props.get(name) or aj.get(name) or event.get(name)

def lambda_handler(event, context):
    # Support both schema names: prompt (current) and question (older)
    prompt = (_get_prop(event, "prompt") or _get_prop(event, "question") or "").strip()

    if not prompt:
        result = {"answer": "Missing required parameter: prompt"}
        status = 400
    else:
        url = f"{AGENTCORE_BASE}{AGENTCORE_PATH}"
        out = _post_json(url, {"question": prompt})
        # Return answer string; keep raw for debugging
        if isinstance(out, dict) and "answer" in out and isinstance(out["answer"], str):
            result = {"answer": out["answer"], "raw": out}
        else:
            result = {"answer": json.dumps(out)[:4000], "raw": out}
        status = 200

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", "agentcore-tool"),
            "apiPath": event.get("apiPath", "/invokeAgentCore"),
            "httpMethod": event.get("httpMethod", "POST"),
            "httpStatusCode": status,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(result)
                }
            }
        }
    }

import json, os, urllib.request

AGENTCORE_BASE = os.environ["AGENTCORE_BASE"].rstrip("/")
AGENTCORE_PATH = os.environ.get("AGENTCORE_PATH", "/agentcore/invoke")
TIMEOUT_S = int(os.environ.get("TIMEOUT_S", "20"))

def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}

def lambda_handler(event, context):
    url = f"{AGENTCORE_BASE}{AGENTCORE_PATH}"
    out = _post_json(url, {"event": event})
    return {"statusCode": 200, "body": json.dumps(out)}

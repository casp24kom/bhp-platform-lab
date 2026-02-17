import os, json, urllib.request

AGENTCORE_URL = os.environ["AGENTCORE_URL"]  # e.g. https://YOUR_AGENTCORE_URL/execute
API_KEY       = os.environ.get("AGENTCORE_API_KEY","")

def handler(event, context):
    body = event.get("body")
    if isinstance(body, str):
        body = json.loads(body)

    req = urllib.request.Request(
        url=AGENTCORE_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type":"application/json","X-Api-Key": API_KEY},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = resp.read().decode("utf-8")

    return {"statusCode":200,"headers":{"Content-Type":"application/json"},"body":out}
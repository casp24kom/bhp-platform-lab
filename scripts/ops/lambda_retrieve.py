import os, json, urllib.request

APP_BASE = os.environ["APP_BASE"]  # e.g. https://aws.gitpushandpray.ai
API_KEY  = os.environ.get("TOOL_API_KEY", "")

def handler(event, context):
    body = event.get("body")
    if isinstance(body, str):
        body = json.loads(body)

    query = body.get("query", "")

    req = urllib.request.Request(
        url=f"{APP_BASE}/tool/retrieve",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Tool-Api-Key": API_KEY
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        out = resp.read().decode("utf-8")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": out
    }
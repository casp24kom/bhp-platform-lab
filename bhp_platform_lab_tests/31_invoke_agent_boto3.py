#!/usr/bin/env python3
import os
import boto3

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
AGENT_ID = os.environ["AGENT_ID"]
AGENT_ALIAS_ID = os.environ["AGENT_ALIAS_ID"]
SESSION_ID = os.environ.get("SESSION_ID", "demo-session-1")

client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)

print("Invoking agent (streaming)...")
resp = client.invoke_agent(
    agentId=AGENT_ID,
    agentAliasId=AGENT_ALIAS_ID,
    sessionId=SESSION_ID,
    inputText="Hello. In one sentence, explain what you are and what you can do.",
    enableTrace=True,
)

final_text_parts = []
trace_events = []

for event in resp["completion"]:
    if "chunk" in event:
        final_text_parts.append(event["chunk"]["bytes"].decode("utf-8"))
    if "trace" in event:
        trace_events.append(event["trace"])

print("\n=== ANSWER ===")
print("".join(final_text_parts))
print("\n=== TRACE EVENTS ===")
print(len(trace_events))

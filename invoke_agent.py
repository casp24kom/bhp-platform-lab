import os
import boto3

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
AGENT_ID = os.environ["AGENT_ID"]
AGENT_ALIAS_ID = os.environ["AGENT_ALIAS_ID"]
SESSION_ID = os.environ.get("SESSION_ID", "demo-session-1")

client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)

resp = client.invoke_agent(
    agentId=AGENT_ID,
    agentAliasId=AGENT_ALIAS_ID,
    sessionId=SESSION_ID,
    inputText="Call the agentcore-tool with prompt: 'Hello from Bedrock agent. Summarise what you return.'",
    enableTrace=True,
)

final_text_parts = []
trace_events = []

# resp["completion"] is a streaming iterator of events
for event in resp["completion"]:
    if "chunk" in event:
        # chunk bytes -> text
        final_text_parts.append(event["chunk"]["bytes"].decode("utf-8"))
    if "trace" in event:
        trace_events.append(event["trace"])

print("=== ANSWER ===")
print("".join(final_text_parts))

print("\n=== TRACE EVENTS (count) ===")
print(len(trace_events))
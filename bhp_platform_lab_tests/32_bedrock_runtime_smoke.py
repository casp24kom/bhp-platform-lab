#!/usr/bin/env python3
import os, json
import boto3
from botocore.exceptions import ClientError

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
MODEL_ID = os.environ.get("MODEL_ID")  # e.g. an inference profile ARN

if not MODEL_ID:
    raise SystemExit("Set MODEL_ID (e.g. Bedrock inference profile ARN)")

br = boto3.client("bedrock-runtime", region_name=AWS_REGION)

body = {
  "anthropic_version": "bedrock-2023-05-31",
  "max_tokens": 32,
  "messages": [
    {"role": "user", "content": [{"type": "text", "text": "Say hello in one short sentence."}]}
  ]
}

try:
    resp = br.invoke_model(
      modelId=MODEL_ID,
      contentType="application/json",
      accept="application/json",
      body=json.dumps(body).encode("utf-8"),
    )
    print(resp["body"].read().decode("utf-8")[:800])
except ClientError as e:
    print("ClientError:", e)

import json, os
from functools import lru_cache

import boto3

@lru_cache(maxsize=1)
def get_secret_json(secret_id: str, region: str) -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_id)
    s = resp.get("SecretString")
    if not s:
        raise RuntimeError(f"SecretString empty for secret_id={secret_id}")
    return json.loads(s)

def hydrate_env_from_secrets_manager():
    """
    If SF_SECRET_ID is set, pull the Snowflake JSON secret and
    set missing SF_* env vars (do not overwrite if already set).
    """
    secret_id = os.getenv("SF_SECRET_ID")
    if not secret_id:
        return

    region = os.getenv("AWS_REGION") or os.getenv("AGENTCORE_REGION") or "ap-southeast-2"
    data = get_secret_json(secret_id, region)

    for k, v in data.items():
        if k and (os.getenv(k) is None or os.getenv(k) == ""):
            os.environ[k] = str(v)
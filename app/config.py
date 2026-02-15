from dotenv import load_dotenv
load_dotenv()
from pydantic import BaseModel
import os, base64


# NEW: pull SF_* from AWS Secrets Manager if SF_SECRET_ID is set
from app.aws_secrets import hydrate_env_from_secrets_manager
hydrate_env_from_secrets_manager()

from pydantic import BaseModel
import os, base64

import json
import boto3
import os

def _hydrate_from_secrets_manager():
    secret_id = os.getenv("SF_SECRET_ID", "")
    if not secret_id:
        return

    # Only hydrate if not already provided via env
    if os.getenv("SF_PRIVATE_KEY_PEM_B64") or os.getenv("SF_PRIVATE_KEY_PEM_PATH"):
        return

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-2"
    sm = boto3.client("secretsmanager", region_name=region)
    resp = sm.get_secret_value(SecretId=secret_id)
    data = json.loads(resp["SecretString"])

    # Put into process env so Settings() picks it up
    for k in ["SF_PRIVATE_KEY_PEM_B64","SF_ACCOUNT_IDENTIFIER","SF_ACCOUNT_URL","SF_USER","SF_PUBLIC_KEY_FP"]:
        if k in data and data[k]:
            os.environ.setdefault(k, data[k])

_hydrate_from_secrets_manager()
class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "prod-demo")
    data_dir: str = os.getenv("DATA_DIR", "/data")
    
    kb_chunks_table: str = os.getenv(
    "KB_CHUNKS_TABLE",
    "BHP_PLATFORM_LAB.KB.SOP_CHUNKS_ENRICHED"  # <-- IMPORTANT: use your VIEW
    )

    topic_templates_table: str = os.getenv(
    "TOPIC_TEMPLATES_TABLE",
    "BHP_PLATFORM_LAB.KB.TOPIC_TEMPLATES"
    )
    sf_private_key_pem_path: str = os.getenv("SF_PRIVATE_KEY_PEM_PATH", "")
    sf_account_identifier: str = os.getenv("SF_ACCOUNT_IDENTIFIER", "")
    sf_account_url: str = os.getenv("SF_ACCOUNT_URL", "")
    sf_user: str = os.getenv("SF_USER", "")
    sf_role: str = os.getenv("SF_ROLE", "BHP_LAB_APP_ROLE")
    sf_warehouse: str = os.getenv("SF_WAREHOUSE", "BHP_LAB_WH")
    sf_database: str = os.getenv("SF_DATABASE", "BHP_PLATFORM_LAB")
    sf_schema: str = os.getenv("SF_SCHEMA", "KB")
    sf_private_key_pem_b64: str = os.getenv("SF_PRIVATE_KEY_PEM_B64", "")
    sf_public_key_fp: str = os.getenv("SF_PUBLIC_KEY_FP", "")

    agentcore_region: str = os.getenv("AGENTCORE_REGION", "ap-southeast-2")
    agentcore_endpoint: str = os.getenv("AGENTCORE_ENDPOINT", "https://bedrock-agentcore.ap-southeast-2.amazonaws.com")
    agentcore_agent_id: str = os.getenv("AGENTCORE_AGENT_ID", "")

import json
import boto3

def _load_sf_from_secrets_manager():
    secret_name = os.getenv("SF_SECRET_NAME", "")
    if not secret_name:
        return

    # Only fill missing values (don’t overwrite App Runner env vars)
    sm = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "ap-southeast-2"))
    resp = sm.get_secret_value(SecretId=secret_name)
    data = json.loads(resp.get("SecretString") or "{}")

    for k, v in data.items():
        if v is None:
            continue
        if os.getenv(k, "") == "":
            os.environ[k] = str(v)

_load_sf_from_secrets_manager()

settings = Settings()

def load_private_key_pem_bytes() -> bytes:
    """
    Returns PEM bytes (not DER) from either:
    - SF_PRIVATE_KEY_PEM_PATH (preferred), or
    - SF_PRIVATE_KEY_PEM_B64 (fallback)
    """
    path = (settings.sf_private_key_pem_path or "").strip()

    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()

    b64 = (settings.sf_private_key_pem_b64 or "").strip()
    if b64:
        return base64.b64decode(b64)

    raise RuntimeError("Missing SF_PRIVATE_KEY_PEM_PATH (valid file) or SF_PRIVATE_KEY_PEM_B64")

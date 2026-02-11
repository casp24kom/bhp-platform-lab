from dotenv import load_dotenv
load_dotenv()
from pydantic import BaseModel
import os, base64

class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "prod-demo")
    data_dir: str = os.getenv("DATA_DIR", "/data")

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

settings = Settings()

def load_private_key_pem_bytes() -> bytes:
    """
    Returns PEM bytes (not DER) from either:
    - SF_PRIVATE_KEY_PEM_PATH (preferred), or
    - SF_PRIVATE_KEY_PEM_B64 (fallback)
    """
    if settings.sf_private_key_pem_path:
        with open(settings.sf_private_key_pem_path, "rb") as f:
            return f.read()

    if settings.sf_private_key_pem_b64:
        return base64.b64decode(settings.sf_private_key_pem_b64)

    raise RuntimeError("Missing SF_PRIVATE_KEY_PEM_PATH or SF_PRIVATE_KEY_PEM_B64")

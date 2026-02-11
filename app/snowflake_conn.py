import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from app.config import settings, load_private_key_pem_bytes

def _account_locator_from_url(url: str) -> str:
    host = url.replace("https://", "").split("/")[0]
    return host.split(".")[0]

def _private_key_der() -> bytes:
    pem = load_private_key_pem_bytes()

    key = serialization.load_pem_private_key(
        pem,
        password=None,
        backend=default_backend(),
    )

    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

def get_sf_connection():
    # Fail fast first
    if not settings.sf_user:
        raise RuntimeError("SF_USER is missing/blank")
    if not settings.sf_account_url:
        raise RuntimeError("SF_ACCOUNT_URL is missing/blank")
    if not settings.sf_role:
        raise RuntimeError("SF_ROLE is missing/blank")
    if not settings.sf_warehouse:
        raise RuntimeError("SF_WAREHOUSE is missing/blank")

    account_locator = _account_locator_from_url(settings.sf_account_url)
    private_key_der = _private_key_der()

    return snowflake.connector.connect(
        account=settings.sf_account_identifier,
        user=settings.sf_user,
        private_key=private_key_der,
        role=settings.sf_role,
        warehouse=settings.sf_warehouse,
        database=settings.sf_database,
        schema=settings.sf_schema,
    )
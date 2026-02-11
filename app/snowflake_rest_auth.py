import time
import jwt
from app.config import settings, load_private_key_pem_bytes

_JWT_CACHE = {"token": None, "exp": 0}

def _upper(s: str) -> str:
    return (s or "").upper()

def generate_snowflake_rest_jwt() -> str:
    now = int(time.time())
    if _JWT_CACHE["token"] and (now + 120) < _JWT_CACHE["exp"]:
        return _JWT_CACHE["token"]

    acct = _upper(settings.sf_account_identifier)
    user = _upper(settings.sf_user)
    fp = settings.sf_public_key_fp
    if not acct:
        raise RuntimeError("Missing SF_ACCOUNT_IDENTIFIER")
    if not user:
        raise RuntimeError("Missing SF_USER")
    if not fp.startswith("SHA256:"):
        raise RuntimeError("SF_PUBLIC_KEY_FP must look like 'SHA256:<hash>'")

    iss = f"{acct}.{user}.{fp}"
    sub = f"{acct}.{user}"
    exp = now + 55 * 60

    payload = {"iss": iss, "sub": sub, "iat": now, "exp": exp}
    token = jwt.encode(payload, load_private_key_pem_bytes(), algorithm="RS256")

    _JWT_CACHE["token"] = token
    _JWT_CACHE["exp"] = exp
    return token

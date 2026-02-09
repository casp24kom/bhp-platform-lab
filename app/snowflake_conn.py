import snowflake.connector
from app.config import settings, load_private_key_pem

def _account_locator_from_url(url: str) -> str:
    host = url.replace("https://", "").split("/")[0]
    return host.split(".")[0]

def get_sf_connection():
    pk = load_private_key_pem()
    account_locator = _account_locator_from_url(settings.sf_account_url)

    return snowflake.connector.connect(
        account=account_locator,
        user=settings.sf_user,
        private_key=pk,
        role=settings.sf_role,
        warehouse=settings.sf_warehouse,
        database=settings.sf_database,
        schema=settings.sf_schema,
    )

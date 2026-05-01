"""Shared Google service account credential loader."""
import json
import os

from google.oauth2 import service_account


def get_google_credentials(scopes: list[str]) -> service_account.Credentials:
    """Return Google service account credentials for the given scopes.

    Reads from ``GOOGLE_CREDENTIALS_JSON`` env var (GitHub Actions) or falls
    back to ``credentials/google_service_account.json`` for local dev.
    Using ``from_service_account_info`` avoids writing credentials to disk.
    """
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        info = json.loads(creds_json)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return service_account.Credentials.from_service_account_file(
        "credentials/google_service_account.json", scopes=scopes
    )

import os
import tempfile

from google.oauth2 import service_account
from googleapiclient.discovery import build

from argus.core.logger import get_logger

log = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_service():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(creds_json)
            creds_path = f.name
    else:
        creds_path = "credentials/google_service_account.json"

    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=_SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def append_signal_row(
    sheet_id: str,
    competitor: str,
    label: str,
    reasoning: str,
    source_url: str,
    detected_at: str,
) -> None:
    """Append one row to Sheet1 columns A–E."""
    service = _get_service()
    values = [[detected_at, competitor, label, reasoning, source_url]]
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sheet1!A:E",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()
    log.info("Sheet row appended: %s / %s", competitor, label)

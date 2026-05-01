"""Google Sheets API client for appending competitive signal rows."""
from googleapiclient.discovery import build

from argus.core.logger import get_logger
from argus.integrations.google_auth import get_google_credentials

log = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_service():
    """Return an authenticated Google Sheets API service client."""
    return build("sheets", "v4", credentials=get_google_credentials(_SCOPES))


def append_signal_row(
    sheet_id: str,
    competitor: str,
    label: str,
    reasoning: str,
    source_url: str,
    detected_at: str,
) -> None:
    """Append one signal row to Sheet1 columns A-E (Detected At, Competitor, Label, Reasoning, Source URL)."""
    service = _get_service()
    values = [[detected_at, competitor, label, reasoning, source_url]]
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sheet1!A:E",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()
    log.info("Sheet row appended: %s / %s", competitor, label)

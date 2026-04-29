import os
import tempfile
from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

from argus.core.logger import get_logger

log = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        # GitHub Actions: credentials stored as JSON string in env var
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(creds_json)
            creds_path = f.name
    else:
        creds_path = "credentials/google_service_account.json"

    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=_SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def create_strategy_event(
    calendar_id: str,
    title: str,
    description: str,
    date: datetime,
    duration_minutes: int = 30,
) -> str:
    """Create a calendar event. Returns the event HTML link."""
    service = _get_service()
    start = date.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=duration_minutes)
    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        "reminders": {"useDefault": True},
    }
    event = service.events().insert(calendarId=calendar_id, body=body).execute()
    link = event.get("htmlLink", "")
    log.info("Calendar event created: %s", title)
    return link

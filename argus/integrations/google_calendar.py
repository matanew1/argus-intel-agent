"""Google Calendar API client for creating strategy review events."""
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build

from argus.core.logger import get_logger
from argus.integrations.google_auth import get_google_credentials

log = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    """Return an authenticated Google Calendar API service client."""
    return build("calendar", "v3", credentials=get_google_credentials(_SCOPES))


def create_strategy_event(
    calendar_id: str,
    title: str,
    description: str,
    date: datetime,
    duration_minutes: int = 30,
) -> str:
    """Create a calendar event at 9:00 UTC on the given date. Returns the event HTML link."""
    service = _get_service()
    start = date.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
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

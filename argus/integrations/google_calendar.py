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
) -> tuple[str, str]:
    """Create a calendar event at 9:00 UTC on the given date.

    Returns ``(event_id, html_link)`` so callers can update the event later.
    """
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
    log.info("Calendar event created: %s", title)
    return event.get("id", ""), event.get("htmlLink", "")


def append_url_to_event(calendar_id: str, event_id: str, new_url: str) -> None:
    """Append *new_url* to an existing event's description (no-op if already present)."""
    service = _get_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    current_desc = event.get("description", "")
    if new_url in current_desc:
        return
    updated_desc = current_desc + f"\nSource: {new_url}"
    service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body={"description": updated_desc},
    ).execute()
    log.info("Appended URL to calendar event %s", event_id)

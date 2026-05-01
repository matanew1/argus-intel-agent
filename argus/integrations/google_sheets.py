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
    """Append one signal row to the first sheet, columns A-E, with black text formatting."""
    service = _get_service()
    values = [[detected_at, competitor, label, reasoning, source_url]]
    resp = service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A:E",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()

    # Parse the row index from the updated range (e.g. "גיליון1!A5:E5" → row 5 → index 4)
    updated_range = resp.get("updates", {}).get("updatedRange", "")
    row_index = _parse_row_index(updated_range)
    if row_index is not None:
        _apply_black_text(service, sheet_id, row_index)

    log.info("Sheet row appended: %s / %s", competitor, label)


def _parse_row_index(updated_range: str) -> int | None:
    """Extract the 0-based row index from a Sheets updated range string like 'Sheet1!A5:E5'."""
    try:
        # Range format: [SheetName!]StartCell:EndCell — grab the first cell's row number
        cell_part = updated_range.split("!")[-1]        # e.g. "A5:E5"
        start_cell = cell_part.split(":")[0]            # e.g. "A5"
        row_number = int("".join(c for c in start_cell if c.isdigit()))
        return row_number - 1                           # convert to 0-based
    except (ValueError, IndexError):
        return None


def _apply_black_text(service, sheet_id: str, row_index: int) -> None:
    """Apply black text colour to all cells in the given 0-based row index."""
    black = {"red": 0.0, "green": 0.0, "blue": 0.0}
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "startRowIndex": row_index,
                            "endRowIndex":   row_index + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex":   5,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"foregroundColor": black}
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.foregroundColor",
                    }
                }
            ]
        },
    ).execute()

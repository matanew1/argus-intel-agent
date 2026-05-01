"""Deduplication helpers: fingerprint generation and seen-item tracking."""
import hashlib
from typing import Any

from argus.core.database import get_session
from argus.core.models import SeenItem


def make_fingerprint(workflow: str, identifier: str) -> str:
    """Return a SHA-256 hex digest of ``workflow::identifier``.

    Deterministic — same inputs always produce the same fingerprint.
    """
    raw = f"{workflow}::{identifier}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_seen(fingerprint: str) -> bool:
    """Return True if this fingerprint already exists in seen_items."""
    with get_session() as session:
        return (
            session.query(SeenItem)
            .filter_by(fingerprint=fingerprint)
            .first()
        ) is not None


def get_seen_source_url(fingerprint: str) -> str | None:
    """Return the stored source_url for a seen fingerprint, if present."""
    with get_session() as session:
        row = (
            session.query(SeenItem.source_url)
            .filter_by(fingerprint=fingerprint)
            .first()
        )
        return row[0] if row else None


def mark_seen(
    fingerprint: str,
    workflow: str,
    item_type: str,
    source_url: str | None = None,
    label: str | None = None,
    acted_on: bool = False,
) -> None:
    """Insert a SeenItem row for fingerprint if one does not already exist."""
    with get_session() as session:
        if not session.query(SeenItem).filter_by(fingerprint=fingerprint).first():
            session.add(
                SeenItem(
                    fingerprint=fingerprint,
                    workflow=workflow,
                    item_type=item_type,
                    source_url=source_url,
                    label=label,
                    acted_on=acted_on,
                )
            )


def filter_unseen(
    items: list[dict[str, Any]],
    workflow: str,
    id_key: str,
) -> list[dict[str, Any]]:
    """Return only items whose id_key value has not been seen before.

    Adds a ``_fingerprint`` key to each returned item for use with mark_seen().
    """
    unseen: list[dict[str, Any]] = []
    for item in items:
        fp = make_fingerprint(workflow, str(item[id_key]))
        if not is_seen(fp):
            item["_fingerprint"] = fp
            unseen.append(item)
    return unseen

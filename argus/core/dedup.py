import hashlib
from typing import Any

from argus.core.database import get_session
from argus.core.models import SeenItem


def make_fingerprint(workflow: str, identifier: str) -> str:
    raw = f"{workflow}::{identifier}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_seen(fingerprint: str) -> bool:
    with get_session() as session:
        return (
            session.query(SeenItem)
            .filter_by(fingerprint=fingerprint)
            .first()
        ) is not None


def mark_seen(
    fingerprint: str,
    workflow: str,
    item_type: str,
    source_url: str | None = None,
    label: str | None = None,
    acted_on: bool = False,
) -> None:
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
    """Return only items whose id_key has not been seen before."""
    unseen: list[dict[str, Any]] = []
    for item in items:
        fp = make_fingerprint(workflow, str(item[id_key]))
        if not is_seen(fp):
            item["_fingerprint"] = fp
            unseen.append(item)
    return unseen

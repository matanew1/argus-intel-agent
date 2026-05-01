"""SQLAlchemy ORM models for all argus database tables."""
import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from argus.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SeenItem(Base):
    """Deduplication table — one row per processed item.

    The ``fingerprint`` column (SHA-256 of ``workflow::identifier``) is the
    unique key used to detect previously processed articles, job postings, and
    page diffs.
    """

    __tablename__ = "seen_items"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(64), unique=True, nullable=False, index=True)
    workflow    = Column(String(50), nullable=False)
    item_type   = Column(String(50), nullable=False)
    source_url  = Column(Text, nullable=True)
    first_seen  = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    label       = Column(String(50), nullable=True)
    acted_on    = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_seen_workflow_first_seen", "workflow", "first_seen"),
    )


class RunLog(Base):
    """Audit trail for every workflow execution.

    ``decisions``, ``actions_taken``, and ``errors`` are stored as JSON arrays
    and mutated through the helper methods below.
    """

    __tablename__ = "run_log"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    workflow         = Column(String(50), nullable=False, index=True)
    trigger_time     = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    items_processed  = Column(Integer, default=0)
    decisions        = Column(Text, default="[]")
    actions_taken    = Column(Text, default="[]")
    errors           = Column(Text, default="[]")
    duration_seconds = Column(Integer, nullable=True)

    def add_decision(self, item_id: str, label: str, reasoning: str) -> None:
        """Append an LLM classification decision to the decisions JSON array."""
        data = json.loads(self.decisions)
        data.append({"item_id": item_id, "label": label, "reasoning": reasoning})
        self.decisions = json.dumps(data)

    def add_action(self, action: str, target: str, status: str, detail: str = "") -> None:
        """Append a completed action (Slack post, calendar event, etc.) to actions_taken."""
        data = json.loads(self.actions_taken)
        data.append({"action": action, "target": target, "status": status, "detail": detail})
        self.actions_taken = json.dumps(data)

    def add_error(self, error: str, tb: str = "") -> None:
        """Append an error message and optional traceback to the errors JSON array."""
        data = json.loads(self.errors)
        data.append({"error": error, "traceback": tb})
        self.errors = json.dumps(data)

    __table_args__ = (
        Index("ix_run_log_workflow_trigger", "workflow", "trigger_time"),
    )


class Config(Base):
    """Hot-reloadable config snapshot; always a single row with id=1."""

    __tablename__ = "config"

    id            = Column(Integer, primary_key=True, default=1)
    updated_at    = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    competitors   = Column(Text, default="[]")   # JSON
    criteria      = Column(Text, default="")
    notifications = Column(Text, default="{}")   # JSON


class PageSnapshot(Base):
    """Last-known text and hash of a competitor pricing/product page.

    Used by PricingWatchWorkflow to detect content changes between runs.
    """

    __tablename__ = "page_snapshots"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    url          = Column(Text, unique=True, nullable=False)
    content_hash = Column(String(64), nullable=False)
    content_text = Column(Text, nullable=False)
    captured_at  = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

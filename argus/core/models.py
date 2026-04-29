import json
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from argus.core.database import Base


class SeenItem(Base):
    __tablename__ = "seen_items"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(64), unique=True, nullable=False, index=True)
    workflow    = Column(String(50), nullable=False)
    item_type   = Column(String(50), nullable=False)
    source_url  = Column(Text, nullable=True)
    first_seen  = Column(DateTime, default=datetime.utcnow, nullable=False)
    label       = Column(String(50), nullable=True)
    acted_on    = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_seen_workflow_first_seen", "workflow", "first_seen"),
    )


class RunLog(Base):
    __tablename__ = "run_log"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    workflow         = Column(String(50), nullable=False, index=True)
    trigger_time     = Column(DateTime, default=datetime.utcnow, nullable=False)
    items_processed  = Column(Integer, default=0)
    decisions        = Column(Text, default="[]")
    actions_taken    = Column(Text, default="[]")
    errors           = Column(Text, default="[]")
    duration_seconds = Column(Integer, nullable=True)

    def add_decision(self, item_id: str, label: str, reasoning: str) -> None:
        data = json.loads(self.decisions)
        data.append({"item_id": item_id, "label": label, "reasoning": reasoning})
        self.decisions = json.dumps(data)

    def add_action(self, action: str, target: str, status: str, detail: str = "") -> None:
        data = json.loads(self.actions_taken)
        data.append({"action": action, "target": target, "status": status, "detail": detail})
        self.actions_taken = json.dumps(data)

    def add_error(self, error: str, tb: str = "") -> None:
        data = json.loads(self.errors)
        data.append({"error": error, "traceback": tb})
        self.errors = json.dumps(data)

    __table_args__ = (
        Index("ix_run_log_workflow_trigger", "workflow", "trigger_time"),
    )


class Config(Base):
    """Hot-reloadable config; always a single row with id=1."""
    __tablename__ = "config"

    id            = Column(Integer, primary_key=True, default=1)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    competitors   = Column(Text, default="[]")   # JSON
    criteria      = Column(Text, default="")
    notifications = Column(Text, default="{}")   # JSON


class PageSnapshot(Base):
    __tablename__ = "page_snapshots"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    url          = Column(Text, unique=True, nullable=False)
    content_hash = Column(String(64), nullable=False)
    content_text = Column(Text, nullable=False)
    captured_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

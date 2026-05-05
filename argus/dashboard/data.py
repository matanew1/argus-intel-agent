"""Database queries, formatters, and data helpers for the Argus dashboard."""
import base64
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from argus.core.database import SessionLocal
from argus.core.models import PageSnapshot, RunLog, SeenItem

LOGO_PATH = ROOT_DIR / "assets" / "logo.png"
PAGE_ICON = str(LOGO_PATH) if LOGO_PATH.exists() else "A"
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

_REFRESH_TTL = 30
_SUMMARY_COLUMNS = ["workflow", "last_run", "total_runs", "total_items"]
_RUN_COLUMNS = ["workflow", "trigger_time", "items_processed", "duration_seconds", "errors", "actions_taken"]
_WORKFLOW_MANIFEST = [
    {"workflow": "news_watch",    "name": "News Watch",                 "cadence": "Every 2 hours UTC",   "file": ".github/workflows/news-watch.yml"},
    {"workflow": "pricing_watch", "name": "Pricing & Site Change Watch","cadence": "Daily 8am UTC",       "file": ".github/workflows/pricing-watch.yml"},
    {"workflow": "job_watch",     "name": "Job Posting Watch",          "cadence": "Daily 9am UTC",       "file": ".github/workflows/job-watch.yml"},
    {"workflow": "weekly_digest", "name": "Weekly Digest",              "cadence": "Friday 4pm UTC",      "file": ".github/workflows/weekly-digest.yml"},
]


# --- JSON helpers ---

def _json_array(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _is_missing_table_error(exc: SQLAlchemyError) -> bool:
    original = getattr(exc, "orig", exc)
    pgcode = getattr(original, "pgcode", "")
    message = str(original).lower()
    return (
        pgcode == "42P01"
        or "undefinedtable" in message
        or 'relation "run_log" does not exist' in message
        or "no such table" in message
    )


# --- Formatters ---

def humanize_time(dt: datetime | None) -> str:
    if dt is None or pd.isna(dt):
        return "never"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def format_dt(dt: datetime | None) -> str:
    if dt is None or pd.isna(dt):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_dt_israel(dt: datetime | None) -> str:
    if dt is None or pd.isna(dt):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ISRAEL_TZ).strftime("%Y-%m-%d %H:%M %Z")


def format_number(value: int | float) -> str:
    if isinstance(value, float):
        value = round(value, 1)
    return f"{value:,}"


# --- Cached DB loaders ---

@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_error_rate(hours: int = 24) -> dict:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).all()
        total = len(logs)
        errored = sum(1 for row in logs if _json_array(row.errors))
        return {"total": total, "errored": errored, "rate": (errored / total * 100) if total else 0, "state": "ready"}
    except SQLAlchemyError as exc:
        session.rollback()
        state = "missing_tables" if _is_missing_table_error(exc) else "db_error"
        return {"total": 0, "errored": 0, "rate": 0, "state": state}
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_run_summary() -> pd.DataFrame:
    session = SessionLocal()
    try:
        rows = (
            session.query(
                RunLog.workflow,
                func.max(RunLog.trigger_time).label("last_run"),
                func.count(RunLog.id).label("total_runs"),
                func.sum(RunLog.items_processed).label("total_items"),
            )
            .group_by(RunLog.workflow)
            .all()
        )
        return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)
    except SQLAlchemyError:
        session.rollback()
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_recent_actions(n: int = 20) -> list[dict]:
    session = SessionLocal()
    try:
        logs = session.query(RunLog).order_by(RunLog.trigger_time.desc()).limit(60).all()
        rows = []
        for log in logs:
            for action in _json_array(log.actions_taken):
                rows.append({
                    "time": log.trigger_time, "workflow": log.workflow,
                    "action": action.get("action", ""), "target": action.get("target", ""),
                    "status": action.get("status", ""), "detail": action.get("detail", ""),
                })
        return rows[:n]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_actions_since(days: int = 30) -> list[dict]:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        logs = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).order_by(RunLog.trigger_time.desc()).all()
        rows = []
        for log in logs:
            for action in _json_array(log.actions_taken):
                rows.append({
                    "time": log.trigger_time, "workflow": log.workflow,
                    "action": action.get("action", ""), "target": action.get("target", ""),
                    "status": action.get("status", ""), "detail": action.get("detail", ""),
                })
        return rows
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_error_logs(hours: int = 24) -> list[dict]:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).order_by(RunLog.trigger_time.desc()).all()
        return [{"workflow": row.workflow, "trigger_time": row.trigger_time, "errors": row.errors} for row in rows]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_recent_decisions(n: int = 40) -> list[dict]:
    session = SessionLocal()
    try:
        logs = session.query(RunLog).order_by(RunLog.trigger_time.desc()).limit(100).all()
        rows = []
        for log in logs:
            for decision in _json_array(log.decisions):
                rows.append({
                    "time": log.trigger_time, "workflow": log.workflow,
                    "item_id": decision.get("item_id", ""),
                    "label": decision.get("label", ""),
                    "reasoning": decision.get("reasoning", ""),
                })
        return rows[:n]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_runs_since(hours: int = 48) -> list[dict]:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).order_by(RunLog.trigger_time.desc()).all()
        return [
            {
                "workflow": row.workflow, "trigger_time": row.trigger_time,
                "items_processed": row.items_processed,
                "decisions": len(_json_array(row.decisions)),
                "actions": len(_json_array(row.actions_taken)),
                "errors": len(_json_array(row.errors)),
            }
            for row in logs
        ]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_run_bounds() -> dict:
    session = SessionLocal()
    try:
        first_run, last_run, total_runs = session.query(
            func.min(RunLog.trigger_time),
            func.max(RunLog.trigger_time),
            func.count(RunLog.id),
        ).one()
        span_hours = 0.0
        if first_run and last_run:
            if first_run.tzinfo is None:
                first_run = first_run.replace(tzinfo=timezone.utc)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            span_hours = (last_run - first_run).total_seconds() / 3600
        return {"first_run": first_run, "last_run": last_run, "total_runs": int(total_runs or 0), "span_hours": span_hours}
    except SQLAlchemyError:
        session.rollback()
        return {"first_run": None, "last_run": None, "total_runs": 0, "span_hours": 0.0}
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_run_history(n: int = 20) -> list[dict]:
    session = SessionLocal()
    try:
        logs = session.query(RunLog).order_by(RunLog.trigger_time.desc()).limit(n).all()
        return [
            {
                "workflow": row.workflow, "trigger_time": row.trigger_time,
                "items_processed": row.items_processed, "duration_seconds": row.duration_seconds,
                "decisions": _json_array(row.decisions),
                "actions": _json_array(row.actions_taken),
                "errors": _json_array(row.errors),
            }
            for row in logs
        ]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_seen_summary() -> pd.DataFrame:
    session = SessionLocal()
    try:
        rows = (
            session.query(
                SeenItem.workflow, SeenItem.item_type,
                func.count(SeenItem.id).label("count"),
                func.max(SeenItem.first_seen).label("latest_seen"),
            )
            .group_by(SeenItem.workflow, SeenItem.item_type)
            .order_by(func.max(SeenItem.first_seen).desc())
            .all()
        )
        return pd.DataFrame(rows, columns=["workflow", "item_type", "count", "latest_seen"])
    except SQLAlchemyError:
        session.rollback()
        return pd.DataFrame(columns=["workflow", "item_type", "count", "latest_seen"])
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_page_snapshots(n: int = 20) -> pd.DataFrame:
    session = SessionLocal()
    try:
        rows = (
            session.query(PageSnapshot.url, PageSnapshot.content_hash, PageSnapshot.captured_at)
            .order_by(PageSnapshot.captured_at.desc())
            .limit(n)
            .all()
        )
        return pd.DataFrame(rows, columns=["url", "content_hash", "captured_at"])
    except SQLAlchemyError:
        session.rollback()
        return pd.DataFrame(columns=["url", "content_hash", "captured_at"])
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL, show_spinner=False)
def load_recent_runs(n: int = 8) -> pd.DataFrame:
    session = SessionLocal()
    try:
        rows = (
            session.query(
                RunLog.workflow, RunLog.trigger_time, RunLog.items_processed,
                RunLog.duration_seconds, RunLog.errors, RunLog.actions_taken,
            )
            .order_by(RunLog.trigger_time.desc())
            .limit(n)
            .all()
        )
        return pd.DataFrame(rows, columns=_RUN_COLUMNS)
    except SQLAlchemyError:
        session.rollback()
        return pd.DataFrame(columns=_RUN_COLUMNS)
    finally:
        session.close()


@st.cache_data(ttl=3600, show_spinner=False)
def logo_data_uri(path: str) -> str:
    logo_file = Path(path)
    if not logo_file.exists():
        return ""
    encoded = base64.b64encode(logo_file.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def load_scheduler_manifest() -> pd.DataFrame:
    rows = []
    for item in _WORKFLOW_MANIFEST:
        path = ROOT_DIR / item["file"]
        text = path.read_text() if path.exists() else ""
        cron_match = re.search(r"cron:\s*['\"]?([^'\"\n#]+)", text)
        command_match = re.search(r"run:\s*(python -m argus\.workflows\.[\w_]+)", text)
        rows.append({
            "workflow": item["workflow"], "name": item["name"], "cadence": item["cadence"],
            "cron": cron_match.group(1).strip() if cron_match else "",
            "command": command_match.group(1).strip() if command_match else "",
            "file": item["file"],
        })
    return pd.DataFrame(rows)


# --- Business logic ---

def status_profile(err: dict) -> dict:
    if err.get("state") == "missing_tables":
        return {"level": "warning", "label": "No logbook yet", "message": "Argus is ready. Run a workflow once to populate the database."}
    if err.get("state") == "db_error":
        return {"level": "error", "label": "Database offline", "message": "Cannot read the workflow log. Check DATABASE_URL and connectivity."}
    if err["rate"] == 0 and err["total"] > 0:
        return {"level": "success", "label": "Operational", "message": f"{err['total']} run(s) in the last 24h with zero errors."}
    if err["total"] == 0:
        return {"level": "info", "label": "Standby", "message": "No workflow runs in the last 24h."}
    return {"level": "error", "label": "Needs review", "message": f"{err['errored']} errored run(s), {err['rate']:.1f}% error rate in 24h."}


def health_score(err: dict) -> int:
    if err.get("state") == "missing_tables":
        return 0
    if err.get("state") == "db_error":
        return 15
    if err["total"] == 0:
        return 42
    return max(0, min(100, round(100 - err["rate"])))


def dashboard_totals(summary_df: pd.DataFrame, actions: list[dict], recent_runs: pd.DataFrame, err: dict) -> dict:
    durations = recent_runs["duration_seconds"].dropna() if not recent_runs.empty else []
    return {
        "score": health_score(err),
        "workflow_count": 0 if summary_df.empty else len(summary_df),
        "item_count": 0 if summary_df.empty else int(summary_df["total_items"].fillna(0).sum()),
        "run_count": 0 if summary_df.empty else int(summary_df["total_runs"].fillna(0).sum()),
        "action_count": len(actions),
        "avg_duration": int(durations.mean()) if len(durations) else 0,
    }


# --- Table formatters ---

def to_table(rows: list[dict], date_fields: tuple[str, ...] = ("time", "trigger_time")) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for field in date_fields:
        if field in df.columns:
            df[field] = df[field].apply(format_dt)
    return df


def summary_table(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df
    table = summary_df.copy()
    table["last_run_israel"] = summary_df["last_run"].apply(format_dt_israel)
    table["last_run_utc"] = summary_df["last_run"].apply(format_dt)
    table["last_seen"] = summary_df["last_run"].apply(humanize_time)
    return table[["workflow", "last_seen", "last_run_israel", "last_run_utc", "total_runs", "total_items"]]


def recent_runs_table(recent_runs: pd.DataFrame) -> pd.DataFrame:
    if recent_runs.empty:
        return pd.DataFrame(columns=["workflow", "israel_time", "utc_time", "items", "duration", "errors", "actions"])
    table = recent_runs.copy()
    table["israel_time"] = table["trigger_time"].apply(format_dt_israel)
    table["utc_time"] = table["trigger_time"].apply(format_dt)
    table["errors"] = table["errors"].apply(lambda raw: len(_json_array(raw)))
    table["actions"] = table["actions_taken"].apply(lambda raw: len(_json_array(raw)))
    table = table.rename(columns={"items_processed": "items", "duration_seconds": "duration"})
    return table[["workflow", "israel_time", "utc_time", "items", "duration", "errors", "actions"]]


def runs_since_table(runs: list[dict]) -> pd.DataFrame:
    table = to_table(runs, date_fields=("trigger_time",))
    if table.empty:
        return pd.DataFrame(columns=["workflow", "israel_time", "utc_time", "items", "decisions", "actions", "errors"])
    original_times = [row["trigger_time"] for row in runs]
    table["israel_time"] = [format_dt_israel(v) for v in original_times]
    table["utc_time"] = [format_dt(v) for v in original_times]
    table = table.rename(columns={"items_processed": "items"})
    return table[["workflow", "israel_time", "utc_time", "items", "decisions", "actions", "errors"]]


def seen_summary_table(seen_summary: pd.DataFrame) -> pd.DataFrame:
    if seen_summary.empty:
        return seen_summary
    table = seen_summary.copy()
    table["latest_seen"] = table["latest_seen"].apply(format_dt)
    return table


def page_snapshots_table(snapshots: pd.DataFrame) -> pd.DataFrame:
    if snapshots.empty:
        return snapshots
    table = snapshots.copy()
    table["captured_at"] = table["captured_at"].apply(format_dt)
    table["content_hash"] = table["content_hash"].str.slice(0, 12)
    return table


def artifact_rows(actions_30d: list[dict], snapshots: pd.DataFrame, seen_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, action_names, system in [
        ("Slack alerts",    {"slack_post", "slack_dm", "slack_channel"}, "Slack"),
        ("Calendar events", {"calendar_event"},                          "Google Calendar"),
        ("Sheet rows",      {"sheets_append"},                           "Google Sheets"),
        ("Digest emails",   {"email"},                                   "Resend"),
    ]:
        matches = [row for row in actions_30d if row["action"] in action_names]
        latest = matches[0] if matches else None
        rows.append({
            "artifact": label, "system": system,
            "status": "Observed" if latest else "Needs real run",
            "latest_israel": format_dt_israel(latest["time"]) if latest else "",
            "proof": _artifact_proof(latest) if latest else "",
        })

    if snapshots.empty:
        rows.append({"artifact": "Pricing snapshots", "system": "page_snapshots", "status": "Needs baseline run", "latest_israel": "", "proof": ""})
    else:
        s = snapshots.iloc[0]
        rows.append({"artifact": "Pricing snapshots", "system": "page_snapshots", "status": "Observed", "latest_israel": format_dt_israel(s["captured_at"]), "proof": s["url"]})

    if seen_summary.empty:
        rows.append({"artifact": "Dedup rows", "system": "seen_items", "status": "Needs news/job run", "latest_israel": "", "proof": ""})
    else:
        total_seen = int(seen_summary["count"].fillna(0).sum())
        rows.append({"artifact": "Dedup rows", "system": "seen_items", "status": "Observed", "latest_israel": format_dt_israel(seen_summary["latest_seen"].max()), "proof": f"{total_seen} seen item(s)"})

    return pd.DataFrame(rows)


def _artifact_proof(row: dict | None) -> str:
    if not row:
        return ""
    proof = row.get("detail") or row.get("target") or ""
    if len(proof) > 90:
        proof = f"{proof[:87]}..."
    return f"{row.get('workflow', '')}: {row.get('action', '')} -> {proof}"

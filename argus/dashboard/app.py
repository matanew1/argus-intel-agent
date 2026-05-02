"""Streamlit dashboard for Argus workflow health and activity."""
import base64
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

st.set_page_config(page_title="Argus Intel", layout="wide", page_icon=PAGE_ICON)

_SUMMARY_COLUMNS = ["workflow", "last_run", "total_runs", "total_items"]
_RUN_COLUMNS = [
    "workflow",
    "trigger_time",
    "items_processed",
    "duration_seconds",
    "errors",
    "actions_taken",
]
_REFRESH_TTL_SECONDS = 30
_WORKFLOW_MANIFEST = [
    {
        "workflow": "news_watch",
        "name": "News Watch",
        "cadence": "Every 2 hours at :17 UTC",
        "file": ".github/workflows/news-watch.yml",
    },
    {
        "workflow": "pricing_watch",
        "name": "Pricing & Site Change Watch",
        "cadence": "Daily 8am UTC",
        "file": ".github/workflows/pricing-watch.yml",
    },
    {
        "workflow": "job_watch",
        "name": "Job Posting Watch",
        "cadence": "Daily 9am UTC",
        "file": ".github/workflows/job-watch.yml",
    },
    {
        "workflow": "weekly_digest",
        "name": "Weekly Digest",
        "cadence": "Friday 4pm UTC",
        "file": ".github/workflows/weekly-digest.yml",
    },
]
_PIPELINE_STEPS = [
    ("01", "Scheduler fires", "GitHub Actions cron starts a workflow on its configured cadence.", "GitHub Actions"),
    ("02", "Config loads", "ConfigLoader reads competitors, criteria, and notification targets.", "config.yaml"),
    ("03", "Signals collected", "The workflow fetches news, jobs, pricing pages, or prior run logs.", "Integrations"),
    ("04", "State checked", "Seen items dedup articles/jobs; page snapshots detect pricing changes.", "Postgres"),
    ("05", "LLM classifies", "Mistral returns a structured label with reasoning and confidence.", "Mistral"),
    ("06", "Decision logged", "The label and reasoning are appended to run_log.decisions.", "run_log"),
    ("07", "Action dispatched", "Actionable signals create Slack, Calendar, Sheets, or email artifacts.", "External apps"),
    ("08", "Proof surfaces", "Dashboard reads run_log, seen_items, and page_snapshots for demo evidence.", "Streamlit"),
]


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_error_rate(hours: int = 24) -> dict:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).all()
        total = len(logs)
        errored = sum(1 for row in logs if _json_array(row.errors))
        return {
            "total": total,
            "errored": errored,
            "rate": (errored / total * 100) if total else 0,
            "state": "ready",
        }
    except SQLAlchemyError as exc:
        session.rollback()
        state = "missing_tables" if _is_missing_table_error(exc) else "db_error"
        return {"total": 0, "errored": 0, "rate": 0, "state": state}
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
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


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_recent_actions(n: int = 20) -> list[dict]:
    session = SessionLocal()
    try:
        logs = session.query(RunLog).order_by(RunLog.trigger_time.desc()).limit(60).all()
        rows = []
        for log in logs:
            for action in _json_array(log.actions_taken):
                rows.append(
                    {
                        "time": log.trigger_time,
                        "workflow": log.workflow,
                        "action": action.get("action", ""),
                        "target": action.get("target", ""),
                        "status": action.get("status", ""),
                        "detail": action.get("detail", ""),
                    }
                )
        return rows[:n]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_actions_since(days: int = 30) -> list[dict]:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        logs = (
            session.query(RunLog)
            .filter(RunLog.trigger_time >= cutoff)
            .order_by(RunLog.trigger_time.desc())
            .all()
        )
        rows = []
        for log in logs:
            for action in _json_array(log.actions_taken):
                rows.append(
                    {
                        "time": log.trigger_time,
                        "workflow": log.workflow,
                        "action": action.get("action", ""),
                        "target": action.get("target", ""),
                        "status": action.get("status", ""),
                        "detail": action.get("detail", ""),
                    }
                )
        return rows
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_error_logs(hours: int = 24) -> list[dict]:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = (
            session.query(RunLog)
            .filter(RunLog.trigger_time >= cutoff)
            .order_by(RunLog.trigger_time.desc())
            .all()
        )
        return [
            {"workflow": row.workflow, "trigger_time": row.trigger_time, "errors": row.errors}
            for row in rows
        ]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_recent_decisions(n: int = 40) -> list[dict]:
    session = SessionLocal()
    try:
        logs = session.query(RunLog).order_by(RunLog.trigger_time.desc()).limit(100).all()
        rows = []
        for log in logs:
            for decision in _json_array(log.decisions):
                rows.append(
                    {
                        "time": log.trigger_time,
                        "workflow": log.workflow,
                        "item_id": decision.get("item_id", ""),
                        "label": decision.get("label", ""),
                        "reasoning": decision.get("reasoning", ""),
                    }
                )
        return rows[:n]
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_runs_since(hours: int = 48) -> list[dict]:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs = (
            session.query(RunLog)
            .filter(RunLog.trigger_time >= cutoff)
            .order_by(RunLog.trigger_time.desc())
            .all()
        )
        return [
            {
                "workflow": row.workflow,
                "trigger_time": row.trigger_time,
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


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
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
        return {
            "first_run": first_run,
            "last_run": last_run,
            "total_runs": int(total_runs or 0),
            "span_hours": span_hours,
        }
    except SQLAlchemyError:
        session.rollback()
        return {"first_run": None, "last_run": None, "total_runs": 0, "span_hours": 0.0}
    finally:
        session.close()


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_run_history(n: int = 20) -> list[dict]:
    session = SessionLocal()
    try:
        logs = session.query(RunLog).order_by(RunLog.trigger_time.desc()).limit(n).all()
        return [
            {
                "workflow": row.workflow,
                "trigger_time": row.trigger_time,
                "items_processed": row.items_processed,
                "duration_seconds": row.duration_seconds,
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


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_seen_summary() -> pd.DataFrame:
    session = SessionLocal()
    try:
        rows = (
            session.query(
                SeenItem.workflow,
                SeenItem.item_type,
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


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
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


@st.cache_data(ttl=_REFRESH_TTL_SECONDS)
def load_recent_runs(n: int = 8) -> pd.DataFrame:
    session = SessionLocal()
    try:
        rows = (
            session.query(
                RunLog.workflow,
                RunLog.trigger_time,
                RunLog.items_processed,
                RunLog.duration_seconds,
                RunLog.errors,
                RunLog.actions_taken,
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


def status_profile(err: dict) -> dict:
    if err.get("state") == "missing_tables":
        return {
            "level": "warning",
            "label": "No logbook yet",
            "message": "Argus is ready. Run a workflow once to populate the database.",
        }
    if err.get("state") == "db_error":
        return {
            "level": "error",
            "label": "Database offline",
            "message": "Cannot read the workflow log. Check DATABASE_URL and connectivity.",
        }
    if err["rate"] == 0 and err["total"] > 0:
        return {
            "level": "success",
            "label": "Operational",
            "message": f"{err['total']} run(s) in the last 24h with zero errors.",
        }
    if err["total"] == 0:
        return {
            "level": "info",
            "label": "Standby",
            "message": "No workflow runs in the last 24h.",
        }
    return {
        "level": "error",
        "label": "Needs review",
        "message": f"{err['errored']} errored run(s), {err['rate']:.1f}% error rate in 24h.",
    }


def health_score(err: dict) -> int:
    if err.get("state") == "missing_tables":
        return 0
    if err.get("state") == "db_error":
        return 15
    if err["total"] == 0:
        return 42
    return max(0, min(100, round(100 - err["rate"])))


def dashboard_totals(
    summary_df: pd.DataFrame,
    actions: list[dict],
    recent_runs: pd.DataFrame,
    err: dict,
) -> dict:
    durations = recent_runs["duration_seconds"].dropna() if not recent_runs.empty else []
    return {
        "score": health_score(err),
        "workflow_count": 0 if summary_df.empty else len(summary_df),
        "item_count": 0 if summary_df.empty else int(summary_df["total_items"].fillna(0).sum()),
        "run_count": 0 if summary_df.empty else int(summary_df["total_runs"].fillna(0).sum()),
        "action_count": len(actions),
        "avg_duration": int(durations.mean()) if len(durations) else 0,
    }


@st.cache_data(ttl=3600)
def logo_data_uri(path: str) -> str:
    logo_file = Path(path)
    if not logo_file.exists():
        return ""
    encoded = base64.b64encode(logo_file.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def format_number(value: int | float) -> str:
    if isinstance(value, float):
        value = round(value, 1)
    return f"{value:,}"


def load_scheduler_manifest() -> pd.DataFrame:
    rows = []
    for item in _WORKFLOW_MANIFEST:
        path = ROOT_DIR / item["file"]
        text = path.read_text() if path.exists() else ""
        cron_match = re.search(r"cron:\s*['\"]?([^'\"\n#]+)", text)
        command_match = re.search(r"run:\s*(python -m argus\.workflows\.[\w_]+)", text)
        rows.append(
            {
                "workflow": item["workflow"],
                "name": item["name"],
                "cadence": item["cadence"],
                "cron": cron_match.group(1).strip() if cron_match else "",
                "command": command_match.group(1).strip() if command_match else "",
                "file": item["file"],
            }
        )
    return pd.DataFrame(rows)


def artifact_rows(actions_30d: list[dict], snapshots: pd.DataFrame, seen_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    action_groups = [
        ("Slack alerts", {"slack_post", "slack_dm", "slack_channel"}, "Slack"),
        ("Calendar events", {"calendar_event"}, "Google Calendar"),
        ("Sheet rows", {"sheets_append"}, "Google Sheets"),
        ("Digest emails", {"email"}, "Resend"),
    ]
    for label, action_names, system in action_groups:
        matches = [row for row in actions_30d if row["action"] in action_names]
        latest = matches[0] if matches else None
        rows.append(
            {
                "artifact": label,
                "system": system,
                "status": "Observed" if latest else "Needs real run",
                "latest": format_dt(latest["time"]) if latest else "",
                "proof": _artifact_proof(latest) if latest else "",
            }
        )

    if snapshots.empty:
        rows.append(
            {
                "artifact": "Pricing snapshots",
                "system": "page_snapshots",
                "status": "Needs baseline run",
                "latest": "",
                "proof": "",
            }
        )
    else:
        latest_snapshot = snapshots.iloc[0]
        rows.append(
            {
                "artifact": "Pricing snapshots",
                "system": "page_snapshots",
                "status": "Observed",
                "latest": format_dt(latest_snapshot["captured_at"]),
                "proof": latest_snapshot["url"],
            }
        )

    if seen_summary.empty:
        rows.append(
            {
                "artifact": "Dedup rows",
                "system": "seen_items",
                "status": "Needs news/job run",
                "latest": "",
                "proof": "",
            }
        )
    else:
        total_seen = int(seen_summary["count"].fillna(0).sum())
        latest_seen = seen_summary["latest_seen"].max()
        rows.append(
            {
                "artifact": "Dedup rows",
                "system": "seen_items",
                "status": "Observed",
                "latest": format_dt(latest_seen),
                "proof": f"{total_seen} seen item(s)",
            }
        )
    return pd.DataFrame(rows)


def _artifact_proof(row: dict | None) -> str:
    if not row:
        return ""
    detail = row.get("detail") or ""
    target = row.get("target") or ""
    workflow = row.get("workflow") or ""
    action = row.get("action") or ""
    proof = detail or target
    if len(proof) > 90:
        proof = f"{proof[:87]}..."
    return f"{workflow}: {action} -> {proof}"


def render_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        
        :root {
            --argus-bg: #f8fafc;
            --argus-panel: #ffffff;
            --argus-panel-soft: #f1f5f9;
            --argus-border: #e2e8f0;
            --argus-border-strong: #cbd5e1;
            --argus-text: #0f172a;
            --argus-muted: #64748b;
            --argus-navy: #0f172a;
            --argus-blue: #3b82f6;
            --argus-teal: #0d9488;
            --argus-amber: #d97706;
            --argus-red: #dc2626;
            --argus-green: #16a34a;
        }
        html, body, [data-testid="stAppViewContainer"] {
            background: var(--argus-bg);
            color: var(--argus-text);
            font-family: 'Inter', sans-serif;
        }
        [data-testid="stHeader"] {
            background: rgba(248, 250, 252, 0.85);
            backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--argus-border);
        }
        .block-container {
            max-width: 1280px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }
        h1, h2, h3 { color: var(--argus-text); letter-spacing: -0.02em; }
        h1 { font-size: 2.25rem; font-weight: 800; line-height: 1.1; margin: 0; }
        h2 { font-size: 1.25rem; font-weight: 700; margin-top: 1.5rem; }
        
        /* Splash Screen Loader */
        .argus-splash-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 60vh;
            animation: fadeIn 0.3s ease-in;
        }
        .argus-splash-spinner {
            width: 48px;
            height: 48px;
            border: 4px solid var(--argus-panel-soft);
            border-top: 4px solid var(--argus-blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 1.5rem;
        }
        .argus-splash-text {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--argus-navy);
            letter-spacing: -0.01em;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes fadeIn { 0% { opacity: 0; } 100% { opacity: 1; } }

        /* Header Updates */
        .argus-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1.25rem;
            padding: 1rem 0 1.5rem;
            border-bottom: 1px solid var(--argus-border);
            margin-bottom: 1.5rem;
        }
        .argus-brand { display: flex; align-items: center; gap: 1.25rem; min-width: 0; }
        .argus-logo img { width: 140px; max-width: 18vw; height: auto; display: block; }
        .argus-eyebrow {
            font-size: 0.75rem; font-weight: 700; color: var(--argus-teal);
            letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.3rem;
        }
        .argus-subtitle { color: var(--argus-muted); font-size: 1rem; margin-top: 0.35rem; font-weight: 500; }
        
        /* Status Dot Pulsing */
        .argus-dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; background: var(--argus-muted); }
        .argus-dot.success { background: var(--argus-green); box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.15); animation: pulse-green 2s infinite; }
        .argus-dot.warning { background: var(--argus-amber); }
        .argus-dot.error { background: var(--argus-red); }
        @keyframes pulse-green { 0% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.4); } 70% { box-shadow: 0 0 0 6px rgba(22, 163, 74, 0); } 100% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0); } }

        /* KPI Cards with Hover Effects */
        .argus-kpi-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1rem; margin: 1rem 0 2rem; }
        .argus-kpi {
            background: var(--argus-panel);
            border: 1px solid var(--argus-border);
            border-radius: 0.75rem;
            padding: 1.25rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .argus-kpi:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.03);
        }
        .argus-kpi-label { color: var(--argus-muted); font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
        .argus-kpi-value { color: var(--argus-text); font-size: 2rem; font-weight: 800; line-height: 1.1; margin-top: 0.5rem; }
        .argus-kpi-note { color: var(--argus-muted); font-size: 0.85rem; margin-top: 0.5rem; font-weight: 500; }
        
        .argus-kpi.accent-blue { border-bottom: 4px solid var(--argus-blue); }
        .argus-kpi.accent-teal { border-bottom: 4px solid var(--argus-teal); }
        .argus-kpi.accent-amber { border-bottom: 4px solid var(--argus-amber); }
        .argus-kpi.accent-navy { border-bottom: 4px solid var(--argus-navy); }
        .argus-kpi.accent-red { border-bottom: 4px solid var(--argus-red); }

        /* Connected Pipeline Layout */
        .argus-pipeline-container {
            position: relative;
            margin: 1.5rem 0 2rem;
            padding: 0 0.5rem;
        }
        .argus-pipeline-line {
            position: absolute;
            top: 2rem;
            bottom: 2rem;
            left: 2.15rem; /* Centers the line behind the step index */
            width: 2px;
            background: var(--argus-border);
            z-index: 0;
        }
        .argus-pipeline-row {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: 3.5rem minmax(0, 1fr) auto;
            align-items: center;
            gap: 1rem;
            background: var(--argus-panel);
            border: 1px solid var(--argus-border);
            border-radius: 0.75rem;
            padding: 1rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            transition: border-color 0.2s ease;
        }
        .argus-pipeline-row:hover { border-color: var(--argus-blue); }
        .argus-step-index {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 2.5rem;
            height: 2.5rem;
            border-radius: 50%;
            background: #eff6ff;
            color: var(--argus-blue);
            font-weight: 800;
            font-size: 0.9rem;
            border: 4px solid var(--argus-bg); /* Creates a visual break in the background line */
        }
        .argus-step-title { color: var(--argus-text); font-size: 1rem; font-weight: 700; margin-bottom: 0.2rem; }
        .argus-step-copy { color: var(--argus-muted); font-size: 0.9rem; line-height: 1.4; font-weight: 500; }
        .argus-step-system {
            justify-self: end;
            border: 1px solid var(--argus-border);
            border-radius: 999px;
            color: var(--argus-navy);
            background: var(--argus-panel-soft);
            padding: 0.35rem 0.75rem;
            font-size: 0.8rem;
            font-weight: 600;
        }

        /* Miscellaneous */
        .argus-status {
            display: flex;
            gap: 0.8rem;
            align-items: flex-start;
            padding: 0.9rem 1rem;
            border: 1px solid var(--argus-border);
            border-left-width: 4px;
            border-radius: 0.7rem;
            background: var(--argus-panel);
            box-shadow: 0 6px 18px rgba(18, 36, 58, 0.05);
            margin: 0.75rem 0 1rem;
        }
        .argus-status.success { border-left-color: var(--argus-green); }
        .argus-status.warning { border-left-color: var(--argus-amber); }
        .argus-status.error { border-left-color: var(--argus-red); }
        .argus-status.info { border-left-color: var(--argus-blue); }
        .argus-status-title {
            font-weight: 750;
            color: var(--argus-text);
            margin-bottom: 0.15rem;
        }
        .argus-status-body {
            color: var(--argus-muted);
            font-size: 0.93rem;
        }
        .argus-section-title {
            color: var(--argus-text);
            font-size: 1.05rem;
            font-weight: 760;
            margin: 1.25rem 0 0.45rem;
        }
        .argus-section-caption {
            color: var(--argus-muted);
            font-size: 0.9rem;
            margin: -0.15rem 0 0.7rem;
        }
        .argus-demo-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.85rem;
            margin: 0.6rem 0 1.15rem;
        }
        .argus-proof {
            background: var(--argus-panel);
            border: 1px solid var(--argus-border);
            border-radius: 0.75rem;
            padding: 0.85rem 0.95rem;
            box-shadow: 0 7px 20px rgba(18, 36, 58, 0.05);
        }
        .argus-proof.accent-blue { border-top: 3px solid var(--argus-blue); }
        .argus-proof.accent-teal { border-top: 3px solid var(--argus-teal); }
        .argus-proof.accent-amber { border-top: 3px solid var(--argus-amber); }
        .argus-proof.accent-navy { border-top: 3px solid var(--argus-navy); }
        .argus-proof.accent-red { border-top: 3px solid var(--argus-red); }
        .argus-proof-label {
            color: var(--argus-muted);
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        .argus-proof-value {
            color: var(--argus-text);
            font-size: 1.45rem;
            font-weight: 760;
            margin-top: 0.45rem;
        }
        .argus-proof-note {
            color: var(--argus-muted);
            font-size: 0.78rem;
            margin-top: 0.35rem;
        }
        .argus-header-meta {
            display: flex;
            align-items: flex-end;
            flex-direction: column;
            gap: 0.4rem;
            white-space: nowrap;
        }
        .argus-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.38rem 0.62rem;
            border: 1px solid var(--argus-border);
            border-radius: 999px;
            background: var(--argus-panel);
            color: var(--argus-text);
            font-size: 0.82rem;
            font-weight: 650;
        }
        .argus-timestamp {
            color: var(--argus-muted);
            font-size: 0.78rem;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
            border-bottom: 1px solid var(--argus-border);
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 0.5rem 0.5rem 0 0;
            padding: 0.55rem 0.9rem;
            color: var(--argus-muted);
            font-weight: 650;
        }
        .stTabs [aria-selected="true"] {
            background: var(--argus-panel);
            color: var(--argus-text);
            border: 1px solid var(--argus-border);
            border-bottom-color: var(--argus-panel);
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--argus-border);
            border-radius: 0.75rem;
            overflow: hidden;
            box-shadow: 0 7px 20px rgba(18, 36, 58, 0.04);
        }
        div[data-testid="stExpander"] {
            border: 1px solid var(--argus-border);
            border-radius: 0.75rem;
            background: var(--argus-panel);
            box-shadow: 0 7px 20px rgba(18, 36, 58, 0.04);
        }
        div[data-testid="stAlert"] {
            border-radius: 0.7rem;
            border: 1px solid var(--argus-border);
        }
        div[data-testid="stAlert"] * { color: var(--argus-text); }
        div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] { color: var(--argus-text); }
        div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p { color: var(--argus-text); font-weight: 650; }
        div[data-testid="stSpinner"] { margin: 1rem 0; }
        
        @media (max-width: 900px) {
            .argus-header { align-items: flex-start; flex-direction: column; }
            .argus-header-meta { align-items: flex-start; }
            .argus-kpi-grid, .argus-demo-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 560px) {
            .argus-logo img { width: 104px; max-width: 38vw; }
            .argus-brand { align-items: flex-start; }
            .argus-kpi-grid, .argus-demo-strip { grid-template-columns: 1fr; }
            .argus-pipeline-row { grid-template-columns: 2.8rem minmax(0, 1fr); }
            .argus-step-system { grid-column: 2; justify-self: start; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    table["last_run"] = table["last_run"].apply(format_dt)
    table["last_seen"] = summary_df["last_run"].apply(humanize_time)
    return table[["workflow", "last_seen", "last_run", "total_runs", "total_items"]]


def recent_runs_table(recent_runs: pd.DataFrame) -> pd.DataFrame:
    if recent_runs.empty:
        return pd.DataFrame(columns=["workflow", "trigger_time", "items", "duration", "errors", "actions"])
    table = recent_runs.copy()
    table["trigger_time"] = table["trigger_time"].apply(format_dt)
    table["errors"] = table["errors"].apply(lambda raw: len(_json_array(raw)))
    table["actions"] = table["actions_taken"].apply(lambda raw: len(_json_array(raw)))
    table = table.rename(columns={"items_processed": "items", "duration_seconds": "duration"})
    return table[["workflow", "trigger_time", "items", "duration", "errors", "actions"]]


def runs_since_table(runs: list[dict]) -> pd.DataFrame:
    table = to_table(runs, date_fields=("trigger_time",))
    if table.empty:
        return pd.DataFrame(columns=["workflow", "trigger_time", "items", "decisions", "actions", "errors"])
    table = table.rename(columns={"items_processed": "items"})
    return table[["workflow", "trigger_time", "items", "decisions", "actions", "errors"]]


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


def render_section(title: str, caption: str = "") -> None:
    caption_markup = (
        f'<div class="argus-section-caption">{html.escape(caption)}</div>'
        if caption
        else ""
    )
    st.markdown(
        f'<div class="argus-section-title">{html.escape(title)}</div>{caption_markup}',
        unsafe_allow_html=True,
    )


def render_status(profile: dict) -> None:
    level = html.escape(profile["level"])
    label = html.escape(profile["label"])
    message = html.escape(profile["message"])
    st.markdown(
        (
            f'<div class="argus-status {level}">'
            f'<span class="argus-dot {level}"></span>'
            '<div>'
            f'<div class="argus-status-title">{label}</div>'
            f'<div class="argus-status-body">{message}</div>'
            '</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def render_metrics(totals: dict, error_rate: dict) -> None:
    cards = [
        ("Health", f"{totals['score']}%", "24h signal quality", "accent-teal"),
        ("Workflows", format_number(totals["workflow_count"]), "active audit streams", "accent-navy"),
        ("Total runs", format_number(totals["run_count"]), "recorded executions", "accent-blue"),
        ("Actions", format_number(totals["action_count"]), "latest artifact feed", "accent-amber"),
        ("24h errors", format_number(error_rate["errored"]), f"{error_rate['rate']:.1f}% error rate", "accent-red"),
    ]
    body = "".join(
        (
            f'<div class="argus-kpi {accent}">'
            f'<div class="argus-kpi-label">{html.escape(label)}</div>'
            f'<div class="argus-kpi-value">{html.escape(value)}</div>'
            f'<div class="argus-kpi-note">{html.escape(note)}</div>'
            '</div>'
        )
        for label, value, note, accent in cards
    )
    st.markdown(f'<div class="argus-kpi-grid">{body}</div>', unsafe_allow_html=True)


def render_header(profile: dict) -> None:
    logo = logo_data_uri(str(LOGO_PATH))
    level = html.escape(profile["level"])
    label = html.escape(profile["label"])
    generated_at = html.escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    if logo:
        logo_markup = f'<img src="{logo}" alt="Argus logo">'
    else:
        logo_markup = "<strong>A</strong>"
    st.markdown(
        (
            '<div class="argus-header">'
            '<div class="argus-brand">'
            f'<div class="argus-logo">{logo_markup}</div>'
            '<div class="argus-title-block">'
            '<div class="argus-eyebrow">Competitive intelligence operations</div>'
            '<h1>Argus Intel</h1>'
            '<div class="argus-subtitle">Scheduler evidence, LLM decisions, external actions, and operational health.</div>'
            '</div>'
            '</div>'
            '<div class="argus-header-meta">'
            f'<div class="argus-pill"><span class="argus-dot {level}"></span>{label}</div>'
            f'<div class="argus-timestamp">Updated {generated_at}</div>'
            '</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def render_architecture() -> None:
    st.graphviz_chart(
        """
        digraph {
          graph [rankdir=LR, bgcolor="transparent", pad="0.2", nodesep="0.55", ranksep="0.65"];
          node [shape=box, style="rounded,filled", color="#B9C3D3", fillcolor="#FFFFFF", fontname="Helvetica", fontsize=11, fontcolor="#172033"];
          edge [color="#526174", arrowsize=0.8];

          config [label="config.yaml"];
          scheduler [label="GitHub Actions cron", fillcolor="#EFF6FF", color="#93C5FD"];
          news [label="News Watch"];
          jobs [label="Job Watch"];
          pricing [label="Pricing Watch"];
          digest [label="Weekly Digest"];
          llm [label="Mistral classifiers", fillcolor="#ECFDF5", color="#99F6E4"];
          db [label="Postgres\\nrun_log, seen_items, snapshots", fillcolor="#F8FAFC", color="#94A3B8"];
          slack [label="Slack", fillcolor="#FFF7ED", color="#FDBA74"];
          calendar [label="Google Calendar", fillcolor="#F0FDFA", color="#5EEAD4"];
          sheets [label="Google Sheets", fillcolor="#F7FEE7", color="#BEF264"];
          email [label="Resend Email", fillcolor="#FEF2F2", color="#FCA5A5"];

          config -> news;
          config -> jobs;
          config -> pricing;
          config -> digest;
          scheduler -> news;
          scheduler -> jobs;
          scheduler -> pricing;
          scheduler -> digest;
          news -> llm;
          jobs -> llm;
          pricing -> llm;
          digest -> llm;
          llm -> db;
          news -> slack;
          news -> calendar;
          jobs -> sheets;
          pricing -> slack;
          pricing -> calendar;
          digest -> email;
          digest -> slack;
        }
        """,
        use_container_width=True,
    )


def render_pipeline_events() -> None:
    rows = "".join(
        (
            '<div class="argus-pipeline-row">'
            f'<div class="argus-step-index">{html.escape(index)}</div>'
            '<div>'
            f'<div class="argus-step-title">{html.escape(title)}</div>'
            f'<div class="argus-step-copy">{html.escape(copy)}</div>'
            '</div>'
            f'<div class="argus-step-system">{html.escape(system)}</div>'
            '</div>'
        )
        for index, title, copy, system in _PIPELINE_STEPS
    )
    # The pipeline line div provides the vertical connection behind the circles
    st.markdown(
        f'<div class="argus-pipeline-container"><div class="argus-pipeline-line"></div>{rows}</div>', 
        unsafe_allow_html=True
    )


def render_demo(
    scheduler_df: pd.DataFrame,
    run_bounds: dict,
    runs_48h: list[dict],
    artifacts: pd.DataFrame,
    snapshots: pd.DataFrame,
    seen_summary: pd.DataFrame,
) -> None:
    demo_cards = [
        ("Cron workflows", format_number(len(scheduler_df)), "GitHub Actions", "accent-blue"),
        ("Run-log span", f"{run_bounds['span_hours']:.1f}h", "database evidence", "accent-teal"),
        ("Runs in 48h", format_number(len(runs_48h)), "recent executions", "accent-navy"),
        ("Artifacts", format_number(int((artifacts["status"] == "Observed").sum())), "observed outputs", "accent-amber"),
    ]
    body = "".join(
        (
            f'<div class="argus-proof {accent}">'
            f'<div class="argus-proof-label">{html.escape(label)}</div>'
            f'<div class="argus-proof-value">{html.escape(value)}</div>'
            f'<div class="argus-proof-note">{html.escape(note)}</div>'
            '</div>'
        )
        for label, value, note, accent in demo_cards
    )
    st.markdown(f'<div class="argus-demo-strip">{body}</div>', unsafe_allow_html=True)

    if run_bounds["span_hours"] >= 48:
        st.success(
            f"48h scheduler evidence present: runs span {format_dt(run_bounds['first_run'])} to {format_dt(run_bounds['last_run'])}."
        )
    elif run_bounds["total_runs"]:
        st.warning(
            f"Run log spans {run_bounds['span_hours']:.1f}h. Keep scheduled runs enabled until this reaches 48h."
        )
    else:
        st.info("No run-log evidence yet. Let GitHub Actions cron fire at least once.")

    render_section("Pipeline Event List", "The lifecycle every workflow follows from scheduled trigger to proof artifact.")
    render_pipeline_events()

    render_section("Architecture", "Scheduled workflows, classifiers, database state, and external artifact systems.")
    render_architecture()

    render_section("Scheduler Proof", "Cron definitions read from the repository workflow files.")
    st.dataframe(scheduler_df, use_container_width=True, hide_index=True)

    runs_table = runs_since_table(runs_48h)
    render_section("Last 48 Hours", "Recorded workflow executions from Postgres.")
    if runs_table.empty:
        st.info("No runs in the last 48 hours.")
    else:
        st.dataframe(runs_table, use_container_width=True, hide_index=True)

    render_section("Real Artifacts", "Latest external outputs and database evidence.")
    st.dataframe(artifacts, use_container_width=True, hide_index=True)

    with st.expander("Database audit trail"):
        render_section("Pricing Snapshots")
        snapshot_table = page_snapshots_table(snapshots)
        if snapshot_table.empty:
            st.info("No pricing snapshots stored yet.")
        else:
            st.dataframe(snapshot_table, use_container_width=True, hide_index=True)

        render_section("Seen Item Summary")
        seen_table = seen_summary_table(seen_summary)
        if seen_table.empty:
            st.info("No seen items stored yet.")
        else:
            st.dataframe(seen_table, use_container_width=True, hide_index=True)

    with st.expander("Loom narration"):
        st.code(
            """Argus is an autonomous competitive-intelligence agent.
GitHub Actions cron wakes up each workflow on schedule.
Each workflow fetches external signals, deduplicates or snapshots state, asks Mistral for a structured classification, then writes actions to Slack, Calendar, Sheets, or email.
The run_log, seen_items, and page_snapshots tables give us the audit trail showing what happened over time.""",
            language="text",
        )


def render_run_history(runs: list[dict]) -> None:
    if not runs:
        st.info("No runs recorded yet.")
        return

    for run in runs:
        title = (
            f"{run['workflow']} - {format_dt(run['trigger_time'])} - "
            f"{run['items_processed']} item(s), "
            f"{len(run['decisions'])} decision(s), "
            f"{len(run['actions'])} action(s), "
            f"{len(run['errors'])} error(s)"
        )
        with st.expander(title):
            render_section("Decisions")
            st.dataframe(to_table(run["decisions"]), use_container_width=True, hide_index=True)

            render_section("Actions")
            st.dataframe(to_table(run["actions"]), use_container_width=True, hide_index=True)

            if run["errors"]:
                render_section("Errors")
                for err in run["errors"]:
                    st.error(err.get("error", "Unknown error"))
                    if err.get("traceback"):
                        st.code(err["traceback"], language="python")


def render_errors(error_logs: list[dict]) -> None:
    has_errors = False
    for log in error_logs:
        errors = _json_array(log["errors"])
        if not errors:
            continue
        has_errors = True
        title = f"{log['workflow']} - {format_dt(log['trigger_time'])} - {len(errors)} error(s)"
        with st.expander(title):
            for err in errors:
                st.error(err.get("error", "Unknown error"))
                if err.get("traceback"):
                    st.code(err["traceback"], language="python")

    if not has_errors:
        st.success("No errors in the last 24 hours.")


# --- Main Execution Block ---

render_styles()

# 1. Create a placeholder and show the splash screen
splash_placeholder = st.empty()
with splash_placeholder.container():
    st.markdown(
        """
        <div class="argus-splash-container">
            <div class="argus-splash-spinner"></div>
            <div class="argus-splash-text">Compiling intelligence data...</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# 2. Fetch all data while the splash is visible
error_rate = load_error_rate()
summary_df = load_run_summary()
actions = load_recent_actions(20)
actions_30d = load_actions_since(30)
decisions = load_recent_decisions(40)
run_history = load_run_history(20)
error_logs = load_error_logs()
recent_runs = load_recent_runs()
runs_48h = load_runs_since(48)
run_bounds = load_run_bounds()
seen_summary = load_seen_summary()
snapshots = load_page_snapshots()
scheduler_df = load_scheduler_manifest()
artifacts = artifact_rows(actions_30d, snapshots, seen_summary)

profile = status_profile(error_rate)
totals = dashboard_totals(summary_df, actions, recent_runs, error_rate)

# 3. Clear the splash screen
splash_placeholder.empty()

# 4. Render the dashboard
render_header(profile)
render_status(profile)
render_metrics(totals, error_rate)

demo_tab, overview_tab, decisions_tab, actions_tab, runs_tab, errors_tab = st.tabs(
    ["Demo", "Overview", "Decisions", "Actions", "Runs", "Errors"]
)

with demo_tab:
    render_demo(scheduler_df, run_bounds, runs_48h, artifacts, snapshots, seen_summary)

with overview_tab:
    render_section("Workflow Summary", "Last observed run and cumulative volume by workflow.")
    if summary_df.empty:
        st.info("No workflow runs recorded yet.")
    else:
        st.dataframe(summary_table(summary_df), use_container_width=True, hide_index=True)

    render_section("Recent Runs", "Latest execution windows with item, action, and error counts.")
    recent_table = recent_runs_table(recent_runs)
    if recent_table.empty:
        st.info("No recent runs recorded yet.")
    else:
        st.dataframe(recent_table, use_container_width=True, hide_index=True)

with decisions_tab:
    render_section("LLM Decisions", "Structured labels and reasoning written to the audit log.")
    decisions_df = to_table(decisions)
    if decisions_df.empty:
        st.info("No LLM decisions recorded yet.")
    else:
        st.dataframe(decisions_df, use_container_width=True, hide_index=True)

with actions_tab:
    render_section("External Actions", "Slack, Calendar, Sheets, and email writes recorded by workflow runs.")
    actions_df = to_table(actions)
    if actions_df.empty:
        st.info("No actions recorded yet.")
    else:
        st.dataframe(actions_df, use_container_width=True, hide_index=True)

with runs_tab:
    render_section("Run History", "Expandable audit records with decisions, actions, and tracebacks.")
    render_run_history(run_history)

with errors_tab:
    render_section("Errors", "Workflow failures captured in the last 24 hours.")
    render_errors(error_logs)
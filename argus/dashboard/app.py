"""Streamlit dashboard for Argus workflow health and activity."""
import json
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
from argus.core.models import RunLog

st.set_page_config(page_title="Argus Intel", layout="wide", page_icon="A")

_SUMMARY_COLUMNS = ["workflow", "last_run", "total_runs", "total_items"]
_RUN_COLUMNS = [
    "workflow",
    "trigger_time",
    "items_processed",
    "duration_seconds",
    "errors",
    "actions_taken",
]


@st.cache_data(ttl=30)
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


@st.cache_data(ttl=30)
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


@st.cache_data(ttl=30)
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


@st.cache_data(ttl=30)
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


@st.cache_data(ttl=30)
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


@st.cache_data(ttl=30)
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


@st.cache_data(ttl=30)
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
    if dt is None:
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
    if dt is None:
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


def render_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1120px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        div[data-testid="stMetric"] {
            padding: 0.75rem 1rem;
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 0.6rem;
            background: rgba(148, 163, 184, 0.08);
        }
        div[data-testid="stSpinner"] {
            margin: 1rem 0;
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


def render_status(profile: dict) -> None:
    message = f"{profile['label']}: {profile['message']}"
    if profile["level"] == "success":
        st.success(message)
    elif profile["level"] == "warning":
        st.warning(message)
    elif profile["level"] == "error":
        st.error(message)
    else:
        st.info(message)


def render_metrics(totals: dict, error_rate: dict) -> None:
    cols = st.columns(5)
    cols[0].metric("Health", f"{totals['score']}%")
    cols[1].metric("Workflows", totals["workflow_count"])
    cols[2].metric("Total runs", totals["run_count"])
    cols[3].metric("Actions", totals["action_count"])
    cols[4].metric("24h errors", error_rate["errored"])


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
            st.write("Decisions")
            st.dataframe(to_table(run["decisions"]), use_container_width=True, hide_index=True)

            st.write("Actions")
            st.dataframe(to_table(run["actions"]), use_container_width=True, hide_index=True)

            if run["errors"]:
                st.write("Errors")
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


render_styles()

error_rate = load_error_rate()
summary_df = load_run_summary()
actions = load_recent_actions(20)
decisions = load_recent_decisions(40)
run_history = load_run_history(20)
error_logs = load_error_logs()
recent_runs = load_recent_runs()

profile = status_profile(error_rate)
totals = dashboard_totals(summary_df, actions, recent_runs, error_rate)

st.title("Argus Intel")
st.caption("Workflow health, recent decisions, external actions, and error history.")
render_status(profile)
render_metrics(totals, error_rate)

overview_tab, decisions_tab, actions_tab, runs_tab, errors_tab = st.tabs(
    ["Overview", "Decisions", "Actions", "Runs", "Errors"]
)

with overview_tab:
    st.subheader("Workflow summary")
    if summary_df.empty:
        st.info("No workflow runs recorded yet.")
    else:
        st.dataframe(summary_table(summary_df), use_container_width=True, hide_index=True)

    st.subheader("Recent runs")
    recent_table = recent_runs_table(recent_runs)
    if recent_table.empty:
        st.info("No recent runs recorded yet.")
    else:
        st.dataframe(recent_table, use_container_width=True, hide_index=True)

with decisions_tab:
    st.subheader("LLM decisions")
    decisions_df = to_table(decisions)
    if decisions_df.empty:
        st.info("No LLM decisions recorded yet.")
    else:
        st.dataframe(decisions_df, use_container_width=True, hide_index=True)

with actions_tab:
    st.subheader("External actions")
    actions_df = to_table(actions)
    if actions_df.empty:
        st.info("No actions recorded yet.")
    else:
        st.dataframe(actions_df, use_container_width=True, hide_index=True)

with runs_tab:
    st.subheader("Run history")
    render_run_history(run_history)

with errors_tab:
    st.subheader("Errors")
    render_errors(error_logs)

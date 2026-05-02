"""Streamlit dashboard for Argus workflow health and activity."""
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


@st.cache_data(ttl=30)
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


@st.cache_data(ttl=30)
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


def render_architecture() -> None:
    st.graphviz_chart(
        """
        digraph {
          graph [rankdir=LR, bgcolor="transparent", pad="0.2", nodesep="0.55", ranksep="0.65"];
          node [shape=box, style="rounded,filled", color="#CBD5E1", fillcolor="#F8FAFC", fontname="Helvetica", fontsize=11];
          edge [color="#64748B", arrowsize=0.8];

          config [label="config.yaml"];
          scheduler [label="GitHub Actions cron"];
          news [label="News Watch"];
          jobs [label="Job Watch"];
          pricing [label="Pricing Watch"];
          digest [label="Weekly Digest"];
          llm [label="Mistral classifiers"];
          db [label="Postgres\\nrun_log, seen_items, snapshots"];
          slack [label="Slack"];
          calendar [label="Google Calendar"];
          sheets [label="Google Sheets"];
          email [label="Resend Email"];

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


def render_demo(
    scheduler_df: pd.DataFrame,
    run_bounds: dict,
    runs_48h: list[dict],
    artifacts: pd.DataFrame,
    snapshots: pd.DataFrame,
    seen_summary: pd.DataFrame,
) -> None:
    st.subheader("Demo cockpit")
    st.caption("Use this tab as the spine for the 3-5 minute architecture walkthrough.")

    cols = st.columns(4)
    cols[0].metric("Cron workflows", len(scheduler_df))
    cols[1].metric("Run-log span", f"{run_bounds['span_hours']:.1f}h")
    cols[2].metric("Runs in 48h", len(runs_48h))
    cols[3].metric("Artifacts observed", int((artifacts["status"] == "Observed").sum()))

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

    st.subheader("Architecture")
    render_architecture()

    st.subheader("Scheduler proof")
    st.dataframe(scheduler_df, use_container_width=True, hide_index=True)

    runs_table = runs_since_table(runs_48h)
    st.subheader("Last 48 hours")
    if runs_table.empty:
        st.info("No runs in the last 48 hours.")
    else:
        st.dataframe(runs_table, use_container_width=True, hide_index=True)

    st.subheader("Real artifacts")
    st.dataframe(artifacts, use_container_width=True, hide_index=True)

    with st.expander("Database audit trail"):
        st.write("Pricing snapshots")
        snapshot_table = page_snapshots_table(snapshots)
        if snapshot_table.empty:
            st.info("No pricing snapshots stored yet.")
        else:
            st.dataframe(snapshot_table, use_container_width=True, hide_index=True)

        st.write("Seen item summary")
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

st.title("Argus Intel")
st.caption("Demo cockpit, workflow health, recent decisions, external actions, and error history.")
render_status(profile)
render_metrics(totals, error_rate)

demo_tab, overview_tab, decisions_tab, actions_tab, runs_tab, errors_tab = st.tabs(
    ["Demo", "Overview", "Decisions", "Actions", "Runs", "Errors"]
)

with demo_tab:
    render_demo(scheduler_df, run_bounds, runs_48h, artifacts, snapshots, seen_summary)

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

"""Streamlit dashboard — last run per workflow, last 20 actions, error rate."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import func

from argus.core.database import SessionLocal
from argus.core.models import RunLog

st.set_page_config(page_title="Argus Intel", layout="wide", page_icon="🔍")
st.title("🔍 Argus Intel Agent")


# ── Data loaders (cached 30s) ────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_error_rate(hours: int = 24) -> dict:
    """Return total runs, errored runs, and error rate % for the last N hours."""
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).all()
        total = len(logs)
        errored = sum(1 for r in logs if json.loads(r.errors))
        return {"total": total, "errored": errored, "rate": (errored / total * 100) if total else 0}
    finally:
        session.close()


@st.cache_data(ttl=30)
def load_run_summary() -> pd.DataFrame:
    """Return a DataFrame with last run time, total runs, and total items per workflow."""
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
        return pd.DataFrame(rows, columns=["workflow", "last_run", "total_runs", "total_items"])
    finally:
        session.close()


@st.cache_data(ttl=30)
def load_recent_actions(n: int = 20) -> list[dict]:
    """Return the N most recent actions across all workflows."""
    session = SessionLocal()
    try:
        logs = session.query(RunLog).order_by(RunLog.trigger_time.desc()).limit(60).all()
        rows = []
        for log in logs:
            for action in json.loads(log.actions_taken):
                rows.append({
                    "time":     log.trigger_time,
                    "workflow": log.workflow,
                    "action":   action.get("action", ""),
                    "target":   action.get("target", ""),
                    "status":   action.get("status", ""),
                    "detail":   action.get("detail", ""),
                })
        return rows[:n]
    finally:
        session.close()


@st.cache_data(ttl=30)
def load_error_logs(hours: int = 24) -> list[RunLog]:
    """Return RunLog rows from the last N hours that contain at least one error."""
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return (
            session.query(RunLog)
            .filter(RunLog.trigger_time >= cutoff)
            .order_by(RunLog.trigger_time.desc())
            .all()
        )
    finally:
        session.close()


def humanize_time(dt: datetime | None) -> str:
    """Convert a UTC datetime to a human-readable relative string (e.g. '5m ago')."""
    if dt is None:
        return "never"
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


# ── Section 1: Status ────────────────────────────────────────────────────────

err = load_error_rate()
if err["rate"] == 0 and err["total"] > 0:
    st.success(f"✅ All systems healthy — {err['total']} run(s) in last 24h, 0 errors")
elif err["total"] == 0:
    st.warning("⏳ No runs recorded in the last 24h yet")
else:
    st.error(f"❌ {err['errored']} error(s) in last 24h — {err['rate']:.1f}% error rate")

# ── Section 2: Last Run Per Workflow ────────────────────────────────────────

st.subheader("Last Run Per Workflow")
summary_df = load_run_summary()
if summary_df.empty:
    st.info("No runs recorded yet.")
else:
    cols = st.columns(len(summary_df))
    for col, (_, row) in zip(cols, summary_df.iterrows()):
        elapsed = humanize_time(row["last_run"])
        col.metric(
            label=row["workflow"].replace("_", " ").title(),
            value=elapsed,
            delta=f"{int(row['total_runs'])} total runs",
        )

# ── Section 3: Recent Actions Feed ──────────────────────────────────────────

st.subheader("Last 20 Actions")
actions = load_recent_actions(20)
if not actions:
    st.info("No actions recorded yet.")
else:
    for a in actions:
        time_str = a["time"].strftime("%I:%M %p") if a["time"] else "?"
        detail = f" — {a['detail']}" if a["detail"] else ""
        st.write(f"🕙 {time_str}: **{a['action']}** → `{a['target']}` ({a['status']}){detail}")

# ── Section 4: Error Log ─────────────────────────────────────────────────────

st.subheader("Errors (last 24h)")
error_logs = load_error_logs()
has_errors = False
for log in error_logs:
    errs = json.loads(log.errors)
    if errs:
        has_errors = True
        with st.expander(
            f"{log.workflow.replace('_',' ').title()} @ {log.trigger_time.strftime('%Y-%m-%d %H:%M')} — {len(errs)} error(s)"
        ):
            for e in errs:
                st.error(e["error"])
                if e.get("traceback"):
                    st.code(e["traceback"], language="python")
if not has_errors:
    st.success("No errors in last 24h.")

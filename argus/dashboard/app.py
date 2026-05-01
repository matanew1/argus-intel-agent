"""Streamlit dashboard — dark glassmorphism competitive-intel command centre."""
import json
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from textwrap import dedent

import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from argus.core.database import SessionLocal
from argus.core.models import RunLog

st.set_page_config(page_title="Argus Intel", layout="wide", page_icon="👁")

_SUMMARY_COLUMNS = ["workflow", "last_run", "total_runs", "total_items"]
_RUN_COLUMNS     = ["workflow", "trigger_time", "items_processed", "duration_seconds", "errors", "actions_taken"]

_WF_COLOR = {
    "news_watch":    "#22d3ee",
    "job_watch":     "#a78bfa",
    "pricing_watch": "#fbbf24",
    "weekly_digest": "#34d399",
}
_LABEL_COLOR = {
    "funding":             "#34d399",
    "product_launch":      "#a78bfa",
    "executive_change":    "#fbbf24",
    "controversy":         "#fb7185",
    "noise":               "#94a3b8",
    "material":            "#fb7185",
    "cosmetic":            "#94a3b8",
    "building_ai_team":    "#a78bfa",
    "infra_scaling":       "#22d3ee",
    "entering_new_market": "#34d399",
    "routine_backfill":    "#94a3b8",
}


# ── Data loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_error_rate(hours: int = 24) -> dict:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs   = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).all()
        total  = len(logs)
        errored = sum(1 for r in logs if _json_array(r.errors))
        return {"total": total, "errored": errored,
                "rate": (errored / total * 100) if total else 0, "state": "ready"}
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
                rows.append({
                    "time":     log.trigger_time,
                    "workflow": log.workflow,
                    "action":   action.get("action", ""),
                    "target":   action.get("target", ""),
                    "status":   action.get("status", ""),
                    "detail":   action.get("detail", ""),
                })
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
        return [{"workflow": r.workflow, "trigger_time": r.trigger_time, "errors": r.errors}
                for r in rows]
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
                rows.append({
                    "time":      log.trigger_time,
                    "workflow":  log.workflow,
                    "item_id":   decision.get("item_id", ""),
                    "label":     decision.get("label", ""),
                    "reasoning": decision.get("reasoning", ""),
                })
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
                "workflow":         r.workflow,
                "trigger_time":     r.trigger_time,
                "items_processed":  r.items_processed,
                "duration_seconds": r.duration_seconds,
                "decisions":        _json_array(r.decisions),
                "actions":          _json_array(r.actions_taken),
                "errors":           _json_array(r.errors),
            }
            for r in logs
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def humanize_time(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    secs  = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


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
    pgcode   = getattr(original, "pgcode", "")
    message  = str(original).lower()
    return (
        pgcode == "42P01"
        or "undefinedtable" in message
        or 'relation "run_log" does not exist' in message
        or "no such table" in message
    )


def status_profile(err: dict) -> dict:
    if err.get("state") == "missing_tables":
        return {"tone": "idle",  "label": "No logbook yet",
                "headline": "Argus is ready, awaiting first run",
                "detail": "Run any workflow once to populate the database"}
    if err.get("state") == "db_error":
        return {"tone": "alert", "label": "Database offline",
                "headline": "Cannot read the workflow log",
                "detail": "Check DATABASE_URL and connectivity, then refresh"}
    if err["rate"] == 0 and err["total"] > 0:
        return {"tone": "ok",   "label": "Operational",
                "headline": "All systems nominal",
                "detail": f"{err['total']} run(s) in 24h — zero errors"}
    if err["total"] == 0:
        return {"tone": "idle",  "label": "Standby",
                "headline": "Waiting for first signal",
                "detail": "No workflow runs in the last 24h"}
    return {"tone": "alert",    "label": "Needs review",
            "headline": f"{err['errored']} errored run(s) detected",
            "detail": f"{err['rate']:.1f}% error rate in 24h"}


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
    workflow_count = 0 if summary_df.empty else len(summary_df)
    item_count     = 0 if summary_df.empty else int(summary_df["total_items"].fillna(0).sum())
    run_count      = 0 if summary_df.empty else int(summary_df["total_runs"].fillna(0).sum())
    durations      = recent_runs["duration_seconds"].dropna() if not recent_runs.empty else []
    avg_duration   = int(durations.mean()) if len(durations) else 0
    return {
        "score":          health_score(err),
        "workflow_count": workflow_count,
        "item_count":     item_count,
        "run_count":      run_count,
        "action_count":   len(actions),
        "avg_duration":   avg_duration,
    }


def render_html(markup: str) -> None:
    """Render raw HTML without Markdown turning indented blocks into code."""
    html = "\n".join(
        line for line in dedent(markup).strip().splitlines()
        if line.strip()
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Styles ────────────────────────────────────────────────────────────────────

def render_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap');

        /* ── Tokens ── */
        :root {
            --bg:           #0b1426;
            --surface:      rgba(20, 43, 76, 0.86);
            --glass:        rgba(255,255,255,0.065);
            --glass-hi:     rgba(255,255,255,0.12);
            --border:       rgba(255,255,255,0.15);
            --text:         #f8fafc;
            --muted:        #94a3b8;
            --cyan:         #22d3ee;
            --purple:       #a78bfa;
            --amber:        #fbbf24;
            --green:        #34d399;
            --red:          #fb7185;
        }

        /* ── Reset & base ── */
        html, body, .stApp {
            background:
                radial-gradient(circle at 18% 12%, rgba(34,211,238,0.16), transparent 30%),
                radial-gradient(circle at 82% 8%, rgba(167,139,250,0.14), transparent 28%),
                linear-gradient(180deg, #101f3a 0%, var(--bg) 48%, #08111f 100%) !important;
            color: var(--text);
            font-family: 'Inter', sans-serif;
        }

        .block-container {
            max-width: 1240px;
            padding-top: 2.5rem !important;
            padding-bottom: 4rem !important;
        }

        /* Hide default Streamlit chrome clutter */
        header[data-testid="stHeader"] { background: transparent !important; }
        .stDeployButton, footer { display: none !important; }

        /* ── Loading spinner ── */
        div[data-testid="stSpinner"] {
            width: fit-content;
            min-width: 240px;
            margin: 18px auto;
            padding: 18px 22px;
            border: 1px solid rgba(34,211,238,0.28);
            border-radius: 16px;
            background:
                radial-gradient(circle at 22% 30%, rgba(34,211,238,0.16), transparent 34%),
                rgba(15,32,58,0.74);
            box-shadow: 0 18px 50px rgba(0,0,0,0.28), 0 0 34px rgba(34,211,238,0.12);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
        }

        div[data-testid="stSpinner"] > div:first-child {
            position: relative !important;
            width: 52px !important;
            height: 52px !important;
            margin-right: 14px !important;
            border-radius: 50% !important;
            background:
                conic-gradient(from 0deg, transparent 0 24%, var(--cyan) 34%, var(--purple) 54%, transparent 76%),
                radial-gradient(circle, rgba(34,211,238,0.16), transparent 62%) !important;
            box-shadow: 0 0 24px rgba(34,211,238,0.3);
            animation: ag-loader-spin 1.05s linear infinite, ag-loader-pulse 1.9s ease-in-out infinite;
        }

        div[data-testid="stSpinner"] > div:first-child::before {
            content: "";
            position: absolute;
            inset: 7px;
            border-radius: inherit;
            background: #0b1426;
            box-shadow: inset 0 0 18px rgba(34,211,238,0.16);
        }

        div[data-testid="stSpinner"] > div:first-child::after {
            content: "";
            position: absolute;
            top: 4px;
            left: 50%;
            width: 8px;
            height: 8px;
            transform: translateX(-50%);
            border-radius: 50%;
            background: #cffafe;
            box-shadow: 0 0 16px var(--cyan), 0 0 28px rgba(34,211,238,0.42);
        }

        div[data-testid="stSpinner"] svg {
            display: none !important;
        }

        div[data-testid="stSpinner"] p {
            color: var(--text) !important;
            font-weight: 800 !important;
            letter-spacing: 0 !important;
        }

        /* ── Hero ── */
        .ag-hero {
            position: relative;
            display: grid;
            grid-template-columns: 1fr 320px;
            gap: 24px;
            align-items: stretch;
            min-height: 270px;
            padding: 32px;
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
            background:
                linear-gradient(135deg, rgba(25,55,94,0.92), rgba(12,26,48,0.88)),
                var(--surface);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            box-shadow: 0 0 0 1px rgba(34,211,238,0.2), 0 28px 72px rgba(0,0,0,0.42);
        }

        /* Gradient orbs */
        .ag-orb {
            position: absolute;
            border-radius: 50%;
            filter: blur(80px);
            pointer-events: none;
            z-index: 0;
        }
        .ag-orb-1 {
            width: 340px; height: 340px;
            top: -100px; left: -60px;
            background: radial-gradient(circle, rgba(6,182,212,0.22) 0%, transparent 70%);
            animation: orb-drift-1 9s ease-in-out infinite;
        }
        .ag-orb-2 {
            width: 280px; height: 280px;
            bottom: -80px; right: 120px;
            background: radial-gradient(circle, rgba(139,92,246,0.18) 0%, transparent 70%);
            animation: orb-drift-2 11s ease-in-out infinite;
        }
        .ag-orb-3 {
            width: 180px; height: 180px;
            top: 30px; right: 360px;
            background: radial-gradient(circle, rgba(16,185,129,0.12) 0%, transparent 70%);
            animation: orb-drift-1 7s ease-in-out infinite reverse;
        }

        /* Grid overlay */
        .ag-grid-overlay {
            position: absolute;
            inset: 0;
            z-index: 0;
            background-image:
                linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
            background-size: 32px 32px;
        }

        /* Scan line */
        .ag-scanline {
            position: absolute;
            inset-block: 0;
            width: 2px;
            background: linear-gradient(180deg, transparent, var(--cyan), transparent);
            opacity: 0.4;
            animation: scanline 6s ease-in-out infinite;
            z-index: 1;
        }

        .hero-copy {
            position: relative;
            z-index: 2;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        .hero-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 16px;
            padding: 6px 14px;
            border: 1px solid rgba(6,182,212,0.3);
            border-radius: 999px;
            background: rgba(6,182,212,0.08);
            color: var(--cyan);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            width: fit-content;
        }

        .hero-eyebrow-dot {
            width: 7px; height: 7px;
            border-radius: 50%;
            background: var(--cyan);
            box-shadow: 0 0 8px var(--cyan);
            animation: pulse-dot 2s ease-in-out infinite;
        }

        .hero-title {
            margin: 0;
            font-size: clamp(2.4rem, 4.5vw, 4.6rem);
            font-weight: 900;
            line-height: 0.93;
            letter-spacing: -0.03em;
            background: linear-gradient(135deg, #f8fafc 0%, var(--cyan) 50%, var(--purple) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .hero-sub {
            margin: 16px 0 0;
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.65;
            max-width: 520px;
        }

        .hero-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 22px;
        }

        .hero-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 14px;
            border: 1px solid var(--border);
            border-radius: 999px;
            background: var(--glass);
            color: var(--text);
            font-size: 0.82rem;
            font-weight: 700;
            backdrop-filter: blur(8px);
        }

        .hero-pill .dot {
            width: 8px; height: 8px;
            border-radius: 50%;
        }

        .tone-ok    .dot { background: var(--green); box-shadow: 0 0 8px var(--green); animation: pulse-dot 2s ease-in-out infinite; }
        .tone-idle  .dot { background: var(--amber); box-shadow: 0 0 8px var(--amber); animation: pulse-dot 2s ease-in-out infinite; }
        .tone-alert .dot { background: var(--red);   box-shadow: 0 0 8px var(--red);   animation: pulse-dot 1.2s ease-in-out infinite; }

        .hero-kpis {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 20px;
        }

        .hero-kpi {
            padding: 12px 14px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--glass);
            backdrop-filter: blur(8px);
        }

        .hero-kpi-label {
            color: var(--muted);
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .hero-kpi-value {
            margin-top: 6px;
            color: var(--text);
            font-size: 1.55rem;
            font-weight: 900;
            line-height: 1;
            font-family: 'JetBrains Mono', monospace;
        }

        /* Bot display panel */
        .bot-panel {
            position: relative;
            z-index: 2;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: rgba(255,255,255,0.055);
            overflow: hidden;
            min-height: 260px;
            padding-bottom: 46px;
            perspective: 900px;
        }

        .bot-panel-grid {
            position: absolute;
            inset: 0;
            background-image:
                linear-gradient(rgba(6,182,212,0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(6,182,212,0.05) 1px, transparent 1px);
            background-size: 20px 20px;
        }

        /* Radar rings */
        .bot-radar {
            position: absolute;
            border-radius: 50%;
            border: 1px solid rgba(6,182,212,0.18);
            left: 50%; top: 50%;
            transform: translate(-50%, -50%);
        }
        .bot-radar-1 { width: 200px; height: 200px; animation: radar-breathe 4s ease-in-out infinite; }
        .bot-radar-2 { width: 138px; height: 138px; animation: radar-breathe 4s ease-in-out infinite reverse; }

        .bot-sweep {
            position: absolute;
            left: 50%; top: 50%;
            width: 100px; height: 100px;
            margin-left: -50px; margin-top: -50px;
            border-radius: 50%;
            background: conic-gradient(from 0deg, rgba(6,182,212,0.35), rgba(6,182,212,0.05) 60deg, transparent 90deg);
            animation: radar-sweep 5s linear infinite;
        }

        .bot-orbit-chips {
            position: absolute;
            inset: 0;
        }

        .orbit-chip {
            position: absolute;
            padding: 5px 9px;
            border: 1px solid var(--border);
            border-radius: 999px;
            background: var(--glass);
            backdrop-filter: blur(8px);
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            animation: float 3.5s ease-in-out infinite;
            text-transform: uppercase;
        }
        .orbit-chip.news    { top: 14px;  left: 14px;  color: var(--cyan);   animation-delay: 0s;    border-color: rgba(6,182,212,0.3); }
        .orbit-chip.jobs    { top: 18px;  right: 14px; color: var(--purple); animation-delay: -0.9s; border-color: rgba(139,92,246,0.3); }
        .orbit-chip.pricing { bottom: 54px; left: 18px;  color: var(--amber);  animation-delay: -1.8s; border-color: rgba(245,158,11,0.3); }
        .orbit-chip.digest  { bottom: 50px; right: 16px; color: var(--green);  animation-delay: -2.7s; border-color: rgba(16,185,129,0.3); }

        /* Robot display */
        .ag-bot {
            position: relative;
            z-index: 3;
            width: 130px;
            height: 168px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            filter: drop-shadow(0 18px 32px rgba(6,182,212,0.18));
            transform-style: preserve-3d;
            animation: bot-bob 3.8s ease-in-out infinite;
        }

        .bot-head-wrap {
            position: relative;
            z-index: 4;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .bot-antenna-stem {
            width: 5px; height: 22px;
            background: linear-gradient(180deg, rgba(255,255,255,0.72), rgba(148,163,184,0.26));
            border-radius: 999px;
            transform-origin: bottom center;
            animation: antenna-wiggle 3.8s ease-in-out infinite;
        }

        .bot-antenna-ball {
            width: 16px; height: 16px;
            border-radius: 50%;
            background: var(--cyan);
            box-shadow: 0 0 18px var(--cyan), 0 0 42px rgba(6,182,212,0.52);
            animation: antenna-pulse 1.8s ease-in-out infinite;
            margin-top: -3px;
        }

        .bot-head {
            position: relative;
            width: 112px; height: 82px;
            border: 2px solid rgba(6,182,212,0.52);
            border-radius: 24px 24px 19px 19px;
            background:
                radial-gradient(circle at 34% 28%, rgba(56,189,248,0.22), transparent 24%),
                linear-gradient(145deg, rgba(20,39,63,0.98), rgba(7,15,29,0.98) 62%, rgba(14,24,44,0.98));
            overflow: visible;
            margin-top: 4px;
            box-shadow:
                0 0 28px rgba(6,182,212,0.22),
                inset 0 1px 0 rgba(255,255,255,0.2),
                inset 0 -18px 32px rgba(0,0,0,0.24);
            animation: head-look 5.2s ease-in-out infinite;
        }

        .bot-head::before {
            content: "";
            position: absolute;
            inset: 8px 10px auto;
            height: 20px;
            border-radius: 18px;
            background: linear-gradient(105deg, rgba(255,255,255,0.18), rgba(255,255,255,0.02));
            opacity: 0.8;
            animation: screen-shimmer 4.6s ease-in-out infinite;
        }

        .bot-head::after {
            content: "";
            position: absolute;
            inset: auto 14px 8px;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(6,182,212,0.42), transparent);
        }

        .bot-ear {
            position: absolute;
            top: 29px;
            width: 13px; height: 32px;
            border: 1px solid rgba(6,182,212,0.28);
            background: linear-gradient(180deg, rgba(15,30,52,0.95), rgba(7,15,29,0.95));
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.1);
        }

        .bot-ear.left {
            left: -13px;
            border-radius: 10px 0 0 10px;
        }

        .bot-ear.right {
            right: -13px;
            border-radius: 0 10px 10px 0;
        }

        .bot-eye {
            position: absolute;
            top: 32px;
            width: 20px; height: 20px;
            border-radius: 50%;
            background:
                radial-gradient(circle at 35% 30%, #cffafe 0 8%, transparent 9%),
                radial-gradient(circle, #22d3ee 0 48%, #0891b2 56%, rgba(6,182,212,0.18) 72%);
            box-shadow: 0 0 16px var(--cyan), 0 0 30px rgba(6,182,212,0.58);
            animation: eye-blink 4s ease-in-out infinite;
        }

        .bot-eye.left { left: 29px; }
        .bot-eye.right { right: 29px; animation-delay: 0.1s; }

        .bot-cheek {
            position: absolute;
            bottom: 20px;
            width: 12px; height: 6px;
            border-radius: 999px;
            background: rgba(34,211,238,0.18);
            filter: blur(1px);
        }

        .bot-cheek.left { left: 21px; }
        .bot-cheek.right { right: 21px; }

        .bot-smile {
            position: absolute;
            left: 50%;
            bottom: 16px;
            width: 38px; height: 16px;
            transform: translateX(-50%);
            border-bottom: 4px solid rgba(103,232,249,0.92);
            border-radius: 0 0 999px 999px;
            box-shadow: 0 8px 14px rgba(6,182,212,0.2);
            animation: smile-glow 2.8s ease-in-out infinite;
        }

        .bot-neck {
            width: 28px; height: 12px;
            margin-top: -1px;
            border: 1px solid rgba(148,163,184,0.2);
            border-radius: 0 0 8px 8px;
            background: linear-gradient(180deg, rgba(71,85,105,0.62), rgba(15,23,42,0.96));
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
        }

        .bot-body {
            position: relative;
            z-index: 2;
            width: 92px; height: 70px;
            border: 2px solid rgba(139,92,246,0.38);
            border-radius: 18px 18px 16px 16px;
            background:
                linear-gradient(145deg, rgba(20,31,54,0.98), rgba(8,14,28,0.98)),
                radial-gradient(circle at 50% 0%, rgba(139,92,246,0.18), transparent 48%);
            margin-top: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow:
                0 0 24px rgba(139,92,246,0.18),
                inset 0 1px 0 rgba(255,255,255,0.14),
                inset 0 -14px 28px rgba(0,0,0,0.22);
            animation: body-breathe 3.4s ease-in-out infinite;
        }

        .bot-body::after {
            content: "";
            position: absolute;
            left: 22px;
            right: 22px;
            bottom: 14px;
            height: 2px;
            border-radius: 999px;
            background: linear-gradient(90deg, transparent, rgba(148,163,184,0.42), transparent);
            box-shadow: 0 8px 0 rgba(148,163,184,0.12);
        }

        .bot-arm {
            position: absolute;
            top: 105px;
            z-index: 1;
            width: 15px; height: 52px;
            border: 1px solid rgba(6,182,212,0.2);
            border-radius: 999px;
            background: linear-gradient(180deg, rgba(20,39,63,0.96), rgba(8,14,28,0.96));
            transform-origin: top center;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.1);
        }

        .bot-arm.left {
            left: 10px;
            animation: arm-swing-left 3.8s ease-in-out infinite;
        }

        .bot-arm.right {
            right: 10px;
            animation: arm-swing-right 3.8s ease-in-out infinite;
        }

        .bot-arm span {
            position: absolute;
            left: 50%;
            bottom: -8px;
            width: 20px; height: 13px;
            transform: translateX(-50%);
            border-radius: 999px;
            background: radial-gradient(circle at 35% 30%, rgba(255,255,255,0.22), transparent 24%), rgba(6,182,212,0.24);
            border: 1px solid rgba(6,182,212,0.35);
        }

        .bot-chest-led {
            position: relative;
            width: 46px; height: 11px;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--cyan), var(--purple));
            box-shadow: 0 0 14px rgba(6,182,212,0.5), inset 0 1px 0 rgba(255,255,255,0.28);
            animation: led-breathe 2.5s ease-in-out infinite;
        }

        .bot-chest-led::after {
            content: "";
            position: absolute;
            inset: 2px auto 2px 6px;
            width: 10px;
            border-radius: inherit;
            background: rgba(255,255,255,0.55);
            filter: blur(3px);
            animation: screen-shimmer 2.5s ease-in-out infinite;
        }

        .bot-shadow {
            position: absolute;
            left: 50%;
            bottom: -5px;
            width: 86px; height: 13px;
            border-radius: 50%;
            background: rgba(6,182,212,0.15);
            filter: blur(7px);
            transform: translateX(-50%);
            animation: shadow-pulse 3.5s ease-in-out infinite;
        }

        .score-bar-wrap {
            position: absolute;
            bottom: 12px;
            left: 14px;
            right: 14px;
            z-index: 3;
        }

        .score-bar-label {
            display: flex;
            justify-content: space-between;
            color: var(--muted);
            font-size: 0.65rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 5px;
        }

        .score-bar-track {
            height: 5px;
            border-radius: 999px;
            background: rgba(255,255,255,0.07);
            overflow: hidden;
        }

        .score-bar-fill {
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, var(--red), var(--amber), var(--green));
            transition: width 0.8s ease;
        }

        /* ── Section title ── */
        .ag-section {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 36px 0 16px;
        }

        .ag-section-bar {
            width: 4px;
            height: 28px;
            border-radius: 999px;
        }

        .ag-section-label {
            color: var(--text);
            font-size: 1.1rem;
            font-weight: 800;
            letter-spacing: -0.01em;
        }

        .ag-section-count {
            margin-left: auto;
            padding: 3px 10px;
            border: 1px solid var(--border);
            border-radius: 999px;
            background: var(--glass);
            color: var(--muted);
            font-size: 0.72rem;
            font-weight: 700;
        }

        /* ── Glass card base ── */
        .ag-card {
            border: 1px solid var(--border);
            border-radius: 12px;
            background: var(--glass);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            overflow: hidden;
            transition: border-color 0.25s, box-shadow 0.25s;
        }

        .ag-card:hover {
            border-color: rgba(255,255,255,0.14);
            box-shadow: 0 8px 40px rgba(0,0,0,0.4);
        }

        /* ── Metric cards ── */
        .metric-card {
            position: relative;
            min-height: 130px;
            padding: 18px 16px 16px;
        }

        .metric-label {
            color: var(--muted);
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }

        .metric-value {
            margin-top: 14px;
            color: var(--text);
            font-size: 2rem;
            font-weight: 900;
            line-height: 1;
            font-family: 'JetBrains Mono', monospace;
        }

        .metric-meta {
            margin-top: 10px;
            color: var(--muted);
            font-size: 0.82rem;
        }

        .metric-glow {
            position: absolute;
            bottom: 0; left: 0; right: 0;
            height: 80px;
            pointer-events: none;
        }

        /* ── Feed rows ── */
        .feed-row {
            display: grid;
            grid-template-columns: 80px 140px minmax(0,1fr);
            gap: 14px;
            align-items: center;
            padding: 13px 16px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--glass);
            margin-bottom: 8px;
            transition: background 0.2s, border-color 0.2s;
        }

        .feed-row:hover {
            background: var(--glass-hi);
            border-color: rgba(255,255,255,0.13);
        }

        .feed-time {
            color: var(--muted);
            font-size: 0.8rem;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }

        .wf-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            white-space: nowrap;
        }

        .wf-chip.news    { background: rgba(6,182,212,0.12);  color: var(--cyan);   border: 1px solid rgba(6,182,212,0.25); }
        .wf-chip.jobs    { background: rgba(139,92,246,0.12); color: var(--purple); border: 1px solid rgba(139,92,246,0.25); }
        .wf-chip.pricing { background: rgba(245,158,11,0.12); color: var(--amber);  border: 1px solid rgba(245,158,11,0.25); }
        .wf-chip.digest  { background: rgba(16,185,129,0.12); color: var(--green);  border: 1px solid rgba(16,185,129,0.25); }
        .wf-chip.default { background: rgba(255,255,255,0.06); color: var(--muted); border: 1px solid var(--border); }

        .feed-body {
            min-width: 0;
            color: var(--text);
            font-size: 0.9rem;
            line-height: 1.5;
        }

        .feed-body code {
            padding: 1px 6px;
            border-radius: 5px;
            background: rgba(255,255,255,0.07);
            color: var(--cyan);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.82rem;
        }

        /* ── Signal log (decisions) ── */
        .signal-row {
            display: grid;
            grid-template-columns: 10px minmax(0,1fr) 160px;
            gap: 14px;
            align-items: start;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--glass);
            margin-bottom: 8px;
            transition: background 0.2s;
        }

        .signal-row:hover { background: var(--glass-hi); }

        .signal-dot {
            width: 10px; height: 10px;
            border-radius: 50%;
            margin-top: 5px;
            flex-shrink: 0;
        }

        .signal-body { min-width: 0; }

        .label-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .signal-reasoning {
            color: var(--text);
            font-size: 0.9rem;
            line-height: 1.5;
        }

        .signal-id {
            margin-top: 5px;
            color: var(--muted);
            font-size: 0.72rem;
            font-family: 'JetBrains Mono', monospace;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .signal-meta {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 6px;
        }

        .signal-time {
            color: var(--muted);
            font-size: 0.72rem;
            font-family: 'JetBrains Mono', monospace;
            white-space: nowrap;
        }

        /* ── Timeline (run history) ── */
        .timeline-row {
            display: grid;
            grid-template-columns: 12px minmax(0,1fr) auto;
            gap: 14px;
            align-items: start;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--glass);
            margin-bottom: 8px;
        }

        .timeline-dot {
            width: 12px; height: 12px;
            border-radius: 50%;
            margin-top: 4px;
            background: var(--green);
            box-shadow: 0 0 8px var(--green);
        }

        .timeline-dot.err {
            background: var(--red);
            box-shadow: 0 0 8px var(--red);
        }

        .timeline-main {
            color: var(--text);
            font-weight: 700;
            font-size: 0.93rem;
        }

        .timeline-meta {
            margin-top: 4px;
            color: var(--muted);
            font-size: 0.8rem;
        }

        .timeline-time {
            color: var(--muted);
            font-size: 0.75rem;
            font-family: 'JetBrains Mono', monospace;
            white-space: nowrap;
        }

        /* ── Empty & error panels ── */
        .ag-empty {
            padding: 20px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--glass);
            color: var(--muted);
            font-size: 0.9rem;
            text-align: center;
        }

        .ag-error-panel {
            padding: 14px 16px;
            border: 1px solid rgba(239,68,68,0.25);
            border-radius: 10px;
            background: rgba(239,68,68,0.07);
            color: #fca5a5;
            margin-bottom: 8px;
        }

        /* ── Keyframes ── */
        @keyframes pulse-dot {
            0%,100% { opacity: 0.7; transform: scale(0.9); }
            50%      { opacity: 1;   transform: scale(1.1); }
        }

        @keyframes ag-loader-spin {
            to { transform: rotate(360deg); }
        }

        @keyframes ag-loader-pulse {
            0%,100% { filter: brightness(0.92) saturate(1); }
            50%      { filter: brightness(1.22) saturate(1.25); }
        }

        @keyframes orb-drift-1 {
            0%,100% { transform: translate(0, 0); }
            50%      { transform: translate(30px, -20px); }
        }

        @keyframes orb-drift-2 {
            0%,100% { transform: translate(0, 0); }
            50%      { transform: translate(-20px, 15px); }
        }

        @keyframes scanline {
            0%   { left: -2px;  opacity: 0;   }
            10%  { opacity: 0.4; }
            90%  { opacity: 0.4; }
            100% { left: 100%;  opacity: 0;   }
        }

        @keyframes radar-breathe {
            0%,100% { transform: translate(-50%,-50%) scale(0.92); opacity: 0.4; }
            50%      { transform: translate(-50%,-50%) scale(1.08); opacity: 0.85; }
        }

        @keyframes radar-sweep {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
        }

        @keyframes float {
            0%,100% { transform: translateY(0); }
            50%      { transform: translateY(-7px); }
        }

        @keyframes bot-bob {
            0%,100% { transform: translateY(0) rotateZ(-0.5deg) rotateX(0deg); }
            25%      { transform: translateY(-7px) rotateZ(1.2deg) rotateX(3deg); }
            50%      { transform: translateY(-11px) rotateZ(0deg) rotateX(0deg); }
            75%      { transform: translateY(-6px) rotateZ(-1.1deg) rotateX(-2deg); }
        }

        @keyframes head-look {
            0%,100% { transform: translateX(0) rotateZ(0deg); }
            30%      { transform: translateX(3px) rotateZ(1.4deg); }
            58%      { transform: translateX(-3px) rotateZ(-1deg); }
            78%      { transform: translateX(1px) rotateZ(0.6deg); }
        }

        @keyframes eye-blink {
            0%,46%,54%,100% { transform: scaleY(1); }
            50%              { transform: scaleY(0.1); }
        }

        @keyframes smile-glow {
            0%,100% { opacity: 0.82; transform: translateX(-50%) scaleX(0.94); }
            50%      { opacity: 1;    transform: translateX(-50%) scaleX(1.08); }
        }

        @keyframes screen-shimmer {
            0%,100% { opacity: 0.45; transform: translateX(-6px); }
            50%      { opacity: 0.9;  transform: translateX(6px); }
        }

        @keyframes antenna-wiggle {
            0%,100% { transform: rotate(-2deg); }
            50%      { transform: rotate(2deg); }
        }

        @keyframes antenna-pulse {
            0%,100% { box-shadow: 0 0 16px var(--cyan), 0 0 32px rgba(6,182,212,0.4); }
            50%      { box-shadow: 0 0 24px var(--cyan), 0 0 48px rgba(6,182,212,0.6); }
        }

        @keyframes body-breathe {
            0%,100% { transform: scaleX(1) scaleY(1); }
            50%      { transform: scaleX(1.03) scaleY(0.98); }
        }

        @keyframes arm-swing-left {
            0%,100% { transform: rotate(10deg); }
            50%      { transform: rotate(-8deg); }
        }

        @keyframes arm-swing-right {
            0%,100% { transform: rotate(-10deg); }
            50%      { transform: rotate(8deg); }
        }

        @keyframes led-breathe {
            0%,100% { opacity: 0.7; }
            50%      { opacity: 1; }
        }

        @keyframes shadow-pulse {
            0%,100% { transform: translateX(-50%) scaleX(0.78); opacity: 0.42; }
            50%      { transform: translateX(-50%) scaleX(1.12); opacity: 0.82; }
        }

        /* ── Responsive ── */
        @media (max-width: 860px) {
            .ag-hero { grid-template-columns: 1fr; }
            .hero-kpis { grid-template-columns: repeat(2,1fr); }
            .feed-row { grid-template-columns: 1fr; gap: 8px; }
            .signal-row { grid-template-columns: 10px minmax(0,1fr); }
            .signal-meta { display: none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Renderers ─────────────────────────────────────────────────────────────────

def _wf_chip_class(wf: str) -> str:
    for key in ("news", "job", "pricing", "digest"):
        if key in wf.lower():
            return key
    return "default"


def render_hero(profile: dict, totals: dict) -> None:
    tone    = escape(profile["tone"])
    label   = escape(profile["label"])
    headline = escape(profile["headline"])
    detail  = escape(profile["detail"])
    score   = int(totals["score"])
    runs    = int(totals["run_count"])
    actions = int(totals["action_count"])
    utc_now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    fill_w  = f"{score}%"
    render_html(
        f"""
        <div class="ag-hero">
            <div class="ag-orb ag-orb-1"></div>
            <div class="ag-orb ag-orb-2"></div>
            <div class="ag-orb ag-orb-3"></div>
            <div class="ag-grid-overlay"></div>
            <div class="ag-scanline"></div>

            <div class="hero-copy">
                <div class="hero-eyebrow">
                    <span class="hero-eyebrow-dot"></span>
                    Autonomous Intel Platform
                </div>
                <h1 class="hero-title">Argus Intel<br>Agent</h1>
                <p class="hero-sub">{headline}. {detail}.</p>
                <div class="hero-pills">
                    <div class="hero-pill tone-{tone}">
                        <span class="dot"></span>
                        {label}
                    </div>
                    <div class="hero-pill">
                        {utc_now}
                    </div>
                </div>
                <div class="hero-kpis">
                    <div class="hero-kpi">
                        <div class="hero-kpi-label">Health</div>
                        <div class="hero-kpi-value">{score}<small style="font-size:1rem;opacity:0.5">%</small></div>
                    </div>
                    <div class="hero-kpi">
                        <div class="hero-kpi-label">Total Runs</div>
                        <div class="hero-kpi-value">{runs}</div>
                    </div>
                    <div class="hero-kpi">
                        <div class="hero-kpi-label">Actions</div>
                        <div class="hero-kpi-value">{actions}</div>
                    </div>
                </div>
            </div>

            <div class="bot-panel">
                <div class="bot-panel-grid"></div>
                <div class="bot-radar bot-radar-1"></div>
                <div class="bot-radar bot-radar-2"></div>
                <div class="bot-sweep"></div>
                <div class="bot-orbit-chips">
                    <div class="orbit-chip news">News</div>
                    <div class="orbit-chip jobs">Jobs</div>
                    <div class="orbit-chip pricing">Price</div>
                    <div class="orbit-chip digest">Digest</div>
                </div>
                <div class="ag-bot">
                    <div class="bot-head-wrap">
                        <div class="bot-antenna-ball"></div>
                        <div class="bot-antenna-stem"></div>
                    </div>
                    <div class="bot-head">
                        <div class="bot-ear left"></div>
                        <div class="bot-ear right"></div>
                        <div class="bot-eye left"></div>
                        <div class="bot-eye right"></div>
                        <div class="bot-cheek left"></div>
                        <div class="bot-cheek right"></div>
                        <div class="bot-smile"></div>
                    </div>
                    <div class="bot-neck"></div>
                    <div class="bot-arm left"><span></span></div>
                    <div class="bot-arm right"><span></span></div>
                    <div class="bot-body">
                        <div class="bot-chest-led"></div>
                    </div>
                    <div class="bot-shadow"></div>
                </div>
                <div class="score-bar-wrap">
                    <div class="score-bar-label">
                        <span>Health Score</span>
                        <span style="color:var(--cyan);font-family:'JetBrains Mono',monospace">{score}%</span>
                    </div>
                    <div class="score-bar-track">
                        <div class="score-bar-fill" style="width:{fill_w}"></div>
                    </div>
                </div>
            </div>
        </div>
        """
    )


def render_section_title(label: str, count: int | None = None) -> None:
    colors = {"Workflow Pulse": "#22d3ee", "LLM Signal Log": "#a78bfa",
              "Recent Actions": "#fbbf24", "Run History": "#34d399",
              "Error Log": "#fb7185"}
    bar_color = colors.get(label.split("(")[0].strip(), "#64748b")
    count_html = (
        f'<div class="ag-section-count">{count}</div>' if count is not None else ""
    )
    st.markdown(
        f'<div class="ag-section">'
        f'<div class="ag-section-bar" style="background:{bar_color};'
        f'box-shadow:0 0 10px {bar_color}55"></div>'
        f'<div class="ag-section-label">{escape(label)}</div>'
        f'{count_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_metric_grid(summary_df: pd.DataFrame) -> None:
    if summary_df.empty:
        st.markdown('<div class="ag-empty">No workflow runs recorded yet.</div>', unsafe_allow_html=True)
        return

    wf_colors = {
        "news_watch":    ("#22d3ee", "rgba(34,211,238,0.12)"),
        "job_watch":     ("#a78bfa", "rgba(167,139,250,0.12)"),
        "pricing_watch": ("#fbbf24", "rgba(251,191,36,0.12)"),
        "weekly_digest": ("#34d399", "rgba(52,211,153,0.12)"),
    }
    fallbacks = [
        ("#22d3ee", "rgba(34,211,238,0.12)"),
        ("#a78bfa", "rgba(167,139,250,0.12)"),
        ("#fbbf24", "rgba(251,191,36,0.12)"),
        ("#34d399", "rgba(52,211,153,0.12)"),
    ]

    cols = st.columns(max(1, len(summary_df)))
    for idx, (col, (_, row)) in enumerate(zip(cols, summary_df.iterrows())):
        with col:
            wf_key    = str(row["workflow"])
            color, bg = wf_colors.get(wf_key, fallbacks[idx % len(fallbacks)])
            label     = escape(wf_key.replace("_", " ").title())
            elapsed   = escape(humanize_time(row["last_run"]))
            runs      = int(row["total_runs"] or 0)
            items     = int(row["total_items"] or 0)
            st.markdown(
                f'<div class="ag-card metric-card" style="background:{bg};border-top:2px solid {color};'
                f'box-shadow:0 0 24px {color}1a;">'
                f'<div class="metric-label">{label}</div>'
                f'<div class="metric-value" style="color:{color}">{elapsed}</div>'
                f'<div class="metric-meta">{runs} runs &nbsp;&middot;&nbsp; {items} items</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_decisions(decisions: list[dict]) -> None:
    if not decisions:
        st.markdown('<div class="ag-empty">No LLM decisions recorded yet.</div>', unsafe_allow_html=True)
        return

    for dec in decisions:
        time_str  = dec["time"].strftime("%b %d %H:%M") if dec["time"] else "?"
        label     = dec.get("label", "unknown")
        color     = _LABEL_COLOR.get(label, "#64748b")
        wf        = str(dec.get("workflow", ""))
        wf_label  = escape(wf.replace("_", " ").title())
        chip_cls  = _wf_chip_class(wf)
        item_id   = escape(str(dec.get("item_id", ""))[:80])
        reasoning = escape(str(dec.get("reasoning", "")))
        badge_lbl = escape(label.replace("_", " ").title())
        is_alert  = label in ("controversy", "material", "executive_change", "funding", "product_launch")
        dot_glow  = f"box-shadow:0 0 8px {color};" if is_alert else ""
        st.markdown(
            f'<div class="signal-row">'
            f'<div class="signal-dot" style="background:{color};{dot_glow}"></div>'
            f'<div class="signal-body">'
            f'<div class="label-badge" style="background:{color}22;color:{color};border:1px solid {color}44">{badge_lbl}</div>'
            f'<div class="signal-reasoning">{reasoning}</div>'
            f'<div class="signal-id">{item_id}</div>'
            f'</div>'
            f'<div class="signal-meta">'
            f'<div class="wf-chip {chip_cls}">{wf_label}</div>'
            f'<div class="signal-time">{escape(time_str)}</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_actions(actions: list[dict]) -> None:
    if not actions:
        st.markdown('<div class="ag-empty">No actions recorded yet.</div>', unsafe_allow_html=True)
        return

    for action in actions:
        time_str    = action["time"].strftime("%H:%M") if action["time"] else "?"
        wf          = str(action.get("workflow", ""))
        wf_label    = escape(wf.replace("_", " ").title())
        chip_cls    = _wf_chip_class(wf)
        action_name = escape(str(action.get("action", "")))
        target      = escape(str(action.get("target", "")))
        status      = escape(str(action.get("status", "")))
        detail      = str(action.get("detail", ""))
        detail_html = f'<div class="metric-meta">{escape(detail)}</div>' if detail else ""
        st.markdown(
            f'<div class="feed-row">'
            f'<div class="feed-time">{escape(time_str)}</div>'
            f'<div class="wf-chip {chip_cls}">{wf_label}</div>'
            f'<div class="feed-body"><strong>{action_name}</strong> &rarr; '
            f'<code>{target}</code>'
            f'<span style="color:var(--muted);margin-left:6px">({status})</span>'
            f'{detail_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_run_history(runs: list[dict]) -> None:
    if not runs:
        st.markdown('<div class="ag-empty">No runs recorded yet.</div>', unsafe_allow_html=True)
        return

    for run in runs:
        time_str   = run["trigger_time"].strftime("%Y-%m-%d %H:%M UTC") if run["trigger_time"] else "?"
        n_dec      = len(run["decisions"])
        n_act      = len(run["actions"])
        n_err      = len(run["errors"])
        dur        = f"{run['duration_seconds']}s" if run["duration_seconds"] is not None else "?"
        err_tag    = f" ⚠ {n_err} error(s)" if n_err else ""
        title      = (
            f"{run['workflow'].replace('_',' ').title()} — {time_str} "
            f"| {run['items_processed']} items | {n_dec} decisions | {n_act} actions | {dur}{err_tag}"
        )
        with st.expander(title):
            if run["decisions"]:
                st.write("**LLM Decisions**")
                for d in run["decisions"]:
                    lbl   = d.get("label", "")
                    color = _LABEL_COLOR.get(lbl, "#64748b")
                    st.markdown(
                        f'<span style="color:{color};font-weight:800">{lbl.replace("_"," ").title()}</span>'
                        f' — {escape(d.get("reasoning",""))}<br/>'
                        f'<small style="color:var(--muted)">{escape(d.get("item_id","")[:90])}</small>',
                        unsafe_allow_html=True,
                    )
            if run["actions"]:
                st.write("**Actions Taken**")
                for a in run["actions"]:
                    target     = str(a.get("target", ""))
                    detail     = str(a.get("detail", ""))
                    detail_str = f" → {detail}" if detail else ""
                    st.write(f"- `{a.get('action','')}` → {target} ({a.get('status','')}){detail_str}")
            if run["errors"]:
                st.write("**Errors**")
                for e in run["errors"]:
                    st.error(e.get("error", "Unknown error"))
                    if e.get("traceback"):
                        st.code(e["traceback"], language="python")


def render_errors(error_logs: list[dict]) -> None:
    has_errors = False
    for log in error_logs:
        errors = _json_array(log["errors"])
        if errors:
            has_errors = True
            stamp = log["trigger_time"].strftime("%Y-%m-%d %H:%M")
            title = f"{log['workflow'].replace('_',' ').title()} @ {stamp} — {len(errors)} error(s)"
            with st.expander(title):
                for err in errors:
                    st.error(err.get("error", "Unknown error"))
                    if err.get("traceback"):
                        st.code(err["traceback"], language="python")
    if not has_errors:
        st.markdown('<div class="ag-empty">No errors in the last 24 hours.</div>', unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────

render_styles()

error_rate  = load_error_rate()
profile     = status_profile(error_rate)
summary_df  = load_run_summary()
actions     = load_recent_actions(20)
decisions   = load_recent_decisions(40)
run_history = load_run_history(20)
error_logs  = load_error_logs()
recent_runs = load_recent_runs()
totals      = dashboard_totals(summary_df, actions, recent_runs, error_rate)

render_hero(profile, totals)

render_section_title("Workflow Pulse", len(summary_df) if not summary_df.empty else None)
render_metric_grid(summary_df)

render_section_title("LLM Signal Log", len(decisions))
st.caption("Every classification Argus made — label, reasoning, and source item.")
render_decisions(decisions)

render_section_title("Recent Actions", len(actions))
st.caption("External writes: Slack posts, calendar events, Google Sheet rows.")
render_actions(actions)

render_section_title("Run History", len(run_history))
st.caption("Expand any run to inspect decisions, actions, and errors.")
render_run_history(run_history)

render_section_title("Error Log (last 24 h)")
if profile["tone"] == "alert":
    st.markdown(
        f'<div class="ag-error-panel">{escape(profile["detail"])}</div>',
        unsafe_allow_html=True,
    )
render_errors(error_logs)

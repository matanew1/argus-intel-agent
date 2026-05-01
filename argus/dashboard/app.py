"""Streamlit dashboard — last run per workflow, last 20 actions, error rate."""
import json
import sys
from datetime import datetime, timedelta, timezone
from html import escape
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


# ── Data loaders (cached 30s) ────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_error_rate(hours: int = 24) -> dict:
    """Return total runs, errored runs, and error rate % for the last N hours."""
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        logs = session.query(RunLog).filter(RunLog.trigger_time >= cutoff).all()
        total = len(logs)
        errored = sum(1 for r in logs if _json_array(r.errors))
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
        return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)
    except SQLAlchemyError:
        session.rollback()
        return pd.DataFrame(columns=_SUMMARY_COLUMNS)
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
    except SQLAlchemyError:
        session.rollback()
        return []
    finally:
        session.close()


def humanize_time(dt: datetime | None) -> str:
    """Convert a UTC datetime to a human-readable relative string (e.g. '5m ago')."""
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


def _json_array(raw: str | None) -> list:
    """Return a JSON array from a RunLog text column, swallowing bad rows."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _is_missing_table_error(exc: SQLAlchemyError) -> bool:
    """Return True when the database exists but Argus tables have not been created."""
    original = getattr(exc, "orig", exc)
    pgcode = getattr(original, "pgcode", "")
    message = str(original).lower()
    return (
        pgcode == "42P01"
        or "undefinedtable" in message
        or 'relation "run_log" does not exist' in message
        or "no such table" in message
    )


def status_profile(err: dict) -> dict:
    """Return display copy and tone for the current health state."""
    if err.get("state") == "missing_tables":
        return {
            "tone": "idle",
            "label": "No logbook yet",
            "headline": "Argus is ready, but the database tables are empty",
            "detail": "Run any workflow once, or initialize the database, then refresh",
        }
    if err.get("state") == "db_error":
        return {
            "tone": "alert",
            "label": "Database check needed",
            "headline": "Argus could not read the workflow log",
            "detail": "Check DATABASE_URL and database connectivity, then refresh",
        }
    if err["rate"] == 0 and err["total"] > 0:
        return {
            "tone": "ok",
            "label": "Operational",
            "headline": "Argus is on patrol",
            "detail": f"{err['total']} run(s) in 24h with no errors",
        }
    if err["total"] == 0:
        return {
            "tone": "idle",
            "label": "Warming up",
            "headline": "Argus is waiting for a signal",
            "detail": "No workflow runs recorded in the last 24h",
        }
    return {
        "tone": "alert",
        "label": "Needs review",
        "headline": "Argus found something noisy",
        "detail": f"{err['errored']} errored run(s), {err['rate']:.1f}% error rate",
    }


def render_styles() -> None:
    """Inject dashboard CSS."""
    st.markdown(
        """
        <style>
        :root {
            --argus-bg: #f6f2e8;
            --argus-panel: #fffdfa;
            --argus-ink: #1f2837;
            --argus-muted: #657083;
            --argus-line: rgba(31, 40, 55, 0.12);
            --argus-teal: #008a83;
            --argus-green: #2f9e6d;
            --argus-coral: #e85d75;
            --argus-violet: #6457d8;
            --argus-amber: #f0b23d;
        }

        .stApp {
            background:
                linear-gradient(180deg, rgba(246, 242, 232, 0.96), rgba(250, 248, 242, 1)),
                repeating-linear-gradient(90deg, rgba(31,40,55,0.025) 0 1px, transparent 1px 28px);
            color: var(--argus-ink);
        }

        .block-container {
            max-width: 1220px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3, p {
            letter-spacing: 0;
        }

        div[data-testid="stMetric"] {
            background: transparent;
            border: 0;
        }

        .argus-hero {
            position: relative;
            display: grid;
            grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
            gap: 24px;
            align-items: stretch;
            min-height: 260px;
            padding: 24px;
            overflow: hidden;
            border: 1px solid var(--argus-line);
            border-radius: 8px;
            background:
                linear-gradient(135deg, #fffdfa 0%, #f4fbf7 52%, #fff4ec 100%);
            box-shadow: 0 18px 48px rgba(31, 40, 55, 0.10);
        }

        .hero-copy {
            position: relative;
            z-index: 2;
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-width: 0;
        }

        .eyebrow {
            width: fit-content;
            margin: 0 0 14px;
            padding: 7px 10px;
            border: 1px solid rgba(0, 138, 131, 0.22);
            border-radius: 999px;
            color: var(--argus-teal);
            background: rgba(0, 138, 131, 0.08);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
        }

        .hero-copy h1 {
            margin: 0;
            color: var(--argus-ink);
            font-size: clamp(2.3rem, 4vw, 4.4rem);
            line-height: 0.95;
            font-weight: 900;
        }

        .hero-copy p {
            max-width: 650px;
            margin: 18px 0 0;
            color: var(--argus-muted);
            font-size: 1rem;
            line-height: 1.65;
        }

        .status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 22px;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            min-height: 36px;
            padding: 8px 12px;
            border-radius: 999px;
            border: 1px solid var(--argus-line);
            background: rgba(255, 255, 255, 0.72);
            color: var(--argus-ink);
            font-weight: 800;
            box-shadow: 0 8px 22px rgba(31, 40, 55, 0.08);
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: var(--argus-green);
            box-shadow: 0 0 0 5px rgba(47, 158, 109, 0.14);
            animation: pulse-dot 1.8s ease-in-out infinite;
        }

        .tone-idle .status-dot {
            background: var(--argus-amber);
            box-shadow: 0 0 0 5px rgba(240, 178, 61, 0.16);
        }

        .tone-alert .status-dot {
            background: var(--argus-coral);
            box-shadow: 0 0 0 5px rgba(232, 93, 117, 0.16);
        }

        .bot-stage {
            position: relative;
            min-height: 220px;
            border: 1px solid rgba(31, 40, 55, 0.10);
            border-radius: 8px;
            background:
                linear-gradient(180deg, rgba(255,255,255,0.70), rgba(255,255,255,0.38)),
                repeating-linear-gradient(0deg, rgba(0,138,131,0.06) 0 2px, transparent 2px 22px);
            overflow: hidden;
        }

        .bot-track {
            position: absolute;
            left: 10%;
            right: 10%;
            bottom: 38px;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(31,40,55,0.22), transparent);
        }

        .scanner-line {
            position: absolute;
            top: 18px;
            bottom: 18px;
            width: 2px;
            background: rgba(0, 138, 131, 0.46);
            box-shadow: 0 0 18px rgba(0, 138, 131, 0.35);
            animation: scan-stage 4.5s ease-in-out infinite;
        }

        .argus-bot {
            position: absolute;
            left: calc(50% - 70px);
            bottom: 45px;
            width: 140px;
            height: 150px;
            transform-origin: 50% 100%;
            animation: argus-patrol 5.8s ease-in-out infinite;
        }

        .bot-shadow {
            position: absolute;
            left: 18px;
            right: 18px;
            bottom: -10px;
            height: 16px;
            border-radius: 999px;
            background: rgba(31, 40, 55, 0.16);
            filter: blur(4px);
            animation: shadow-breathe 5.8s ease-in-out infinite;
        }

        .bot-antenna {
            position: absolute;
            left: 66px;
            top: -13px;
            width: 8px;
            height: 22px;
            border-radius: 999px;
            background: var(--argus-ink);
        }

        .bot-antenna::after {
            content: "";
            position: absolute;
            left: -5px;
            top: -11px;
            width: 18px;
            height: 18px;
            border-radius: 999px;
            background: var(--argus-amber);
            box-shadow: 0 0 16px rgba(240, 178, 61, 0.55);
            animation: antenna-glow 1.6s ease-in-out infinite;
        }

        .bot-head {
            position: absolute;
            left: 20px;
            top: 8px;
            width: 100px;
            height: 72px;
            border: 3px solid var(--argus-ink);
            border-radius: 8px;
            background: linear-gradient(180deg, #fff 0%, #dff6ef 100%);
            box-shadow: inset 0 -8px 0 rgba(0, 138, 131, 0.10);
        }

        .bot-eye {
            position: absolute;
            top: 25px;
            width: 17px;
            height: 17px;
            border-radius: 999px;
            background: var(--argus-teal);
            box-shadow: 0 0 14px rgba(0, 138, 131, 0.55);
            animation: bot-blink 4.2s ease-in-out infinite;
        }

        .bot-eye.left { left: 25px; }
        .bot-eye.right { right: 25px; }

        .bot-smile {
            position: absolute;
            left: 39px;
            top: 47px;
            width: 22px;
            height: 9px;
            border-bottom: 3px solid var(--argus-ink);
            border-radius: 0 0 999px 999px;
        }

        .bot-body {
            position: absolute;
            left: 28px;
            top: 84px;
            width: 84px;
            height: 58px;
            border: 3px solid var(--argus-ink);
            border-radius: 8px;
            background: linear-gradient(135deg, #fff6dc 0%, #ffffff 55%, #efeaff 100%);
        }

        .bot-body::before,
        .bot-body::after {
            content: "";
            position: absolute;
            top: 16px;
            width: 30px;
            height: 8px;
            border-radius: 999px;
            background: var(--argus-coral);
        }

        .bot-body::before {
            left: -34px;
            transform: rotate(16deg);
            transform-origin: right center;
            animation: bot-wave-left 2.5s ease-in-out infinite;
        }

        .bot-body::after {
            right: -34px;
            transform: rotate(-16deg);
            transform-origin: left center;
            animation: bot-wave-right 2.8s ease-in-out infinite;
        }

        .bot-badge {
            position: absolute;
            left: 17px;
            top: 17px;
            min-width: 48px;
            padding: 5px 7px;
            border-radius: 6px;
            background: var(--argus-ink);
            color: #fffdfa;
            font-size: 0.68rem;
            font-weight: 900;
            text-align: center;
        }

        .section-title {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 30px 0 12px;
            color: var(--argus-ink);
            font-size: 1.2rem;
            font-weight: 900;
        }

        .section-title::before {
            content: "";
            width: 10px;
            height: 22px;
            border-radius: 999px;
            background: var(--argus-teal);
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(205px, 1fr));
            gap: 12px;
        }

        .metric-card,
        .feed-row,
        .empty-panel,
        .error-panel {
            border: 1px solid var(--argus-line);
            border-radius: 8px;
            background: rgba(255, 253, 250, 0.86);
            box-shadow: 0 10px 28px rgba(31, 40, 55, 0.07);
        }

        .metric-card {
            position: relative;
            min-height: 128px;
            padding: 16px;
            overflow: hidden;
        }

        .metric-card::after {
            content: "";
            position: absolute;
            left: 0;
            right: 0;
            bottom: 0;
            height: 4px;
            background: var(--accent, var(--argus-teal));
        }

        .metric-label {
            color: var(--argus-muted);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
        }

        .metric-value {
            margin-top: 12px;
            color: var(--argus-ink);
            font-size: 2rem;
            line-height: 1;
            font-weight: 900;
        }

        .metric-meta {
            margin-top: 12px;
            color: var(--argus-muted);
            font-size: 0.9rem;
        }

        .feed-list {
            display: grid;
            gap: 10px;
        }

        .feed-row {
            display: grid;
            grid-template-columns: 86px 150px minmax(0, 1fr);
            gap: 12px;
            align-items: center;
            padding: 12px 14px;
        }

        .feed-time {
            color: var(--argus-muted);
            font-size: 0.86rem;
            font-weight: 800;
        }

        .workflow-chip {
            width: fit-content;
            max-width: 100%;
            padding: 6px 9px;
            border-radius: 999px;
            background: rgba(100, 87, 216, 0.10);
            color: var(--argus-violet);
            font-size: 0.78rem;
            font-weight: 850;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .feed-body {
            min-width: 0;
            color: var(--argus-ink);
            line-height: 1.45;
        }

        .feed-body code {
            padding: 2px 5px;
            border-radius: 5px;
            background: rgba(31, 40, 55, 0.08);
            color: var(--argus-ink);
            white-space: normal;
        }

        .empty-panel,
        .error-panel {
            padding: 18px;
            color: var(--argus-muted);
        }

        .error-panel {
            border-color: rgba(232, 93, 117, 0.28);
            color: var(--argus-coral);
            background: rgba(255, 245, 247, 0.85);
        }

        @keyframes pulse-dot {
            0%, 100% { transform: scale(0.88); opacity: 0.7; }
            50% { transform: scale(1.1); opacity: 1; }
        }

        @keyframes scan-stage {
            0%, 100% { left: 12%; opacity: 0.18; }
            50% { left: 88%; opacity: 0.72; }
        }

        @keyframes argus-patrol {
            0%, 100% { transform: translate(-34px, 0) rotate(-3deg); }
            25% { transform: translate(8px, -8px) rotate(2deg); }
            50% { transform: translate(42px, 0) rotate(3deg); }
            75% { transform: translate(4px, -6px) rotate(-1deg); }
        }

        @keyframes shadow-breathe {
            0%, 100% { transform: scaleX(0.82); opacity: 0.12; }
            50% { transform: scaleX(1.1); opacity: 0.22; }
        }

        @keyframes antenna-glow {
            0%, 100% { transform: scale(0.88); }
            50% { transform: scale(1.08); }
        }

        @keyframes bot-blink {
            0%, 46%, 54%, 100% { transform: scaleY(1); }
            50% { transform: scaleY(0.15); }
        }

        @keyframes bot-wave-left {
            0%, 100% { transform: rotate(16deg); }
            50% { transform: rotate(2deg); }
        }

        @keyframes bot-wave-right {
            0%, 100% { transform: rotate(-16deg); }
            50% { transform: rotate(-2deg); }
        }

        @media (max-width: 820px) {
            .argus-hero {
                grid-template-columns: 1fr;
                padding: 18px;
            }

            .bot-stage {
                min-height: 210px;
            }

            .feed-row {
                grid-template-columns: 1fr;
                gap: 8px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(profile: dict) -> None:
    """Render the animated Argus header."""
    tone = escape(profile["tone"])
    label = escape(profile["label"])
    headline = escape(profile["headline"])
    detail = escape(profile["detail"])
    st.markdown(
        f"""
        <div class="argus-hero tone-{tone}">
            <div class="hero-copy">
                <div class="eyebrow">Autonomous Intel Companion</div>
                <h1>Argus Intel Agent</h1>
                <p>{headline}. {detail}.</p>
                <div class="status-row">
                    <div class="status-pill">
                        <span class="status-dot"></span>
                        <span>{label}</span>
                    </div>
                    <div class="status-pill">Robot: ARGUS</div>
                </div>
            </div>
            <div class="bot-stage" aria-label="Animated Argus robot">
                <div class="scanner-line"></div>
                <div class="bot-track"></div>
                <div class="argus-bot">
                    <div class="bot-shadow"></div>
                    <div class="bot-antenna"></div>
                    <div class="bot-head">
                        <span class="bot-eye left"></span>
                        <span class="bot-eye right"></span>
                        <span class="bot-smile"></span>
                    </div>
                    <div class="bot-body">
                        <span class="bot-badge">ARGUS</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_title(label: str) -> None:
    """Render a compact section title."""
    st.markdown(f'<div class="section-title">{escape(label)}</div>', unsafe_allow_html=True)


def render_metric_grid(summary_df: pd.DataFrame) -> None:
    """Render workflow summary metric cards."""
    if summary_df.empty:
        st.markdown('<div class="empty-panel">No workflow runs recorded yet.</div>', unsafe_allow_html=True)
        return

    accents = ["#008a83", "#e85d75", "#6457d8", "#f0b23d", "#2f9e6d"]
    cards = []
    for idx, (_, row) in enumerate(summary_df.iterrows()):
        label = escape(str(row["workflow"]).replace("_", " ").title())
        elapsed = escape(humanize_time(row["last_run"]))
        total_runs = int(row["total_runs"] or 0)
        total_items = int(row["total_items"] or 0)
        accent = accents[idx % len(accents)]
        cards.append(
            f"""
            <div class="metric-card" style="--accent: {accent};">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{elapsed}</div>
                <div class="metric-meta">{total_runs} total runs | {total_items} items processed</div>
            </div>
            """
        )
    st.markdown(f'<div class="metric-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_actions(actions: list[dict]) -> None:
    """Render recent actions as a styled feed."""
    if not actions:
        st.markdown('<div class="empty-panel">No actions recorded yet.</div>', unsafe_allow_html=True)
        return

    rows = []
    for action in actions:
        time_str = action["time"].strftime("%I:%M %p") if action["time"] else "?"
        workflow = escape(str(action.get("workflow", "")).replace("_", " ").title())
        action_name = escape(str(action.get("action", "")))
        target = escape(str(action.get("target", "")))
        status = escape(str(action.get("status", "")))
        detail = escape(str(action.get("detail", "")))
        detail_html = f'<div class="metric-meta">{detail}</div>' if detail else ""
        rows.append(
            f"""
            <div class="feed-row">
                <div class="feed-time">{escape(time_str)}</div>
                <div class="workflow-chip">{workflow}</div>
                <div class="feed-body">
                    <strong>{action_name}</strong> -> <code>{target}</code> ({status})
                    {detail_html}
                </div>
            </div>
            """
        )
    st.markdown(f'<div class="feed-list">{"".join(rows)}</div>', unsafe_allow_html=True)


def render_errors(error_logs: list[RunLog]) -> None:
    """Render the error log section."""
    has_errors = False
    for log in error_logs:
        errors = _json_array(log.errors)
        if errors:
            has_errors = True
            stamp = log.trigger_time.strftime("%Y-%m-%d %H:%M")
            title = f"{log.workflow.replace('_',' ').title()} @ {stamp} - {len(errors)} error(s)"
            with st.expander(title):
                for err in errors:
                    st.error(err.get("error", "Unknown error"))
                    if err.get("traceback"):
                        st.code(err["traceback"], language="python")

    if not has_errors:
        st.markdown('<div class="empty-panel">No errors in the last 24 hours.</div>', unsafe_allow_html=True)


render_styles()

error_rate = load_error_rate()
profile = status_profile(error_rate)
summary_df = load_run_summary()
actions = load_recent_actions(20)
error_logs = load_error_logs()

render_hero(profile)

render_section_title("Workflow Pulse")
render_metric_grid(summary_df)

render_section_title("Recent Actions")
render_actions(actions)

render_section_title("Error Log")
if profile["tone"] == "alert":
    st.markdown(
        f'<div class="error-panel">{escape(profile["detail"])}</div>',
        unsafe_allow_html=True,
    )
render_errors(error_logs)

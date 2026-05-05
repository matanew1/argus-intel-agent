"""Tab renderers: Overview, How It Works, and Proof."""
import html

import pandas as pd
import streamlit as st

from argus.dashboard.components import render_section
from argus.dashboard.data import (
    _json_array,
    format_dt,
    format_dt_israel,
    format_number,
    humanize_time,
    page_snapshots_table,
    runs_since_table,
    seen_summary_table,
    to_table,
)

_PIPELINE_STEPS = [
    ("01", "Scheduler fires",   "GitHub Actions cron triggers the workflow automatically.",          "GitHub Actions"),
    ("02", "Config loads",      "Reads competitors, criteria, and notification targets.",            "config.yaml"),
    ("03", "Signals fetched",   "Fetches news articles, job postings, pricing pages, or past logs.", "APIs / web"),
    ("04", "Dedup check",       "Skips anything already seen. Pricing Watch uses page snapshots.",   "Postgres"),
    ("05", "LLM classifies",    "Mistral assigns a structured label + reasoning to each signal.",    "Mistral"),
    ("06", "Decision logged",   "Label and reasoning saved to run_log.decisions.",                   "run_log"),
    ("07", "Action taken",      "Actionable signals write to Slack, Calendar, Sheets, or email.",    "Integrations"),
    ("08", "Audit complete",    "run_log row saved. Dashboard reads it as evidence.",                "Dashboard"),
]

_WORKFLOW_SCHEDULES = [
    ("News Watch",     "Every 2 hours",     "news, funding, launches, controversies", "Slack alert · Calendar event"),
    ("Job Watch",      "Daily 9am UTC",     "new job postings per competitor",         "Google Sheets row"),
    ("Pricing Watch",  "Daily 8am UTC",     "competitor pricing/product pages",        "Slack DM · Calendar event"),
    ("Weekly Digest",  "Friday 4pm UTC",    "all signals from the past 7 days",        "Email · Slack TL;DR"),
]


# ── Tab 1: Overview ──────────────────────────────────────────────────────────

def render_overview(summary_df: pd.DataFrame, actions_30d: list[dict]) -> None:
    render_section("What Argus Monitors", "Four scheduled workflows, each with a different signal source and output.")
    _render_workflow_cards()

    render_section("Workflow Run Status", "Last run time and total executions per workflow.")
    if summary_df.empty:
        st.info("No workflow runs recorded yet — waiting for the first scheduled run.")
    else:
        table = summary_df.copy()
        table["last_run"] = table["last_run"].apply(format_dt_israel)
        table["last_seen"] = summary_df["last_run"].apply(humanize_time)
        table["total_runs"] = table["total_runs"].fillna(0).astype(int)
        table["total_items"] = table["total_items"].fillna(0).astype(int)
        st.dataframe(
            table[["workflow", "last_seen", "last_run", "total_runs", "total_items"]],
            width="stretch",
            hide_index=True,
        )

    if actions_30d:
        render_section("Recent Actions", f"Last {min(5, len(actions_30d))} external writes (Slack, Calendar, Sheets, email).")
        recent = actions_30d[:5]
        rows = [{"time": format_dt_israel(r["time"]), "workflow": r["workflow"], "action": r["action"], "detail": (r.get("detail") or r.get("target") or "")[:80]} for r in recent]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_workflow_cards() -> None:
    cols = st.columns(4)
    card_data = [
        ("News Watch",    "Every 2h",    "Slack · Calendar", "#3b82f6"),
        ("Job Watch",     "Daily 9am",   "Google Sheets",    "#0d9488"),
        ("Pricing Watch", "Daily 8am",   "Slack DM · Cal",   "#d97706"),
        ("Weekly Digest", "Fri 4pm",     "Email · Slack",    "#7c3aed"),
    ]
    for col, (name, schedule, output, color) in zip(cols, card_data):
        with col:
            st.markdown(
                f'<div style="border:1px solid #e2e8f0;border-top:3px solid {color};border-radius:0.75rem;padding:1rem;background:#fff;">'
                f'<div style="font-size:0.75rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">{html.escape(schedule)}</div>'
                f'<div style="font-size:1rem;font-weight:700;color:#0f172a;margin:0.4rem 0 0.3rem;">{html.escape(name)}</div>'
                f'<div style="font-size:0.82rem;color:#64748b;">{html.escape(output)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Tab 2: How It Works ──────────────────────────────────────────────────────

def render_how_it_works(scheduler_df: pd.DataFrame) -> None:
    render_section("Architecture", "Every workflow follows the same path: cron → fetch → classify → act → log.")
    _render_architecture()

    render_section("Step-by-Step Pipeline", "The exact same 8 steps for every scheduled run.")
    _render_pipeline_steps()

    render_section("Cron Schedule", "Actual cron definitions from the GitHub Actions workflow files.")
    cols_to_show = [c for c in ["name", "cadence", "cron", "command"] if c in scheduler_df.columns]
    st.dataframe(scheduler_df[cols_to_show], width="stretch", hide_index=True)


def _render_architecture() -> None:
    st.graphviz_chart(
        """
        digraph {
          graph [rankdir=LR, bgcolor="transparent", pad="0.3", nodesep="0.6", ranksep="0.8"];
          node [shape=box, style="rounded,filled", color="#B9C3D3", fillcolor="#FFFFFF",
                fontname="Helvetica", fontsize=11, fontcolor="#172033"];
          edge [color="#526174", arrowsize=0.8];

          scheduler [label="GitHub Actions\\ncron", fillcolor="#EFF6FF", color="#93C5FD"];
          config    [label="config.yaml"];
          news      [label="News Watch"];
          jobs      [label="Job Watch"];
          pricing   [label="Pricing Watch"];
          digest    [label="Weekly Digest"];
          llm       [label="Mistral AI\\nclassifier", fillcolor="#ECFDF5", color="#99F6E4"];
          db        [label="Postgres\\naudit trail",  fillcolor="#F8FAFC", color="#94A3B8"];
          slack     [label="Slack",           fillcolor="#FFF7ED", color="#FDBA74"];
          calendar  [label="Calendar",        fillcolor="#F0FDFA", color="#5EEAD4"];
          sheets    [label="Sheets",          fillcolor="#F7FEE7", color="#BEF264"];
          email     [label="Email",           fillcolor="#FEF2F2", color="#FCA5A5"];

          scheduler -> news; scheduler -> jobs; scheduler -> pricing; scheduler -> digest;
          config    -> news; config -> jobs; config -> pricing; config -> digest;
          news    -> llm; jobs -> llm; pricing -> llm; digest -> llm;
          llm     -> db;
          news    -> slack; news -> calendar;
          jobs    -> sheets;
          pricing -> slack; pricing -> calendar;
          digest  -> email; digest -> slack;
        }
        """,
        width="stretch",
    )


def _render_pipeline_steps() -> None:
    rows = "".join(
        f'<div class="argus-pipeline-row">'
        f'<div class="argus-step-index">{html.escape(idx)}</div>'
        f'<div><div class="argus-step-title">{html.escape(title)}</div>'
        f'<div class="argus-step-copy">{html.escape(copy)}</div></div>'
        f'<div class="argus-step-system">{html.escape(system)}</div>'
        f'</div>'
        for idx, title, copy, system in _PIPELINE_STEPS
    )
    st.markdown(
        f'<div class="argus-pipeline-container"><div class="argus-pipeline-line"></div>{rows}</div>',
        unsafe_allow_html=True,
    )


# ── Tab 3: Proof ─────────────────────────────────────────────────────────────

def render_proof(
    run_bounds: dict,
    runs_48h: list[dict],
    artifacts: pd.DataFrame,
    snapshots: pd.DataFrame,
    seen_summary: pd.DataFrame,
    decisions: list[dict],
    actions: list[dict],
    run_history: list[dict],
    error_logs: list[dict],
) -> None:
    _render_proof_cards(run_bounds, runs_48h, artifacts)

    render_section("Artifacts Created", "Every real output Argus produced — checked against the database.")
    st.dataframe(artifacts, width="stretch", hide_index=True)

    render_section("Runs in Last 48 Hours", "Scheduled executions recorded in Postgres.")
    runs_table = runs_since_table(runs_48h)
    if runs_table.empty:
        st.info("No runs in the last 48 hours.")
    else:
        st.dataframe(runs_table, width="stretch", hide_index=True)

    with st.expander("Deep dive — LLM decisions, actions, snapshots, run history, errors"):
        render_section("LLM Decisions")
        decisions_df = to_table(decisions)
        if decisions_df.empty:
            st.info("No LLM decisions recorded yet.")
        else:
            st.dataframe(decisions_df, width="stretch", hide_index=True)

        render_section("External Actions")
        actions_df = to_table(actions)
        if actions_df.empty:
            st.info("No actions recorded yet.")
        else:
            st.dataframe(actions_df, width="stretch", hide_index=True)

        render_section("Pricing Snapshots")
        snapshot_table = page_snapshots_table(snapshots)
        if snapshot_table.empty:
            st.info("No pricing snapshots stored yet.")
        else:
            st.dataframe(snapshot_table, width="stretch", hide_index=True)

        render_section("Seen Item Dedup")
        seen_table = seen_summary_table(seen_summary)
        if seen_table.empty:
            st.info("No seen items stored yet.")
        else:
            st.dataframe(seen_table, width="stretch", hide_index=True)

        render_section("Run History")
        _render_run_history(run_history)

        render_section("Errors (last 24h)")
        _render_errors(error_logs)


def _render_proof_cards(run_bounds: dict, runs_48h: list[dict], artifacts: pd.DataFrame) -> None:
    cards = [
        ("Scheduler running for", f"{run_bounds['span_hours']:.0f}h", "hours of logged runs",  "accent-teal"),
        ("Runs in last 48h",      format_number(len(runs_48h)),        "scheduled executions",  "accent-navy"),
        ("Artifacts observed",    format_number(int((artifacts["status"] == "Observed").sum())), "real outputs created", "accent-amber"),
        ("Audit tables",          "3",                                  "run_log · seen_items · snapshots", "accent-blue"),
    ]
    body = "".join(
        f'<div class="argus-proof {accent}">'
        f'<div class="argus-proof-label">{html.escape(label)}</div>'
        f'<div class="argus-proof-value">{html.escape(value)}</div>'
        f'<div class="argus-proof-note">{html.escape(note)}</div>'
        f'</div>'
        for label, value, note, accent in cards
    )
    st.markdown(f'<div class="argus-demo-strip">{body}</div>', unsafe_allow_html=True)

    if run_bounds["span_hours"] >= 48:
        st.success(f"48h requirement met — {format_dt_israel(run_bounds['first_run'])} → {format_dt_israel(run_bounds['last_run'])}.")
    elif run_bounds["total_runs"]:
        st.warning(f"Run log spans {run_bounds['span_hours']:.1f}h so far. Need 48h for full evidence.")
    else:
        st.info("No runs recorded yet. Let GitHub Actions cron fire at least once.")


def _render_run_history(runs: list[dict]) -> None:
    if not runs:
        st.info("No runs recorded yet.")
        return
    for run in runs:
        label = (
            f"{run['workflow']} — {format_dt(run['trigger_time'])} — "
            f"{run['items_processed']} items · {len(run['decisions'])} decisions · "
            f"{len(run['actions'])} actions · {len(run['errors'])} errors"
        )
        with st.expander(label):
            st.dataframe(to_table(run["decisions"]), width="stretch", hide_index=True)
            st.dataframe(to_table(run["actions"]),   width="stretch", hide_index=True)
            for err in run["errors"]:
                st.error(err.get("error", "Unknown error"))
                if err.get("traceback"):
                    st.code(err["traceback"], language="python")


def _render_errors(error_logs: list[dict]) -> None:
    has_errors = False
    for log in error_logs:
        errors = _json_array(log["errors"])
        if not errors:
            continue
        has_errors = True
        with st.expander(f"{log['workflow']} — {format_dt(log['trigger_time'])} — {len(errors)} error(s)"):
            for err in errors:
                st.error(err.get("error", "Unknown error"))
                if err.get("traceback"):
                    st.code(err["traceback"], language="python")
    if not has_errors:
        st.success("No errors in the last 24 hours.")

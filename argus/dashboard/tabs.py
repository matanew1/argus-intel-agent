"""Tab renderers: Command Center, Flow, and Evidence."""
import html
from collections import Counter

import pandas as pd
import streamlit as st

from argus.dashboard.components import render_section
from argus.dashboard.data import (
    ISRAEL_TZ,
    _json_array,
    format_dt,
    format_dt_israel,
    format_number,
    page_snapshots_table,
    recent_runs_table,
    runs_since_table,
    seen_summary_table,
    summary_table,
    to_table,
)

_ACTION_COLORS = ["#2563eb", "#0d9488", "#d97706", "#7c3aed", "#dc2626", "#475569"]

_PIPELINE_STEPS = [
    ("01", "Scheduler fires",   "GitHub Actions cron starts a workflow on its configured cadence.",       "GitHub Actions"),
    ("02", "Config loads",      "ConfigLoader reads competitors, criteria, and notification targets.",     "config.yaml"),
    ("03", "Signals collected", "The workflow fetches news, jobs, pricing pages, or prior run logs.",      "Integrations"),
    ("04", "State checked",     "Seen items dedup articles/jobs; page snapshots detect pricing changes.",  "Postgres"),
    ("05", "LLM classifies",    "Mistral returns a structured label with reasoning.",                      "Mistral"),
    ("06", "Decision logged",   "The label and reasoning are appended to run_log.decisions.",              "run_log"),
    ("07", "Action dispatched", "Actionable signals create Slack, Calendar, Sheets, or email artifacts.", "External apps"),
    ("08", "Proof surfaces",    "Dashboard reads run_log, seen_items, and page_snapshots.",                "Streamlit"),
]


# ── Command Center ──────────────────────────────────────────────────────────

def render_command_center(
    summary_df: pd.DataFrame,
    recent_runs: pd.DataFrame,
    runs_48h: list[dict],
    actions_30d: list[dict],
) -> None:
    left, right = st.columns([1.12, 0.88])
    with left:
        render_section("Run Volume", "Total executions recorded per workflow.")
        if summary_df.empty:
            st.info("No workflow runs recorded yet.")
        else:
            chart_df = summary_df[["workflow", "total_runs"]].copy()
            chart_df["total_runs"] = chart_df["total_runs"].fillna(0).astype(int)
            st.bar_chart(chart_df.sort_values("total_runs", ascending=False), x="workflow", y="total_runs", height=285, width="stretch")
    with right:
        _render_action_donut(actions_30d)

    render_section("Workflow Summary", "Last observed run and cumulative totals.")
    if summary_df.empty:
        st.info("No workflow runs recorded yet.")
    else:
        st.dataframe(summary_table(summary_df), width="stretch", hide_index=True)


def _render_action_donut(actions_30d: list[dict]) -> None:
    counts = Counter(row["action"] or "unknown" for row in actions_30d)
    if not counts:
        st.markdown('<div class="argus-empty-state">No external actions recorded yet</div>', unsafe_allow_html=True)
        return
    top = counts.most_common(5)
    other = sum(counts.values()) - sum(c for _, c in top)
    if other:
        top.append(("other", other))
    total = sum(c for _, c in top)
    start, segments, legend_rows = 0.0, [], []
    for i, (name, count) in enumerate(top):
        color = _ACTION_COLORS[i % len(_ACTION_COLORS)]
        end = start + (count / total * 100)
        segments.append(f"{color} {start:.2f}% {end:.2f}%")
        legend_rows.append(
            f'<div class="argus-legend-row">'
            f'<span class="argus-legend-swatch" style="background:{color};"></span>'
            f'<span>{html.escape(name)}</span>'
            f'<span class="argus-legend-count">{format_number(count)}</span>'
            f'</div>'
        )
        start = end
    st.markdown(
        f'<div class="argus-chart-panel">'
        f'<div class="argus-chart-title">Action Breakdown</div>'
        f'<div class="argus-chart-caption">External artifacts by type, last 30 days.</div>'
        f'<div class="argus-donut-layout">'
        f'<div class="argus-donut" style="background:conic-gradient({", ".join(segments)});">'
        f'<div class="argus-donut-center"><strong>{format_number(total)}</strong><span>actions</span></div>'
        f'</div>'
        f'<div class="argus-legend">{"".join(legend_rows)}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ── Flow ─────────────────────────────────────────────────────────────────────

def render_flow(scheduler_df: pd.DataFrame) -> None:
    render_section("Pipeline Steps", "The same control path every scheduled workflow follows.")
    _render_pipeline_steps()

    render_section("Architecture", "Scheduler, workflows, classifier, database, and artifact outputs.")
    _render_architecture()

    render_section("Scheduler Proof", "Cron definitions read from the repository workflow files.")
    st.dataframe(scheduler_df, width="stretch", hide_index=True)


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


def _render_architecture() -> None:
    st.graphviz_chart(
        """
        digraph {
          graph [rankdir=LR, bgcolor="transparent", pad="0.2", nodesep="0.55", ranksep="0.65"];
          node [shape=box, style="rounded,filled", color="#B9C3D3", fillcolor="#FFFFFF", fontname="Helvetica", fontsize=11, fontcolor="#172033"];
          edge [color="#526174", arrowsize=0.8];

          config    [label="config.yaml"];
          scheduler [label="GitHub Actions cron", fillcolor="#EFF6FF", color="#93C5FD"];
          news      [label="News Watch"];
          jobs      [label="Job Watch"];
          pricing   [label="Pricing Watch"];
          digest    [label="Weekly Digest"];
          llm       [label="Mistral classifiers", fillcolor="#ECFDF5", color="#99F6E4"];
          db        [label="Postgres\\nrun_log, seen_items, snapshots", fillcolor="#F8FAFC", color="#94A3B8"];
          slack     [label="Slack",          fillcolor="#FFF7ED", color="#FDBA74"];
          calendar  [label="Google Calendar",fillcolor="#F0FDFA", color="#5EEAD4"];
          sheets    [label="Google Sheets",  fillcolor="#F7FEE7", color="#BEF264"];
          email     [label="Resend Email",   fillcolor="#FEF2F2", color="#FCA5A5"];

          config -> news; config -> jobs; config -> pricing; config -> digest;
          scheduler -> news; scheduler -> jobs; scheduler -> pricing; scheduler -> digest;
          news -> llm; jobs -> llm; pricing -> llm; digest -> llm;
          llm -> db;
          news -> slack; news -> calendar;
          jobs -> sheets;
          pricing -> slack; pricing -> calendar;
          digest -> email; digest -> slack;
        }
        """,
        width="stretch",
    )


# ── Evidence ─────────────────────────────────────────────────────────────────

def render_evidence(
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

    render_section("Real Artifacts", "What Argus created — Slack, Calendar, Sheets, email, dedup, and snapshots.")
    st.dataframe(artifacts, width="stretch", hide_index=True)

    render_section("Last 48 Hours", "Workflow executions from Postgres.")
    runs_table = runs_since_table(runs_48h)
    if runs_table.empty:
        st.info("No runs in the last 48 hours.")
    else:
        st.dataframe(runs_table, width="stretch", hide_index=True)

    with st.expander("LLM decisions"):
        decisions_df = to_table(decisions)
        if decisions_df.empty:
            st.info("No LLM decisions recorded yet.")
        else:
            st.dataframe(decisions_df, width="stretch", hide_index=True)

    with st.expander("Full audit trail — actions, snapshots, seen items, run history, errors"):
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

        render_section("Seen Item Summary")
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
        ("Run-log span", f"{run_bounds['span_hours']:.1f}h",                                    "database evidence",         "accent-teal"),
        ("Runs in 48h",  format_number(len(runs_48h)),                                          "recent executions",         "accent-navy"),
        ("Artifacts",    format_number(int((artifacts["status"] == "Observed").sum())),          "observed outputs",          "accent-amber"),
        ("Audit tables", format_number(3),                                                       "run_log, seen_items, snaps","accent-blue"),
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
        st.success(f"48h evidence present: {format_dt_israel(run_bounds['first_run'])} → {format_dt_israel(run_bounds['last_run'])}.")
    elif run_bounds["total_runs"]:
        st.warning(f"Run log spans {run_bounds['span_hours']:.1f}h. Keep scheduled runs enabled until this reaches 48h.")
    else:
        st.info("No run-log evidence yet. Let GitHub Actions cron fire at least once.")


def _render_run_history(runs: list[dict]) -> None:
    if not runs:
        st.info("No runs recorded yet.")
        return
    for run in runs:
        title = (
            f"{run['workflow']} — {format_dt(run['trigger_time'])} — "
            f"{run['items_processed']} item(s), {len(run['decisions'])} decision(s), "
            f"{len(run['actions'])} action(s), {len(run['errors'])} error(s)"
        )
        with st.expander(title):
            render_section("Decisions")
            st.dataframe(to_table(run["decisions"]), width="stretch", hide_index=True)
            render_section("Actions")
            st.dataframe(to_table(run["actions"]), width="stretch", hide_index=True)
            if run["errors"]:
                render_section("Errors")
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

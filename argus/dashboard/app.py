"""Argus dashboard — entry point."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import streamlit as st

from argus.dashboard.data import (
    PAGE_ICON,
    artifact_rows,
    dashboard_totals,
    load_actions_since,
    load_error_logs,
    load_error_rate,
    load_page_snapshots,
    load_recent_actions,
    load_recent_decisions,
    load_run_bounds,
    load_run_history,
    load_run_summary,
    load_runs_since,
    load_scheduler_manifest,
    load_seen_summary,
    status_profile,
)
from argus.dashboard.styles import render_styles
from argus.dashboard.components import render_header, render_metrics, render_status
from argus.dashboard.tabs import render_how_it_works, render_overview, render_proof

st.set_page_config(page_title="Argus", layout="wide", page_icon=PAGE_ICON)
render_styles()

# Splash screen while data loads
splash = st.empty()
with splash.container():
    st.markdown(
        """
        <div class="argus-splash-container">
            <div class="argus-splash-card">
                <div class="argus-splash-spinner"></div>
                <div class="argus-splash-text">Loading Argus Intelligence</div>
                <div class="argus-splash-subtext">Preparing scheduler proof, run logs, decisions, and artifacts.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Load all data
error_rate   = load_error_rate()
summary_df   = load_run_summary()
actions      = load_recent_actions(20)
actions_30d  = load_actions_since(30)
decisions    = load_recent_decisions(40)
run_history  = load_run_history(20)
error_logs   = load_error_logs()
runs_48h     = load_runs_since(48)
run_bounds   = load_run_bounds()
seen_summary = load_seen_summary()
snapshots    = load_page_snapshots()
scheduler_df = load_scheduler_manifest()
artifacts    = artifact_rows(actions_30d, snapshots, seen_summary)
profile      = status_profile(error_rate)
totals       = dashboard_totals(summary_df, actions, pd.DataFrame(), error_rate)

splash.empty()

# Render
render_header(profile)
render_status(profile)
render_metrics(totals, error_rate)

overview_tab, how_tab, proof_tab = st.tabs(["Overview", "How It Works", "Proof"])

with overview_tab:
    render_overview(summary_df, actions_30d)

with how_tab:
    render_how_it_works(scheduler_df)

with proof_tab:
    render_proof(run_bounds, runs_48h, artifacts, snapshots, seen_summary, decisions, actions, run_history, error_logs)

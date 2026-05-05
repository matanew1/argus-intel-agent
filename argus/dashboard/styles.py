"""Dashboard CSS theme."""
import streamlit as st


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
            background: var(--argus-bg); color: var(--argus-text); font-family: 'Inter', sans-serif;
        }
        [data-testid="stHeader"] {
            background: rgba(248,250,252,0.85); backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--argus-border);
        }
        .block-container { max-width: 1280px; padding-top: 2rem; padding-bottom: 4rem; }
        h1, h2, h3 { color: var(--argus-text); letter-spacing: -0.02em; }
        h1 { font-size: 2.25rem; font-weight: 800; line-height: 1.1; margin: 0; }
        h2 { font-size: 1.25rem; font-weight: 700; margin-top: 1.5rem; }

        /* Splash */
        .argus-splash-container {
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; height: 60vh; animation: fadeIn 0.3s ease-in;
        }
        .argus-splash-card {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            min-width: 320px; padding: 2rem 2.25rem; border: 1px solid var(--argus-border);
            border-radius: 1rem; background: var(--argus-panel); box-shadow: 0 24px 60px rgba(18,36,58,0.10);
        }
        .argus-splash-spinner {
            width: 48px; height: 48px; border: 4px solid var(--argus-panel-soft);
            border-top: 4px solid var(--argus-blue); border-radius: 50%;
            animation: spin 1s linear infinite; margin-bottom: 1.5rem;
        }
        .argus-splash-text { font-size: 1.1rem; font-weight: 600; color: var(--argus-navy); letter-spacing: -0.01em; }
        .argus-splash-subtext { margin-top: 0.4rem; color: var(--argus-muted); font-size: 0.88rem; font-weight: 500; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes fadeIn { 0% { opacity: 0; } 100% { opacity: 1; } }

        /* Header */
        .argus-header {
            display: flex; align-items: center; justify-content: space-between;
            gap: 1.25rem; padding: 1rem 0 1.5rem;
            border-bottom: 1px solid var(--argus-border); margin-bottom: 1.5rem;
        }
        .argus-brand { display: flex; align-items: center; gap: 1.25rem; min-width: 0; }
        .argus-logo img { width: 230px; max-width: 28vw; height: auto; display: block; }
        .argus-eyebrow {
            font-size: 0.75rem; font-weight: 700; color: var(--argus-teal);
            letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.3rem;
        }

        /* Status dot */
        .argus-dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; background: var(--argus-muted); }
        .argus-dot.success { background: var(--argus-green); box-shadow: 0 0 0 4px rgba(22,163,74,0.15); animation: pulse-green 2s infinite; }
        .argus-dot.warning { background: var(--argus-amber); }
        .argus-dot.error   { background: var(--argus-red); }
        @keyframes pulse-green {
            0%   { box-shadow: 0 0 0 0 rgba(22,163,74,0.4); }
            70%  { box-shadow: 0 0 0 6px rgba(22,163,74,0); }
            100% { box-shadow: 0 0 0 0 rgba(22,163,74,0); }
        }

        /* KPI cards */
        .argus-kpi-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1rem; margin: 1rem 0 2rem; }
        .argus-kpi {
            background: var(--argus-panel); border: 1px solid var(--argus-border);
            border-radius: 0.75rem; padding: 1.25rem;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .argus-kpi:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); }
        .argus-kpi-label { color: var(--argus-muted); font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
        .argus-kpi-value { color: var(--argus-text); font-size: 2rem; font-weight: 800; line-height: 1.1; margin-top: 0.5rem; }
        .argus-kpi-note  { color: var(--argus-muted); font-size: 0.85rem; margin-top: 0.5rem; font-weight: 500; }
        .argus-kpi.accent-blue  { border-bottom: 4px solid var(--argus-blue); }
        .argus-kpi.accent-teal  { border-bottom: 4px solid var(--argus-teal); }
        .argus-kpi.accent-amber { border-bottom: 4px solid var(--argus-amber); }
        .argus-kpi.accent-navy  { border-bottom: 4px solid var(--argus-navy); }
        .argus-kpi.accent-red   { border-bottom: 4px solid var(--argus-red); }

        /* Pipeline steps */
        .argus-pipeline-container { position: relative; margin: 1.5rem 0 2rem; padding: 0 0.5rem; }
        .argus-pipeline-line {
            position: absolute; top: 2rem; bottom: 2rem; left: 2.15rem;
            width: 2px; background: var(--argus-border); z-index: 0;
        }
        .argus-pipeline-row {
            position: relative; z-index: 1;
            display: grid; grid-template-columns: 3.5rem minmax(0, 1fr) auto;
            align-items: center; gap: 1rem;
            background: var(--argus-panel); border: 1px solid var(--argus-border);
            border-radius: 0.75rem; padding: 1rem; margin-bottom: 0.75rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05); transition: border-color 0.2s ease;
        }
        .argus-pipeline-row:hover { border-color: var(--argus-blue); }
        .argus-step-index {
            display: flex; align-items: center; justify-content: center;
            width: 2.5rem; height: 2.5rem; border-radius: 50%;
            background: #eff6ff; color: var(--argus-blue); font-weight: 800; font-size: 0.9rem;
            border: 4px solid var(--argus-bg);
        }
        .argus-step-title { color: var(--argus-text); font-size: 1rem; font-weight: 700; margin-bottom: 0.2rem; }
        .argus-step-copy  { color: var(--argus-muted); font-size: 0.9rem; line-height: 1.4; font-weight: 500; }
        .argus-step-system {
            justify-self: end; border: 1px solid var(--argus-border); border-radius: 999px;
            color: var(--argus-navy); background: var(--argus-panel-soft);
            padding: 0.35rem 0.75rem; font-size: 0.8rem; font-weight: 600;
        }

        /* Status banner */
        .argus-status {
            display: flex; gap: 0.8rem; align-items: flex-start;
            padding: 0.9rem 1rem; border: 1px solid var(--argus-border); border-left-width: 4px;
            border-radius: 0.7rem; background: var(--argus-panel);
            box-shadow: 0 6px 18px rgba(18,36,58,0.05); margin: 0.75rem 0 1rem;
        }
        .argus-status.success { border-left-color: var(--argus-green); }
        .argus-status.warning { border-left-color: var(--argus-amber); }
        .argus-status.error   { border-left-color: var(--argus-red); }
        .argus-status.info    { border-left-color: var(--argus-blue); }
        .argus-status-title { font-weight: 750; color: var(--argus-text); margin-bottom: 0.15rem; }
        .argus-status-body  { color: var(--argus-muted); font-size: 0.93rem; }

        /* Section titles */
        .argus-section-title   { color: var(--argus-text); font-size: 1.05rem; font-weight: 760; margin: 1.25rem 0 0.45rem; }
        .argus-section-caption { color: var(--argus-muted); font-size: 0.9rem; margin: -0.15rem 0 0.7rem; }

        /* Demo proof strip */
        .argus-demo-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.85rem; margin: 0.6rem 0 1.15rem; }
        .argus-proof {
            background: var(--argus-panel); border: 1px solid var(--argus-border);
            border-radius: 0.75rem; padding: 0.85rem 0.95rem; box-shadow: 0 7px 20px rgba(18,36,58,0.05);
        }
        .argus-proof.accent-blue  { border-top: 3px solid var(--argus-blue); }
        .argus-proof.accent-teal  { border-top: 3px solid var(--argus-teal); }
        .argus-proof.accent-amber { border-top: 3px solid var(--argus-amber); }
        .argus-proof.accent-navy  { border-top: 3px solid var(--argus-navy); }
        .argus-proof-label { color: var(--argus-muted); font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
        .argus-proof-value { color: var(--argus-text); font-size: 1.45rem; font-weight: 760; margin-top: 0.45rem; }
        .argus-proof-note  { color: var(--argus-muted); font-size: 0.78rem; margin-top: 0.35rem; }

        /* Header clocks */
        .argus-header-meta { display: flex; align-items: flex-end; flex-direction: column; gap: 0.4rem; white-space: nowrap; }
        .argus-clock-grid  { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.55rem; margin-top: 0.1rem; }
        .argus-clock {
            min-width: 10.5rem; padding: 0.55rem 0.68rem;
            border: 1px solid var(--argus-border); border-radius: 0.7rem;
            background: var(--argus-panel); box-shadow: 0 6px 18px rgba(18,36,58,0.04);
        }
        .argus-clock span   { display: block; color: var(--argus-muted); font-size: 0.68rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; }
        .argus-clock strong { display: block; margin-top: 0.2rem; color: var(--argus-text); font-size: 0.84rem; font-weight: 760; }
        .argus-pill {
            display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.38rem 0.62rem;
            border: 1px solid var(--argus-border); border-radius: 999px;
            background: var(--argus-panel); color: var(--argus-text); font-size: 0.82rem; font-weight: 650;
        }

        /* Donut chart */
        .argus-chart-panel {
            min-height: 18.5rem; background: var(--argus-panel); border: 1px solid var(--argus-border);
            border-radius: 0.75rem; padding: 1rem; box-shadow: 0 7px 20px rgba(18,36,58,0.04);
        }
        .argus-chart-title   { color: var(--argus-text); font-size: 0.95rem; font-weight: 780; margin-bottom: 0.18rem; }
        .argus-chart-caption { color: var(--argus-muted); font-size: 0.82rem; font-weight: 500; margin-bottom: 0.85rem; }
        .argus-donut-layout  { display: grid; grid-template-columns: 11.5rem minmax(0, 1fr); gap: 1rem; align-items: center; min-height: 13rem; }
        .argus-donut {
            position: relative; width: 11rem; height: 11rem; border-radius: 50%;
            box-shadow: inset 0 0 0 1px rgba(15,23,42,0.08), 0 10px 22px rgba(18,36,58,0.08);
        }
        .argus-donut::after {
            content: ""; position: absolute; inset: 2.5rem; border-radius: 50%;
            background: var(--argus-panel); box-shadow: inset 0 0 0 1px var(--argus-border);
        }
        .argus-donut-center {
            position: absolute; inset: 0; z-index: 1;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            text-align: center; pointer-events: none;
        }
        .argus-donut-center strong { color: var(--argus-text); font-size: 1.45rem; font-weight: 800; line-height: 1; }
        .argus-donut-center span   { color: var(--argus-muted); font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.22rem; }
        .argus-legend       { display: grid; gap: 0.48rem; }
        .argus-legend-row   { display: grid; grid-template-columns: 0.8rem minmax(0, 1fr) auto; align-items: center; gap: 0.48rem; color: var(--argus-text); font-size: 0.84rem; font-weight: 620; }
        .argus-legend-swatch { width: 0.7rem; height: 0.7rem; border-radius: 50%; }
        .argus-legend-count  { color: var(--argus-muted); font-weight: 760; }

        /* Empty state */
        .argus-empty-state {
            display: flex; align-items: center; justify-content: center; min-height: 13rem;
            border: 1px dashed var(--argus-border-strong); border-radius: 0.7rem;
            color: var(--argus-muted); font-weight: 650; background: var(--argus-panel-soft);
        }

        /* Streamlit overrides */
        .stTabs [data-baseweb="tab-list"] { gap: 0.35rem; border-bottom: 1px solid var(--argus-border); }
        .stTabs [data-baseweb="tab"] { border-radius: 0.5rem 0.5rem 0 0; padding: 0.55rem 0.9rem; color: var(--argus-muted); font-weight: 650; }
        .stTabs [aria-selected="true"] { background: var(--argus-panel); color: var(--argus-text); border: 1px solid var(--argus-border); border-bottom-color: var(--argus-panel); }
        div[data-testid="stDataFrame"] { border: 1px solid var(--argus-border); border-radius: 0.75rem; overflow: hidden; box-shadow: 0 7px 20px rgba(18,36,58,0.04); }
        div[data-testid="stExpander"]  { border: 1px solid var(--argus-border); border-radius: 0.75rem; background: var(--argus-panel); box-shadow: 0 7px 20px rgba(18,36,58,0.04); }
        div[data-testid="stAlert"] { border-radius: 0.7rem; border: 1px solid var(--argus-border); }
        div[data-testid="stAlert"] * { color: var(--argus-text); }
        div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p { color: var(--argus-text); font-weight: 650; }
        div[data-testid="stSpinner"] { display: none; }

        /* Responsive */
        @media (max-width: 900px) {
            .argus-header, .argus-header-meta { flex-direction: column; align-items: flex-start; }
            .argus-clock-grid { grid-template-columns: 1fr; }
            .argus-kpi-grid, .argus-demo-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 560px) {
            .argus-logo img { width: 168px; max-width: 58vw; }
            .argus-donut-layout, .argus-kpi-grid, .argus-demo-strip { grid-template-columns: 1fr; }
            .argus-pipeline-row { grid-template-columns: 2.8rem minmax(0, 1fr); }
            .argus-step-system  { grid-column: 2; justify-self: start; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

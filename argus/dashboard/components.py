"""Reusable UI components: header, status banner, metrics, section titles."""
import html
from datetime import datetime, timezone

import streamlit as st

from argus.dashboard.data import (
    ISRAEL_TZ,
    LOGO_PATH,
    format_dt_israel,
    format_number,
    logo_data_uri,
)


def render_section(title: str, caption: str = "") -> None:
    caption_markup = f'<div class="argus-section-caption">{html.escape(caption)}</div>' if caption else ""
    st.markdown(
        f'<div class="argus-section-title">{html.escape(title)}</div>{caption_markup}',
        unsafe_allow_html=True,
    )


def render_status(profile: dict) -> None:
    level = html.escape(profile["level"])
    label = html.escape(profile["label"])
    message = html.escape(profile["message"])
    st.markdown(
        f'<div class="argus-status {level}">'
        f'<span class="argus-dot {level}"></span>'
        f'<div><div class="argus-status-title">{label}</div>'
        f'<div class="argus-status-body">{message}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_header(profile: dict) -> None:
    logo = logo_data_uri(str(LOGO_PATH))
    level = html.escape(profile["level"])
    label = html.escape(profile["label"])
    now_utc = datetime.now(timezone.utc)
    generated_at = html.escape(now_utc.strftime("%Y-%m-%d %H:%M UTC"))
    israel_at = html.escape(now_utc.astimezone(ISRAEL_TZ).strftime("%Y-%m-%d %H:%M %Z"))
    logo_markup = f'<img src="{logo}" alt="Argus logo">' if logo else "<strong>A</strong>"
    st.markdown(
        f'<div class="argus-header">'
        f'<div class="argus-brand">'
        f'<div class="argus-logo">{logo_markup}</div>'
        f'<div><div class="argus-eyebrow">Competitive intelligence operations</div></div>'
        f'</div>'
        f'<div class="argus-header-meta">'
        f'<div class="argus-pill"><span class="argus-dot {level}"></span>{label}</div>'
        f'<div class="argus-clock-grid">'
        f'<div class="argus-clock"><span>Israel time</span><strong>{israel_at}</strong></div>'
        f'<div class="argus-clock"><span>UTC</span><strong>{generated_at}</strong></div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_metrics(totals: dict, error_rate: dict) -> None:
    cards = [
        ("Health",     f"{totals['score']}%",                  "24h signal quality",      "accent-teal"),
        ("Workflows",  format_number(totals["workflow_count"]), "active audit streams",    "accent-navy"),
        ("Total runs", format_number(totals["run_count"]),      "recorded executions",     "accent-blue"),
        ("Actions",    format_number(totals["action_count"]),   "latest artifact feed",    "accent-amber"),
        ("24h errors", format_number(error_rate["errored"]),    f"{error_rate['rate']:.1f}% error rate", "accent-red"),
    ]
    body = "".join(
        f'<div class="argus-kpi {accent}">'
        f'<div class="argus-kpi-label">{html.escape(label)}</div>'
        f'<div class="argus-kpi-value">{html.escape(value)}</div>'
        f'<div class="argus-kpi-note">{html.escape(note)}</div>'
        f'</div>'
        for label, value, note, accent in cards
    )
    st.markdown(f'<div class="argus-kpi-grid">{body}</div>', unsafe_allow_html=True)

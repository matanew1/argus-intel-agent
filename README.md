# Argus Intel Agent

An always-on competitive intelligence agent that watches competitor companies and acts autonomously — no human prompts, ever.

## What It Does

| Workflow | Schedule | Action |
|---|---|---|
| **News Watch** | Every 2 hours UTC | Classifies news → Calendar event (funding/launch) or Slack alert (controversy) |
| **Job Watch** | Daily 9am UTC | Clusters new roles → Google Sheet row for non-routine signals |
| **Pricing Watch** | Daily 8am UTC | Diffs competitor pages → Slack DM + Calendar event for material changes |
| **Weekly Digest** | Friday 4pm UTC | Synthesizes week's signals → Email + Slack TL;DR |

All decisions are LLM-driven (Mistral AI). Zero regex. Every classification and its reasoning is logged to Postgres before any action is taken.

---

## Architecture

```
config.yaml ──► ConfigLoader ──► Workflows ──► Classifiers (Mistral AI)
                                     │                │
                                     ▼                ▼
                              Neon Postgres      Integrations
                         (seen_items, run_log,   (Slack, Calendar,
                          config, page_snapshots)  Sheets, Resend)
                                     │
                                     ▼
                            GitHub Actions (cron scheduler)
                                     │
                                     ▼
                            Streamlit Dashboard (localhost:8501)
```

---

## Project Structure

```
argus/
├── core/           # database, models, config_loader, dedup, logger
├── classifiers/    # one LLM classifier per decision type (news, jobs, diff, digest)
├── integrations/   # Slack, Google Calendar/Sheets, NewsAPI, Resend, scraper, google_auth
├── workflows/      # 4 workflows + BaseWorkflow template
└── dashboard/      # Streamlit status UI

.github/workflows/  # 5 cron triggers (news, jobs, pricing, digest, cleanup)
config.yaml         # single source of truth — competitors, criteria, notification IDs
.env                # secrets (never committed)
```

---

## Prerequisites

- Python 3.11+
- [Neon](https://neon.tech) free account (Postgres)
- [Mistral AI](https://mistral.ai) API key
- [NewsAPI](https://newsapi.org) key (free: 100 req/day)
- Slack app with `chat:write` + `im:write` scopes
- [Resend](https://resend.com) account (free: 3,000 emails/month)
- Google Cloud service account with Calendar + Sheets APIs enabled

See [docs/api_setup.md](docs/api_setup.md) for full setup instructions for each service.

---

## Quickstart

### 1. Clone & configure

```bash
git clone https://github.com/matanew1/argus-intel-agent.git
cd argus-intel-agent
cp .env.example .env
# Fill in your API keys in .env
```

Edit `config.yaml` to set your competitors, criteria, and notification IDs (Slack channel, calendar ID, sheet ID).

### 2. Create database tables

```bash
pip install -r requirements.txt
python -c "from argus.core.database import init_db; init_db(); print('Tables created')"
```

### 3. Run locally (dry run — no real API writes)

```bash
DRY_RUN=true python -m argus.workflows.news_watch
DRY_RUN=true python -m argus.workflows.job_watch
DRY_RUN=true python -m argus.workflows.pricing_watch
DRY_RUN=true python -m argus.workflows.weekly_digest
```

### 4. Run the dashboard

```bash
streamlit run argus/dashboard/app.py
# Open http://localhost:8501
```

### 5. Deploy to GitHub Actions

1. Push this repo to GitHub
2. Add all secrets at **Settings → Secrets and variables → Actions**:

| Secret | Description |
|---|---|
| `DATABASE_URL` | Neon connection string (`postgresql://...?sslmode=require`) |
| `MISTRAL_API_KEY` | Mistral API key |
| `NEWSAPI_KEY` | NewsAPI key |
| `SLACK_BOT_TOKEN` | `xoxb-...` bot token |
| `RESEND_API_KEY` | Resend API key |
| `RESEND_FROM_EMAIL` | Verified sender address (or `onboarding@resend.dev` for testing) |
| `GOOGLE_CREDENTIALS_JSON` | Full JSON content of service account key |
| `CALENDAR_ID` | Your Google Calendar ID (usually your Gmail address) |
| `GOOGLE_SHEET_ID` | Spreadsheet ID from its URL |

3. Workflows fire automatically on schedule. Test manually via **Actions → [workflow] → Run workflow** with `dry_run: true` first.

### 6. Run tests

```bash
pytest tests/ -v
```

---

## Configuration

Edit `config.yaml` to:
- Add or remove competitors (name, news query, careers URL, optional LinkedIn RSS URL, pricing URLs)
- Update `what_i_care_about` criteria in plain English — passed to every LLM classifier
- Change notification IDs (Slack channel, calendar, sheet, digest email)

For job watch, set `linkedin_rss` to a feed URL when available. Leave it blank to fall back to scraping `careers_url`.

Changes are picked up on the next workflow run with no restart needed (ConfigLoader watches the file).

---

## Dashboard

```bash
streamlit run argus/dashboard/app.py
```

Three tabs:
- **Command Center** — run volume chart, action breakdown, workflow summary
- **Flow** — 8-step pipeline diagram, architecture graph, scheduler proof table
- **Evidence** — 48h proof cards, artifact checklist, LLM decisions, full audit trail

Dashboard code is split across `argus/dashboard/`: `app.py` (entry), `data.py` (DB queries), `components.py` (header/metrics), `tabs.py` (tab renderers), `styles.py` (CSS).

---

For full service setup instructions see [docs/api_setup.md](docs/api_setup.md).
For architecture details see [docs/architecture.md](docs/architecture.md).
For a full workflow deep dive and Loom demo guide see [docs/workflow_deep_dive_and_demo_guide.md](docs/workflow_deep_dive_and_demo_guide.md).

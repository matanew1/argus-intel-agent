# Argus Intel Agent

An always-on competitive intelligence agent that watches a list of competitor companies and acts autonomously — no human prompts, ever.

## What It Does

| Workflow | Schedule | Action |
|---|---|---|
| **News Watch** | Every 2 hours | Classifies news → Calendar event (funding/launch) or Slack alert (controversy) |
| **Job Posting Watch** | Daily 9am | Tags new roles → Google Sheet row for non-routine signals |
| **Pricing Watch** | Daily 8am | Diffs competitor pages → Slack DM + Calendar event for material changes |
| **Weekly Digest** | Friday 4pm | LLM synthesizes week's signals → Email + Slack TL;DR |

All decisions are LLM-driven (Mistral AI). Zero regex. Every decision's reasoning is logged.

## Architecture

```
config.yaml ──► ConfigLoader ──► Workflows ──► Judges (Mistral AI)
                                     │              │
                                     ▼              ▼
                              Neon Postgres     Integrations
                         (seen_items, run_log,  (Slack, Calendar,
                          config, page_snapshots) Sheets, Resend)
                                     │
                                     ▼
                            GitHub Actions (cron scheduler)
                                     │
                                     ▼
                            Streamlit Dashboard (localhost:8501)
```

## Prerequisites

- Python 3.11+
- [Neon](https://neon.tech) free account (Postgres DB)
- [Mistral AI](https://mistral.ai) API key (free tier)
- [NewsAPI](https://newsapi.org) key (free tier, 100 req/day)
- Slack app with `chat:write` + `im:write` scopes
- [Resend](https://resend.com) account + verified sender domain
- Google Cloud service account with Calendar + Sheets APIs enabled

## Quickstart

### 1. Clone & configure

```bash
git clone https://github.com/matanew1/argus-intel-agent.git
cd argus-intel-agent
cp .env.example .env
# Fill in your API keys in .env
```

Edit `config.yaml` to set your competitors, criteria, and notification IDs.

### 2. Set up Neon Postgres

1. Create a free project at [neon.tech](https://neon.tech)
2. Copy the connection string to `DATABASE_URL` in `.env`
3. Create tables:

```bash
pip install -r requirements.txt
python -c "from argus.core.database import init_db; init_db(); print('Tables created')"
```

### 3. Set up Google service account

See [docs/api_setup.md](docs/api_setup.md) for full step-by-step instructions. Summary:
1. GCP → enable Calendar API + Sheets API
2. Create Service Account → download JSON → save to `credentials/google_service_account.json`
3. Share your calendar and spreadsheet with the service account email

### 4. Run locally (dashboard)

```bash
docker-compose up          # starts local Postgres + Streamlit at localhost:8501
```

To test a workflow locally (dry run — no real API writes):

```bash
DATABASE_URL=postgresql://argus:argus@localhost:5432/argus \
  DRY_RUN=true \
  python -m argus.workflows.news_watch
```

### 5. Deploy scheduler to GitHub Actions

1. Push this repo to GitHub
2. Add all secrets at **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `DATABASE_URL` | Neon connection string (`postgresql://...?sslmode=require`) |
| `MISTRAL_API_KEY` | Mistral API key |
| `NEWSAPI_KEY` | NewsAPI key |
| `SLACK_BOT_TOKEN` | `xoxb-...` bot token |
| `RESEND_API_KEY` | Resend API key |
| `RESEND_FROM_EMAIL` | Verified sender address |
| `GOOGLE_CREDENTIALS_JSON` | Full JSON content of service account key file |
| `CALENDAR_ID` | `primary` or your calendar's ID |
| `GOOGLE_SHEET_ID` | Spreadsheet ID from its URL |
| `SLACK_CHANNEL_ID` | `#competitive-intel` channel ID |
| `SLACK_DM_USER_ID` | Your Slack user ID (for urgent pricing DMs) |

3. Enable Actions in the repo. Workflows fire automatically on schedule.
4. Test manually: **Actions → News Watch → Run workflow** (tick `dry_run`)

### 6. Run tests

```bash
pytest tests/ -v
```

## Dashboard

```bash
streamlit run argus/dashboard/app.py
# Open http://localhost:8501
```

Shows:
- System health (green/red)
- Last run per workflow with elapsed time
- Last 20 actions feed (`"10:00 AM: calendar_event → primary (created)"`)
- Error log with full tracebacks

## Project Structure

```
argus/
├── core/           # database, models, config_loader, dedup, logger
├── judges/         # one LLM judge module per decision type
├── integrations/   # Slack, Google Calendar/Sheets, NewsAPI, Resend, Scraper
├── workflows/      # 4 workflows + BaseWorkflow template
└── dashboard/      # Streamlit app (~120 lines)

.github/workflows/  # 4 cron triggers + weekly cleanup
config.yaml         # single source of truth — edit to tune the agent
```

## Customization

Edit `config.yaml` to add/remove competitors, update the `what_i_care_about` criteria (plain English), or change notification IDs. Changes are picked up on the next workflow run — no restart needed.

For more details see [docs/api_setup.md](docs/api_setup.md) and [docs/architecture.md](docs/architecture.md).

# API Setup Guide

Step-by-step instructions for setting up every external service Argus uses.

---

## 1. Neon Postgres (Database)

1. Go to [neon.tech](https://neon.tech) → **Sign up for free**
2. Create a new project (any name, e.g. `argus`)
3. From the project dashboard copy the **Connection string** — it looks like:
   `postgresql://user:pass@ep-xxx.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`
4. Paste it as `DATABASE_URL` in `.env` and as the `DATABASE_URL` GitHub Secret
5. Create tables:
   ```bash
   python -c "from argus.core.database import init_db; init_db(); print('Tables created')"
   ```

---

## 2. Mistral AI (LLM)

1. Go to [console.mistral.ai](https://console.mistral.ai) → **Sign in / Create account**
2. **API Keys** → **Create new key**
3. Copy the key → set as `MISTRAL_API_KEY` in `.env` and GitHub Secrets
4. Model used: `mistral-small-latest` (set in `config.yaml` under `llm.model`)

---

## 3. NewsAPI (News Feed)

1. Go to [newsapi.org](https://newsapi.org) → **Get API Key** (free)
2. Free plan: 100 requests/day — sufficient for 2 competitors checked every 2 hours
3. Copy the key → `NEWSAPI_KEY` in `.env` and GitHub Secrets

---

## 4. Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name it `Argus Intel`, select your workspace
3. **OAuth & Permissions** → **Bot Token Scopes** → add:
   - `chat:write` (post messages to channels)
   - `im:write` (send DMs)
   - `channels:read` (list channels)
4. **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-...`) → `SLACK_BOT_TOKEN` in `.env` and GitHub Secrets
5. In your target channel run `/invite @Argus Intel` to add the bot
6. Get your **channel ID**: right-click the channel name → **View channel details** → copy the ID (`C...`)
7. Get your **user ID**: click your profile picture → **Profile** → **⋮** → **Copy member ID** (`U...`)
8. Paste both into `config.yaml` under `notifications.slack_channel` and `notifications.slack_dm_user`

---

## 5. Google Service Account (Calendar + Sheets)

### Create the service account

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create or select a project
2. **APIs & Services** → **Enable APIs** → enable:
   - **Google Calendar API**
   - **Google Sheets API**
3. **APIs & Services** → **Credentials** → **Create Credentials** → **Service Account**
4. Give it a name (e.g. `argus-intel`) → **Create and Continue** → skip optional steps
5. Click the service account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
6. Download the JSON file → save to `credentials/google_service_account.json` for local dev
7. For GitHub Actions: copy the **full JSON content** as a single-line string → GitHub Secret `GOOGLE_CREDENTIALS_JSON`

### Share your Google Calendar

1. Open [Google Calendar](https://calendar.google.com) → find your calendar
2. **Settings** (⚙️) → **Settings for my calendars** → select the calendar → **Share with specific people**
3. Add the service account email (the `client_email` value from the JSON)
4. Permission: **Make changes to events**
5. Copy the **Calendar ID** from calendar settings → set as `CALENDAR_ID` in `.env`, GitHub Secrets, and `config.yaml`

### Create and share your Google Sheet

1. Go to [sheets.google.com](https://sheets.google.com) → **+ Blank** → rename to `Competitor Signals`
2. Add headers in row 1: `Detected At` | `Competitor` | `Label` | `Reasoning` | `Source URL`
3. Click **Share** → paste the service account email → **Editor** role → uncheck "Notify people" → **Share**
4. Copy the **Spreadsheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit`
5. Set as `GOOGLE_SHEET_ID` in `.env`, GitHub Secrets, and `config.yaml`

---

## 6. Resend (Email)

1. Go to [resend.com](https://resend.com) → **Sign up** (free: 3,000 emails/month)
2. **API Keys** → **Create API Key** → copy → `RESEND_API_KEY` in `.env` and GitHub Secrets
3. For `RESEND_FROM_EMAIL`:
   - **Quick start (no domain):** use `onboarding@resend.dev` — works immediately
   - **Custom domain:** **Domains** → **Add Domain** → verify DNS records → use `argus@yourdomain.com`
4. Set `RESEND_FROM_EMAIL` in `.env` and GitHub Secrets

---

## Environment Variables Summary

| Variable | Where to set | Source |
|---|---|---|
| `DATABASE_URL` | `.env` + GitHub Secret | Neon connection string |
| `MISTRAL_API_KEY` | `.env` + GitHub Secret | Mistral console |
| `NEWSAPI_KEY` | `.env` + GitHub Secret | newsapi.org dashboard |
| `SLACK_BOT_TOKEN` | `.env` + GitHub Secret | Slack app → OAuth & Permissions |
| `RESEND_API_KEY` | `.env` + GitHub Secret | Resend dashboard |
| `RESEND_FROM_EMAIL` | `.env` + GitHub Secret | Your verified email or `onboarding@resend.dev` |
| `GOOGLE_CREDENTIALS_JSON` | `.env` + GitHub Secret | Full JSON content of service account key |
| `CALENDAR_ID` | `.env` + GitHub Secret + `config.yaml` | Your Gmail address or specific calendar ID |
| `GOOGLE_SHEET_ID` | `.env` + GitHub Secret + `config.yaml` | From spreadsheet URL |

> `slack_channel` and `slack_dm_user` are set in `config.yaml`, not as environment variables.

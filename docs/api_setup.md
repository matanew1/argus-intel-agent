# API Setup Guide

Step-by-step instructions for setting up every external service Argus uses.

---

## 1. Neon Postgres (Database)

1. Go to [neon.tech](https://neon.tech) → **Sign up for free**
2. Create a new project (any name, e.g. `argus`)
3. From the project dashboard, copy the **Connection string** — it looks like:
   `postgresql://user:pass@ep-xxx-yyy.us-east-2.aws.neon.tech/argus?sslmode=require`
4. Paste it as `DATABASE_URL` in `.env` and as the `DATABASE_URL` GitHub Secret
5. Run `python -c "from argus.core.database import init_db; init_db()"` to create tables

---

## 2. Mistral AI (LLM)

1. Go to [console.mistral.ai](https://console.mistral.ai) → **Sign in / Create account**
2. Navigate to **API Keys** → **Create new key**
3. Copy the key → set as `MISTRAL_API_KEY` in `.env` and GitHub Secrets
4. Free tier: generous token allowance sufficient for this agent's usage

---

## 3. NewsAPI (News Feed)

1. Go to [newsapi.org](https://newsapi.org) → **Get API Key** (free)
2. Free plan: 100 requests/day (agent uses ~12/day for 1 competitor — scales to ~8 with free tier)
3. Copy the key → `NEWSAPI_KEY` in `.env` and GitHub Secrets

---

## 4. Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name it `Argus Intel`, select your workspace
3. **OAuth & Permissions** → **Bot Token Scopes** → add:
   - `chat:write` (post messages)
   - `im:write` (send DMs)
   - `channels:read` (list channels)
4. **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-...`) → `SLACK_BOT_TOKEN`
5. In the `#competitive-intel` channel, run `/invite @Argus Intel` to add the bot
6. Get the **channel ID**: right-click the channel name → **View channel details** → copy ID (`C...`)
7. Get your **user ID**: click your profile → **Profile** → the ID is in the URL or via the "..." menu

---

## 5. Google Service Account (Calendar + Sheets)

### Create the service account

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create or select a project
2. **APIs & Services** → **Enable APIs** → enable:
   - **Google Calendar API**
   - **Google Sheets API**
3. **APIs & Services** → **Credentials** → **Create Credentials** → **Service Account**
4. Give it a name (e.g. `argus-intel`), click **Create and Continue**, skip optional steps
5. Click the service account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
6. Download the JSON file → save to `credentials/google_service_account.json` locally
7. For GitHub Actions: copy the **full JSON content** (as a string) → GitHub Secret `GOOGLE_CREDENTIALS_JSON`

### Share your Google Calendar

1. Open [Google Calendar](https://calendar.google.com) → find the target calendar
2. **Settings** (⚙️) → **Settings for my calendars** → select the calendar → **Share with specific people**
3. Add the service account email (found in the JSON as `"client_email"`)
4. Permission: **Make changes to events**
5. Use `primary` as the calendar ID, or get the specific ID from calendar settings

### Share your Google Sheet

1. Open the Google Sheet (or create a new one titled "Competitor Signals")
2. Click **Share** → paste the service account email → **Editor** role
3. Copy the **Spreadsheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit`
4. Set as `GOOGLE_SHEET_ID` in `.env` and GitHub Secrets
5. Ensure the sheet has headers in row 1: `Detected At | Competitor | Label | Reasoning | Source URL`

---

## 6. Resend (Email)

1. Go to [resend.com](https://resend.com) → **Sign up** (free: 3,000 emails/month)
2. **Domains** → **Add domain** → verify DNS records for your domain
3. **API Keys** → **Create API Key** → copy → `RESEND_API_KEY`
4. Set `RESEND_FROM_EMAIL` to a verified address on your domain (e.g. `argus@yourdomain.com`)
5. Free tier limit: 3,000 emails/month. Agent sends 1 email/week → well within limits.

---

## Environment Variables Summary

| Variable | Source |
|---|---|
| `DATABASE_URL` | Neon connection string |
| `MISTRAL_API_KEY` | Mistral console |
| `NEWSAPI_KEY` | newsapi.org dashboard |
| `SLACK_BOT_TOKEN` | Slack app → OAuth & Permissions |
| `RESEND_API_KEY` | Resend dashboard |
| `RESEND_FROM_EMAIL` | Your verified domain email |
| `GOOGLE_CREDENTIALS_JSON` | Content of service account JSON |
| `CALENDAR_ID` | `primary` or specific calendar ID |
| `GOOGLE_SHEET_ID` | From spreadsheet URL |
| `SLACK_CHANNEL_ID` | Channel ID (`C...`) |
| `SLACK_DM_USER_ID` | Your Slack user ID (`U...`) |

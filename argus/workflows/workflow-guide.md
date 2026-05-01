# Workflow Verification Guide

## Workflow 1: News Watch

Dry run:

Actions -> News Watch -> Run workflow -> dry_run: true
Click the run -> open the job -> expand Run News Watch.

Check for:
- NewsAPI returned X articles.
- News classifier: <headline> -> funding/noise/etc.
- Noise or dry_run -> skipping action.
- News Watch done -> X items, 0 action(s).
- Nothing appears in Slack or Calendar.

Non-dry run:

Same steps, but set dry_run: false.

Check for:
- Slack: :green_circle: News Watch started.
- Logs show a Calendar event or Slack message if anything was classified as funding, product_launch, executive_change, or controversy.
- Slack: :white_check_mark: News Watch done -> X items, Y action(s).
- If any signal was found, Google Calendar has a new event tomorrow at 9am.

## Workflow 2: Job Watch

Dry run:

Actions -> Job Watch -> Run workflow -> dry_run: true

Check for:
- Scraped X job links from the configured careers URL.
- Jobs classifier: OpenAI -> building_ai_team / routine_backfill / etc.
- routine_backfill or dry_run -> skipping sheet write.
- Job Watch done -> X items, 0 action(s).
- No rows added to Google Sheet.

Non-dry run:

Same steps, but set dry_run: false.

Check for:
- If label is not routine_backfill, Google Sheet has a new row.
- Row columns: Detected At | Competitor | Label | Reasoning | Source URL.
- Slack: :white_check_mark: Job Watch done.

## Workflow 3: Pricing Watch

Dry run, first run:

Actions -> Pricing Watch -> Run workflow -> dry_run: true

Check for:
- Baseline stored for the configured pricing URL.
- Pricing Watch done -> X items, 0 action(s).

This is expected on first run. It saves the baseline and has no diff yet.

Dry run, second run onward:

Run again after a few minutes.

Check for:
- No change detected for the configured pricing URL, if page is unchanged.
- If a diff is detected, Diff classifier -> cosmetic/material.
- Cosmetic change or dry_run -> no action taken.
- No Slack DM and no Calendar event.

Non-dry run:

Same steps, but set dry_run: false.

If a material change is detected, check for:
- Slack DM urgent alert.
- Alert posted to Slack channel.
- Calendar event created.
- Slack: :white_check_mark: Pricing Watch done.

## Workflow 4: Weekly Digest

Run this last. It reads RunLog rows from the other workflows.

Dry run:

Actions -> Weekly Digest -> Run workflow -> dry_run: true

Check for:
- X run logs found in past 7 days.
- Synthesized markdown printed in logs, truncated to the first 300 chars.
- Dry run -> digest synthesized but not sent.
- No email sent and no Slack post.

Non-dry run:

Same steps, but set dry_run: false.

Check for:
- Configured digest recipient receives an email with subject "Competitive Intel Digest - Week of ...".
- Slack channel shows :newspaper: Weekly Digest with TL;DR.
- Logs show weekly digest emailed to the configured recipient.

## Healthy Run Checklist

Check for:
- Exit code: 0.
- Duration: under 120 seconds.
- Slack start and done pings.
- items_processed > 0.
- No [ERROR] lines in logs.

If news or jobs shows 0 items processed, the API key may be missing or the query returned nothing. Check the raw log line immediately before it.

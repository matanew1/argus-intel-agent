"""Workflow 3 — Pricing & Site Change Watch: runs daily at 8am."""
from datetime import datetime, timezone

from argus.core.database import get_session
from argus.core.logger import get_logger
from argus.core.models import PageSnapshot, RunLog
from argus.integrations.scraper import content_hash, fetch_page_text, unified_diff
from argus.classifiers.diff import classify_diff
from argus.workflows.base import BaseWorkflow

log = get_logger(__name__)


class PricingWatchWorkflow(BaseWorkflow):
    """Detect and classify changes on competitor pricing and product pages.

    On first visit a baseline snapshot is stored. Subsequent runs compare the
    current page hash against the snapshot; if different, a unified diff is sent
    to the LLM classifier.

    Actions taken per label:
    - ``material`` → Slack DM to owner + channel post + Google Calendar event.
    - ``cosmetic`` → logged and skipped.
    """

    name = "pricing_watch"

    def _execute(self, cfg: dict, run_log: RunLog, dry_run: bool) -> None:
        """Process every pricing URL for every competitor."""
        channel_id  = cfg["notifications"]["slack_channel"]
        dm_user     = cfg["notifications"]["slack_dm_user"]
        calendar_id = cfg["notifications"]["calendar_id"]
        competitors = cfg.get("competitors", [])

        for competitor in competitors:
            for url in competitor.get("pricing_urls", []):
                run_log.items_processed += 1
                self._process_url(
                    url, competitor["name"], channel_id, dm_user,
                    calendar_id, run_log, dry_run,
                )

    def _process_url(
        self, url: str, competitor: str,
        channel_id: str, dm_user: str, calendar_id: str,
        run_log: RunLog, dry_run: bool,
    ) -> None:
        """Fetch the page, diff against the last snapshot, classify the change, and act."""
        new_text = self._safe_action(fetch_page_text, run_log, "fetch_page_text", url)
        if new_text is None:
            return

        new_hash = content_hash(new_text)
        old = self._safe_action(self._get_snapshot, run_log, "get_snapshot", url)

        if old is None:
            self._safe_action(self._store_snapshot, run_log, "store_snapshot", url, new_hash, new_text)
            log.info("Baseline stored for %s", url)
            return

        if old["content_hash"] == new_hash:
            log.info("No change detected for %s", url)
            return

        diff = unified_diff(old["content_text"], new_text)
        judgment = self._safe_action(classify_diff, run_log, "classify_diff", competitor, url, diff)
        if judgment is None:
            return

        diff_id = f"{url}::{new_hash[:12]}"
        run_log.add_decision(diff_id, judgment.label, judgment.reasoning)

        if judgment.label == "material" and not dry_run:
            alert_text = (
                f":alert: *Pricing/Product change detected*\n"
                f"*{competitor}* — {url}\n"
                f">{judgment.summary}"
            )
            self._safe_action(self._send_dm, run_log, "slack_dm", dm_user, alert_text)
            self._safe_action(self._post_to_slack, run_log, "slack_channel", channel_id, alert_text)
            self._safe_action(
                self._create_pricing_event, run_log, "calendar_event",
                calendar_id, competitor, url, judgment.summary,
            )
            run_log.add_action("slack_dm", dm_user, "sent")
            run_log.add_action("slack_channel", channel_id, "sent")
            run_log.add_action("calendar_event", calendar_id, "created")
            log.info("Material pricing change alert sent for %s", competitor)
        else:
            log.warning("Cosmetic change or dry_run for %s — no action taken", url)

        self._store_snapshot(url, new_hash, new_text)

    @staticmethod
    def _get_snapshot(url: str) -> dict | None:
        """Return snapshot data as a plain dict, or None if no baseline exists yet."""
        with get_session() as session:
            row = session.query(PageSnapshot).filter_by(url=url).first()
            if row is None:
                return None
            return {"content_hash": row.content_hash, "content_text": row.content_text}

    @staticmethod
    def _store_snapshot(url: str, hash_val: str, text: str) -> None:
        """Insert or update the PageSnapshot row for url."""
        with get_session() as session:
            snap = session.query(PageSnapshot).filter_by(url=url).first()
            if snap:
                snap.content_hash = hash_val
                snap.content_text = text
                snap.captured_at = datetime.now(timezone.utc)
            else:
                session.add(PageSnapshot(url=url, content_hash=hash_val, content_text=text))

    @staticmethod
    def _create_pricing_event(calendar_id, competitor, url, summary) -> None:
        """Create a 30-minute calendar event for a detected pricing change."""
        from argus.integrations.google_calendar import create_strategy_event
        create_strategy_event(
            calendar_id,
            f"Pricing change: {competitor}",
            f"{summary}\n\nPage: {url}",
            datetime.now(timezone.utc),
            30,
        )


if __name__ == "__main__":
    PricingWatchWorkflow.main()

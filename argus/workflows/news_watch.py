"""Workflow 1 — News Watch: runs every 2 hours."""
import os
from datetime import datetime, timedelta

from argus.core.dedup import filter_unseen, mark_seen
from argus.core.logger import get_logger
from argus.core.models import RunLog
from argus.integrations.news_client import fetch_news
from argus.judges.news import judge_news
from argus.workflows.base import BaseWorkflow

log = get_logger(__name__)


class NewsWatchWorkflow(BaseWorkflow):
    name = "news_watch"

    def _execute(self, cfg: dict, run_log: RunLog, dry_run: bool) -> None:
        criteria    = cfg["criteria"]["what_i_care_about"]
        channel_id  = cfg["notifications"]["slack_channel"]
        calendar_id = cfg["notifications"]["calendar_id"]

        for competitor in cfg["competitors"]:
            articles = self._safe_action(
                fetch_news, run_log, "fetch_news", competitor["news_query"]
            ) or []

            items = [{"url": a.url, "_article": a} for a in articles]
            unseen = filter_unseen(items, self.name, "url")
            run_log.items_processed += len(articles)

            for item in unseen:
                article = item["_article"]
                fp = item["_fingerprint"]
                judgment = self._safe_action(
                    judge_news, run_log, "judge_news",
                    vars(article), criteria,
                )
                if judgment is None:
                    continue

                run_log.add_decision(fp, judgment.label, judgment.reasoning)

                if judgment.label in ("funding", "product_launch") and not dry_run:
                    tomorrow = datetime.utcnow() + timedelta(days=1)
                    title = (
                        f"Strategy Review: {competitor['name']} — "
                        f"{judgment.label.replace('_', ' ').title()}"
                    )
                    event_url = self._safe_action(
                        self._create_calendar_event, run_log, "create_calendar_event",
                        calendar_id, title, article.url, tomorrow,
                    )
                    run_log.add_action("calendar_event", event_url or calendar_id, "created", article.url)
                    log.info("Calendar event created for %s", competitor["name"])

                elif judgment.label in ("executive_change", "controversy") and not dry_run:
                    text = (
                        f":rotating_light: *{competitor['name']}* — "
                        f"{judgment.label.replace('_', ' ').title()}\n"
                        f">{judgment.reasoning}\n"
                        f"<{article.url}|Read article>"
                    )
                    self._safe_action(
                        self._post_to_slack, run_log, "slack_post", channel_id, text
                    )
                    run_log.add_action("slack_post", channel_id, "sent", article.url)

                else:
                    log.warning("Noise or dry_run — skipping action for: %s", article.title[:60])

                mark_seen(fp, self.name, "news_article", article.url, judgment.label,
                          acted_on=judgment.label not in ("noise",))

    @staticmethod
    def _create_calendar_event(calendar_id: str, title: str, article_url: str, date: datetime) -> str:
        from argus.integrations.google_calendar import create_strategy_event
        return create_strategy_event(calendar_id, title, f"Source: {article_url}", date, 30)

    @staticmethod
    def _post_to_slack(channel_id: str, text: str) -> None:
        from argus.integrations.slack_client import post_to_channel
        post_to_channel(channel_id, text)


if __name__ == "__main__":
    from argus.core.database import init_db
    dry = os.getenv("DRY_RUN", "false").lower() == "true"
    init_db()
    NewsWatchWorkflow().run(dry_run=dry)

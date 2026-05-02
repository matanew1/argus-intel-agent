"""Workflow 1 — News Watch: runs every 2 hours."""
from datetime import datetime, timedelta, timezone

from argus.core.dedup import (
    filter_unseen,
    get_seen_source_url,
    is_seen,
    make_fingerprint,
    mark_seen,
)
from argus.core.logger import get_logger
from argus.core.models import RunLog
from argus.integrations.news_client import fetch_news
from argus.classifiers.news import classify_news
from argus.workflows.base import BaseWorkflow

log = get_logger(__name__)


class NewsWatchWorkflow(BaseWorkflow):
    """Fetch competitor news, classify each article with Mistral, and act on signals.

    Actions taken per label:
    - ``funding`` / ``product_launch`` → Google Calendar event for tomorrow.
    - ``executive_change`` / ``controversy`` → Slack channel alert.
    - ``noise`` → logged and skipped.
    """

    name = "news_watch"

    def _execute(self, cfg: dict, run_log: RunLog, dry_run: bool) -> None:
        """Iterate over competitors, classify unseen articles, and dispatch actions."""
        criteria    = cfg["criteria"]["what_i_care_about"]
        channel_id  = cfg["notifications"]["slack_channel"]
        calendar_id = cfg["notifications"]["calendar_id"]
        competitors = cfg.get("competitors", [])

        for competitor in competitors:
            articles = self._safe_action(
                fetch_news, run_log, "fetch_news", competitor["news_query"]
            ) or []

            # Drop articles that don't mention this competitor — prevents cross-contamination
            # when NewsAPI returns articles about other companies in the same query results.
            name = competitor["name"].lower()
            articles = [
                a for a in articles
                if name in a.title.lower() or name in a.description.lower()
            ]

            items = [{"url": a.url, "_article": a} for a in articles]
            unseen = filter_unseen(items, self.name, "url")
            run_log.items_processed += len(articles)

            for item in unseen:
                article = item["_article"]
                fp = item["_fingerprint"]
                mark_article = True
                judgment = self._safe_action(
                    classify_news, run_log, "classify_news",
                    vars(article), criteria,
                )
                if judgment is None:
                    continue

                run_log.add_decision(fp, judgment.label, judgment.reasoning)

                if judgment.label in ("funding", "product_launch") and not dry_run:
                    calendar_action_succeeded = False
                    # One calendar event per competitor per label per day — prevents
                    # duplicate events when multiple articles cover the same story.
                    today = datetime.now(timezone.utc).date().isoformat()
                    cal_fp = make_fingerprint(self.name, f"calendar::{name}::{judgment.label}::{today}")
                    if is_seen(cal_fp):
                        event_id = get_seen_source_url(cal_fp)
                        if event_id:
                            updated_event_id = self._safe_action(
                                self._append_url_to_calendar_event,
                                run_log,
                                "append_url_to_calendar_event",
                                calendar_id,
                                event_id,
                                article.url,
                            )
                            if updated_event_id:
                                calendar_action_succeeded = True
                                run_log.add_action(
                                    "calendar_event",
                                    updated_event_id,
                                    "updated",
                                    article.url,
                                )
                                log.info(
                                    "Calendar event updated for %s %s today",
                                    competitor["name"],
                                    judgment.label,
                                )
                        else:
                            log.warning(
                                "Calendar event already created for %s %s today, "
                                "but no event id was stored; cannot append article URL",
                                competitor["name"],
                                judgment.label,
                            )
                    else:
                        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
                        title = (
                            f"Strategy Review: {competitor['name']} — "
                            f"{judgment.label.replace('_', ' ').title()}"
                        )
                        event = self._safe_action(
                            self._create_calendar_event, run_log, "create_calendar_event",
                            calendar_id, title, article.url, tomorrow,
                        )
                        if event:
                            event_id, event_url = event
                            calendar_action_succeeded = True
                            run_log.add_action(
                                "calendar_event",
                                event_url or calendar_id,
                                "created",
                                article.url,
                            )
                            mark_seen(
                                cal_fp,
                                self.name,
                                "calendar_dedup",
                                source_url=event_id,
                                label=judgment.label,
                                acted_on=True,
                            )
                            log.info("Calendar event created for %s", competitor["name"])
                    if not calendar_action_succeeded:
                        mark_article = False

                elif judgment.label in ("executive_change", "controversy") and not dry_run:
                    text = (
                        f":rotating_light: *{competitor['name']}* — "
                        f"{judgment.label.replace('_', ' ').title()}\n"
                        f">{judgment.reasoning}\n"
                        f"<{article.url}|Read article>"
                    )
                    self._safe_action(self._post_to_slack, run_log, "slack_post", channel_id, text)
                    run_log.add_action("slack_post", channel_id, "sent", article.url)

                else:
                    log.warning("Noise or dry_run — skipping action for: %s", article.title[:60])

                if mark_article:
                    mark_seen(fp, self.name, "news_article", article.url, judgment.label,
                              acted_on=judgment.label not in ("noise",))
                else:
                    log.warning("Article left unmarked so calendar append can retry: %s", article.url)

    @staticmethod
    def _create_calendar_event(
        calendar_id: str,
        title: str,
        article_url: str,
        date: datetime,
    ) -> tuple[str, str]:
        """Create a 30-minute strategy review event and return its id and HTML link."""
        from argus.integrations.google_calendar import create_strategy_event
        return create_strategy_event(calendar_id, title, f"Source: {article_url}", date, 30)

    @staticmethod
    def _append_url_to_calendar_event(calendar_id: str, event_id: str, article_url: str) -> str:
        """Append an article URL to an existing strategy review event."""
        from argus.integrations.google_calendar import append_url_to_event
        append_url_to_event(calendar_id, event_id, article_url)
        return event_id


if __name__ == "__main__":
    NewsWatchWorkflow.main()

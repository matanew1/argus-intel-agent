"""Workflow 2 — Job Posting Watch: runs daily at 9am."""
from datetime import datetime, timezone

from argus.core.dedup import filter_unseen, mark_seen
from argus.core.logger import get_logger
from argus.core.models import RunLog
from argus.integrations.scraper import scrape_jobs_html, scrape_jobs_rss
from argus.classifiers.jobs import classify_job_cluster
from argus.workflows.base import BaseWorkflow

log = get_logger(__name__)


class JobWatchWorkflow(BaseWorkflow):
    """Scrape competitor careers pages, cluster new roles, and log strategic signals.

    New job postings are batched per competitor and sent to the LLM as a cluster
    so that strategic patterns (e.g. 12 new ML roles) surface as a single signal
    rather than individual noise items.

    Actions taken per label:
    - ``infra_scaling`` / ``entering_new_market`` / ``building_ai_team`` → append row to Google Sheet.
    - ``routine_backfill`` → logged and skipped.
    """

    name = "job_watch"

    def _execute(self, cfg: dict, run_log: RunLog, dry_run: bool) -> None:
        """Fetch, deduplicate, classify, and record job signals for every competitor."""
        criteria = cfg["criteria"]["what_i_care_about"]
        sheet_id = cfg["notifications"]["google_sheet_id"]

        for competitor in cfg["competitors"]:
            raw_jobs = self._fetch_jobs(competitor)
            run_log.items_processed += len(raw_jobs)

            unseen = filter_unseen(raw_jobs, self.name, "id")
            if not unseen:
                log.info("No new job postings for %s", competitor["name"])
                continue

            judgment = self._safe_action(
                classify_job_cluster, run_log, "classify_job_cluster",
                competitor["name"], unseen, criteria,
            )
            if judgment is None:
                continue

            batch_id = f"{competitor['name']}:{len(unseen)}_roles"
            run_log.add_decision(batch_id, judgment.label, judgment.reasoning)

            if judgment.label != "routine_backfill" and not dry_run:
                self._safe_action(
                    self._append_sheet_row, run_log, "append_sheet_row",
                    sheet_id, competitor["name"], judgment.label,
                    judgment.reasoning, competitor.get("careers_url", ""),
                )
                run_log.add_action("sheets_append", sheet_id, "written", judgment.label)
                log.info("Sheet row added for %s (%s)", competitor["name"], judgment.label)
            else:
                log.warning(
                    "routine_backfill or dry_run — skipping sheet write for %s", competitor["name"]
                )

            for item in unseen:
                mark_seen(
                    item["_fingerprint"], self.name, "job_posting",
                    source_url=item.get("id"),
                    label=judgment.label,
                    acted_on=(judgment.label != "routine_backfill"),
                )

    @staticmethod
    def _fetch_jobs(competitor: dict) -> list[dict]:
        """Return job listings via RSS if configured, otherwise fall back to HTML scraping."""
        if rss_url := competitor.get("linkedin_rss"):
            return scrape_jobs_rss(rss_url)
        return scrape_jobs_html(competitor.get("careers_url", ""))

    @staticmethod
    def _append_sheet_row(sheet_id, competitor, label, reasoning, url) -> None:
        """Append one signal row to the configured Google Sheet."""
        from argus.integrations.google_sheets import append_signal_row
        append_signal_row(
            sheet_id, competitor, label, reasoning, url,
            detected_at=datetime.now(timezone.utc).isoformat(),
        )


if __name__ == "__main__":
    JobWatchWorkflow.main()

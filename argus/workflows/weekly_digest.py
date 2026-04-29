"""Workflow 4 — Weekly Digest: runs every Friday at 4pm."""
import json
import os
from datetime import datetime, timedelta

from argus.core.database import get_session
from argus.core.logger import get_logger
from argus.core.models import RunLog
from argus.judges.digest import synthesize_digest
from argus.workflows.base import BaseWorkflow

log = get_logger(__name__)


class WeeklyDigestWorkflow(BaseWorkflow):
    name = "weekly_digest"

    def _execute(self, cfg: dict, run_log: RunLog, dry_run: bool) -> None:
        criteria   = cfg["criteria"]["what_i_care_about"]
        channel_id = cfg["notifications"]["slack_channel"]
        email_to   = cfg["notifications"]["digest_email"]
        cutoff     = datetime.utcnow() - timedelta(days=7)

        recent_logs = self._load_recent_logs(cutoff)
        run_log.items_processed = len(recent_logs)

        if not recent_logs:
            log.info("No run logs in past 7 days — skipping digest")
            run_log.add_action("digest", "skipped", "no_data")
            return

        run_logs_text = self._serialize_logs(recent_logs)
        digest_md = self._safe_action(
            synthesize_digest, run_log, "synthesize_digest",
            run_logs_text, criteria,
        )
        if digest_md is None:
            return

        week_str = datetime.utcnow().strftime("%b %d, %Y")
        subject = f"Competitive Intel Digest — Week of {week_str}"

        if not dry_run:
            msg_id = self._safe_action(
                self._send_email, run_log, "send_email",
                email_to, subject, digest_md,
            )
            run_log.add_action("email", email_to, "sent", msg_id or "")

            tldr = self._extract_tldr(digest_md)
            self._safe_action(
                self._post_to_slack, run_log, "slack_post",
                channel_id, f":newspaper: *Weekly Digest*\n{tldr}\n_(Full digest emailed)_",
            )
            run_log.add_action("slack_post", channel_id, "sent")
            log.info("Weekly digest emailed to %s and posted to Slack", email_to)
        else:
            log.info("Dry run — digest synthesized but not sent:\n%s", digest_md[:300])

    @staticmethod
    def _load_recent_logs(cutoff: datetime) -> list[RunLog]:
        with get_session() as session:
            return (
                session.query(RunLog)
                .filter(RunLog.trigger_time >= cutoff)
                .filter(RunLog.workflow != "weekly_digest")
                .order_by(RunLog.trigger_time.asc())
                .all()
            )

    @staticmethod
    def _serialize_logs(logs: list[RunLog]) -> str:
        lines: list[str] = []
        for r in logs:
            lines.append(f"\n--- {r.workflow} at {r.trigger_time.isoformat()} ---")
            for d in json.loads(r.decisions):
                lines.append(f"  DECISION: {d['label']} — {d['reasoning']}")
            for a in json.loads(r.actions_taken):
                lines.append(f"  ACTION: {a['action']} → {a['target']} ({a['status']})")
        return "\n".join(lines)

    @staticmethod
    def _extract_tldr(digest_md: str) -> str:
        if "##" in digest_md:
            section = digest_md.split("##")[1]
            return section[:500].strip()
        return digest_md[:500].strip()

    @staticmethod
    def _send_email(to: str, subject: str, body: str) -> str:
        from argus.integrations.resend_client import send_digest_email
        return send_digest_email(to, subject, body)

    @staticmethod
    def _post_to_slack(channel_id: str, text: str) -> None:
        from argus.integrations.slack_client import post_to_channel
        post_to_channel(channel_id, text)


if __name__ == "__main__":
    from argus.core.database import init_db
    dry = os.getenv("DRY_RUN", "false").lower() == "true"
    init_db()
    WeeklyDigestWorkflow().run(dry_run=dry)

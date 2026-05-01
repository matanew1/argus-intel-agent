"""Workflow 4 — Weekly Digest: runs every Friday at 4pm."""
import json
from datetime import datetime, timedelta, timezone

from argus.core.database import get_session
from argus.core.logger import get_logger
from argus.core.models import RunLog
from argus.classifiers.digest import synthesize_digest
from argus.workflows.base import BaseWorkflow

log = get_logger(__name__)


class WeeklyDigestWorkflow(BaseWorkflow):
    """Synthesise the past week's signals into a markdown digest and distribute it.

    Steps:
    1. Load all RunLog rows from the past 7 days (excluding previous digest runs).
    2. Serialise decisions and actions to plain text.
    3. Ask Mistral to write a structured executive summary.
    4. Email the full digest via Resend.
    5. Post a TL;DR to Slack.
    """

    name = "weekly_digest"

    def _execute(self, cfg: dict, run_log: RunLog, dry_run: bool) -> None:
        """Load recent logs, synthesise a digest, then email and post to Slack."""
        criteria   = cfg["criteria"]["what_i_care_about"]
        channel_id = cfg["notifications"]["slack_channel"]
        email_to   = cfg["notifications"]["digest_email"]
        cutoff     = datetime.now(timezone.utc) - timedelta(days=7)

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

        week_str = datetime.now(timezone.utc).strftime("%b %d, %Y")
        subject = f"Competitive Intel Digest — Week of {week_str}"

        if not dry_run:
            msg_id = self._safe_action(
                self._send_digest_email, run_log, "send_email",
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
            log.info("Dry run — digest synthesised but not sent:\n%s", digest_md[:300])

    @staticmethod
    def _load_recent_logs(cutoff: datetime) -> list[dict]:
        """Return all non-digest RunLog rows from after cutoff as plain dicts (avoids detached-instance errors)."""
        with get_session() as session:
            rows = (
                session.query(RunLog)
                .filter(RunLog.trigger_time >= cutoff)
                .filter(RunLog.workflow != "weekly_digest")
                .order_by(RunLog.trigger_time.asc())
                .all()
            )
            return [
                {
                    "workflow":     r.workflow,
                    "trigger_time": r.trigger_time,
                    "decisions":    r.decisions,
                    "actions_taken": r.actions_taken,
                }
                for r in rows
            ]

    @staticmethod
    def _serialize_logs(logs: list[dict]) -> str:
        """Convert a list of RunLog dicts into a human-readable plain-text block."""
        lines: list[str] = []
        for r in logs:
            lines.append(f"\n--- {r['workflow']} at {r['trigger_time'].isoformat()} ---")
            for d in json.loads(r["decisions"]):
                lines.append(f"  DECISION: {d['label']} — {d['reasoning']}")
            for a in json.loads(r["actions_taken"]):
                lines.append(f"  ACTION: {a['action']} → {a['target']} ({a['status']})")
        return "\n".join(lines)

    @staticmethod
    def _extract_tldr(digest_md: str) -> str:
        """Return the first 500 characters of the first markdown section as a TL;DR."""
        if "##" in digest_md:
            section = digest_md.split("##")[1]
            return section[:500].strip()
        return digest_md[:500].strip()

    @staticmethod
    def _send_digest_email(to: str, subject: str, body: str) -> str:
        """Send the digest email via Resend and return the message ID."""
        from argus.integrations.resend_client import send_digest_email
        return send_digest_email(to, subject, body)


if __name__ == "__main__":
    WeeklyDigestWorkflow.main()

"""Abstract base class shared by all argus workflows."""
import json
import os
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from argus.core.config_loader import ConfigLoader
from argus.core.database import get_session
from argus.core.logger import get_logger
from argus.core.models import RunLog

log = get_logger(__name__)


def _save_run_log(run_log: RunLog) -> None:
    """Persist (or update) a RunLog row using merge so it works for both insert and update."""
    with get_session() as session:
        session.merge(run_log)


class BaseWorkflow(ABC):
    """Template-method base class for all argus workflows.

    Subclasses implement ``_execute()``; everything else (config loading,
    RunLog creation, Slack pings, error handling, timing) is handled here.
    """

    name: str = "base"

    def run(self, dry_run: bool = False) -> RunLog:
        """Execute the workflow and return the completed RunLog.

        Steps:
        1. Load config via ConfigLoader singleton.
        2. Create a new RunLog.
        3. Optionally post a startup Slack ping.
        4. Delegate to ``_execute()``.
        5. Record duration, save RunLog, post completion ping.

        Exceptions raised inside ``_execute()`` are caught, logged to RunLog,
        and swallowed so the GitHub Actions step still exits 0.
        """
        cfg = ConfigLoader.instance().get()
        channel_id = cfg.get("notifications", {}).get("slack_channel", "")
        run_log = RunLog(
            workflow=self.name,
            trigger_time=datetime.now(timezone.utc),
            items_processed=0,
            decisions="[]",
            actions_taken="[]",
            errors="[]",
        )
        start = time.monotonic()

        if not dry_run and channel_id:
            self._notify_start(channel_id)

        try:
            self._execute(cfg, run_log, dry_run=dry_run)
        except Exception as exc:
            run_log.add_error(str(exc), traceback.format_exc())
            log.error("Workflow %s failed: %s", self.name, exc)
        finally:
            run_log.duration_seconds = int(time.monotonic() - start)
            _save_run_log(run_log)
            actions = json.loads(run_log.actions_taken)
            log.info(
                "Workflow %s done — %d items, %d action(s) in %ds",
                self.name,
                run_log.items_processed,
                len(actions),
                run_log.duration_seconds,
            )
            if not dry_run and channel_id:
                self._notify_done(channel_id, run_log)

        return run_log

    @abstractmethod
    def _execute(self, cfg: dict, log: RunLog, dry_run: bool) -> None:
        """Workflow-specific logic. Implemented by each subclass."""
        ...

    def _safe_action(self, fn, run_log: RunLog, action_name: str, *args, **kwargs):
        """Call fn with one automatic retry on failure.

        If both attempts raise, the error is logged to run_log and None is
        returned — the workflow continues rather than crashing.
        """
        for attempt in range(2):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if attempt == 0:
                    time.sleep(2)
                else:
                    run_log.add_error(
                        f"{action_name} failed: {exc}",
                        traceback.format_exc(),
                    )
                    log.error("%s failed after 2 attempts: %s", action_name, exc)
                    return None

    @staticmethod
    def _post_to_slack(channel_id: str, text: str) -> None:
        """Post a message to a Slack channel."""
        from argus.integrations.slack_client import post_to_channel
        post_to_channel(channel_id, text)

    @staticmethod
    def _send_dm(user_id: str, text: str) -> None:
        """Send a Slack DM to a user."""
        from argus.integrations.slack_client import send_dm
        send_dm(user_id, text)

    def _notify_start(self, channel_id: str) -> None:
        """Post a startup ping to Slack. Failures are silently ignored."""
        try:
            from argus.integrations.slack_client import notify_start
            notify_start(self.name, channel_id)
        except Exception:
            pass

    def _notify_done(self, channel_id: str, run_log: RunLog) -> None:
        """Post a completion summary to Slack. Failures are silently ignored."""
        try:
            from argus.integrations.slack_client import notify_done
            actions = json.loads(run_log.actions_taken)
            notify_done(self.name, channel_id, run_log.items_processed, len(actions))
        except Exception:
            pass

    @classmethod
    def main(cls) -> None:
        """Entry point for running a workflow directly (``python -m argus.workflows.foo``)."""
        from argus.core.database import init_db
        dry = os.getenv("DRY_RUN", "false").lower() == "true"
        init_db()
        cls().run(dry_run=dry)

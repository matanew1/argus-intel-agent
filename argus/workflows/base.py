import json
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime

from argus.core.config_loader import ConfigLoader
from argus.core.database import get_session
from argus.core.logger import get_logger
from argus.core.models import RunLog

log = get_logger(__name__)


def _save_run_log(run_log: RunLog) -> None:
    with get_session() as session:
        session.merge(run_log)


class BaseWorkflow(ABC):
    name: str = "base"

    def run(self, dry_run: bool = False) -> RunLog:
        """
        Template method:
        1. Load config
        2. Create RunLog
        3. Optionally post startup Slack ping
        4. Delegate to _execute()
        5. Record duration, save, post completion ping
        """
        cfg = ConfigLoader.instance().get()
        channel_id = cfg.get("notifications", {}).get("slack_channel", "")
        run_log = RunLog(
            workflow=self.name,
            trigger_time=datetime.utcnow(),
            items_processed=0,
            decisions="[]",
            actions_taken="[]",
            errors="[]",
        )
        start = time.monotonic()

        if not dry_run and channel_id:
            self._try_notify_start(channel_id)

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
                self._try_notify_done(channel_id, run_log)

        return run_log

    @abstractmethod
    def _execute(self, cfg: dict, log: RunLog, dry_run: bool) -> None: ...

    def _safe_action(self, fn, run_log: RunLog, action_name: str, *args, **kwargs):
        """Call fn with 2-attempt retry. Logs failure to run_log without raising."""
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

    def _try_notify_start(self, channel_id: str) -> None:
        try:
            from argus.integrations.slack_client import notify_start
            notify_start(self.name, channel_id)
        except Exception:
            pass

    def _try_notify_done(self, channel_id: str, run_log: RunLog) -> None:
        try:
            from argus.integrations.slack_client import notify_done
            actions = json.loads(run_log.actions_taken)
            notify_done(self.name, channel_id, run_log.items_processed, len(actions))
        except Exception:
            pass

"""Thread-safe singleton that loads config.yaml and hot-reloads it on file changes."""
import json
import threading
from pathlib import Path
from typing import Any

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from argus.core.logger import get_logger

log = get_logger(__name__)

_CONFIG_PATH = Path("config.yaml")


class ConfigLoader:
    """Singleton config loader with file-watching and DB sync.

    Usage:
        cfg = ConfigLoader.instance().get()
    """

    _instance: "ConfigLoader | None" = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self, path: Path = _CONFIG_PATH) -> None:
        """Load config from path and start the file watcher."""
        self._path = path
        self._data: dict[str, Any] = {}
        self._load()
        self._start_watcher()

    @classmethod
    def instance(cls, path: Path = _CONFIG_PATH) -> "ConfigLoader":
        """Return the singleton, creating it on first call (double-checked lock)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(path)
        return cls._instance

    def _load(self) -> None:
        """Parse YAML from disk and sync the result to the DB Config row."""
        with self._lock:
            with open(self._path) as f:
                self._data = yaml.safe_load(f)
            log.info("Config loaded from %s", self._path)
            self._sync_to_db()

    def get(self) -> dict[str, Any]:
        """Return a shallow copy of the current config dict (thread-safe)."""
        with self._lock:
            return dict(self._data)

    def _sync_to_db(self) -> None:
        """Write the current config into the single Config DB row (id=1).

        Failures are logged and swallowed so a DB outage never blocks startup.
        """
        try:
            from argus.core.database import get_session
            from argus.core.models import Config
            notif = self._data.get("notifications", {})
            comp = self._data.get("competitors", [])
            criteria = self._data.get("criteria", {}).get("what_i_care_about", "")
            with get_session() as session:
                row = session.get(Config, 1)
                if row is None:
                    row = Config(id=1)
                    session.add(row)
                row.competitors = json.dumps(comp)
                row.criteria = criteria
                row.notifications = json.dumps(notif)
        except Exception as exc:
            log.warning("Could not sync config to DB: %s", exc)

    def _start_watcher(self) -> None:
        """Spawn a daemon watchdog thread that calls _load() when config.yaml changes."""
        loader = self

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event) -> None:
                if Path(event.src_path).resolve() == loader._path.resolve():
                    loader._load()

        observer = Observer()
        observer.schedule(_Handler(), str(self._path.parent), recursive=False)
        observer.daemon = True
        observer.start()

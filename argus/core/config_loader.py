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
    _instance: "ConfigLoader | None" = None
    _lock: threading.RLock = threading.RLock()

    def __init__(self, path: Path = _CONFIG_PATH) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self._load()
        self._start_watcher()

    @classmethod
    def instance(cls, path: Path = _CONFIG_PATH) -> "ConfigLoader":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(path)
        return cls._instance

    def _load(self) -> None:
        with self._lock:
            with open(self._path) as f:
                self._data = yaml.safe_load(f)
            log.info("Config loaded from %s", self._path)
            self._sync_to_db()

    def get(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def _sync_to_db(self) -> None:
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
        loader = self

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event) -> None:
                if Path(event.src_path).resolve() == loader._path.resolve():
                    loader._load()

        observer = Observer()
        observer.schedule(_Handler(), str(self._path.parent), recursive=False)
        observer.daemon = True
        observer.start()

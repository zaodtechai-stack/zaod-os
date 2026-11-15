"""Installed-application database at ``/var/lib/zaod/db.json``."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path

from . import util
from .errors import StateError

DB_FORMAT = 1


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = {"format": DB_FORMAT, "apps": {}}
        self._loaded = False

    @contextlib.contextmanager
    def locked(self):
        """Serialise every mutation with an advisory lock on ``db.lock``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(".lock")
        with open(lock_path, "w", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                self.load()
                yield self
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def load(self) -> dict:
        self._loaded = True
        if not self.path.is_file():
            self.data = {"format": DB_FORMAT, "apps": {}}
            return self.data
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateError(f"{self.path} is corrupt: {exc}") from exc
        if not isinstance(data, dict) or data.get("format") != DB_FORMAT:
            raise StateError(f"{self.path} has an unsupported format")
        data.setdefault("apps", {})
        self.data = data
        return self.data

    def save(self) -> None:
        payload = json.dumps(self.data, indent=2, sort_keys=True).encode() + b"\n"
        util.atomic_write_bytes(self.path, payload, mode=0o644)

    @property
    def apps(self) -> dict:
        self._ensure_loaded()
        return self.data.setdefault("apps", {})

    def get(self, app_id: str) -> dict | None:
        self._ensure_loaded()
        return self.apps.get(app_id)

    def record(self, app_id: str, record: dict) -> None:
        self.apps[app_id] = record
        self.save()

    def forget(self, app_id: str) -> None:
        self.apps.pop(app_id, None)
        self.save()

    def installed_ids(self) -> list[str]:
        return sorted(self.apps)

    def record_install(self, manifest, *, target: str, source: str, key_id: str | None, files: int) -> dict:
        record = {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "kind": manifest.kind,
            "path": target,
            "installed_at": util.utc_now(),
            "manifest_sha256": util.sha256_bytes(manifest.canonical),
            "source": source,
            "key_id": key_id or "unsigned",
            "files": files,
            "permissions": manifest.permissions,
        }
        self.record(manifest.id, record)
        return record


def open_database(paths) -> Database:
    return Database(paths.db_file)


def fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:  # pragma: no cover - platform dependent
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

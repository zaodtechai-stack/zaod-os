"""Zaod Store backend.

Reads the signed store index through `zaodlib` (already installed on a Zaod
system) and performs privileged operations through the `zaod` CLI helper, so the
Store itself never runs as root. Browsing works offline from the cached index.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class StoreError(RuntimeError):
    """The store could not complete an operation."""


def _load_zaodlib():
    candidates = [os.environ.get("ZAOD_LIB"), "/usr/lib/zaod", "/zaod/lib"]
    for candidate in candidates:
        if candidate and (Path(candidate) / "zaodlib" / "__init__.py").is_file():
            sys.path.insert(0, candidate)
            break
    else:
        raise StoreError("zaodlib is not installed; the store needs a Zaod system")
    from zaodlib import db, keys, paths, repo

    return db, keys, paths, repo


def _compare_versions(left: str, right: str) -> int:
    def parts(value: str) -> list[int]:
        result = []
        for chunk in value.split("."):
            digits = "".join(ch for ch in chunk if ch.isdigit())
            result.append(int(digits) if digits else 0)
        return result

    first, second = parts(left), parts(right)
    for index in range(max(len(first), len(second))):
        a = first[index] if index < len(first) else 0
        b = second[index] if index < len(second) else 0
        if a != b:
            return 1 if a > b else -1
    return 0


class StoreBackend:
    """Browse, install, update and remove store apps."""

    def __init__(self, paths=None, run=None, zaod_cli: str | None = None):
        self.db_module, self.keys_module, paths_module, self.repo_module = _load_zaodlib()
        self.paths = paths or paths_module.Paths()
        self.run = run or self._run_privileged
        self.zaod_cli = zaod_cli or os.environ.get("ZAOD_CLI", "zaod")

    # ---- privileged actions -------------------------------------------------
    def _run_privileged(self, argv: list[str]) -> str:
        command = ["pkexec", "zaod-priv-helper", *argv]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=600)
        except FileNotFoundError as error:
            raise StoreError(f"cannot run {command[0]}: {error.filename} is missing") from error
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise StoreError(message[0] if message else "the operation failed")
        return result.stdout.strip()

    def install(self, app_id: str) -> str:
        return self.run(["install", app_id])

    def remove(self, app_id: str) -> str:
        return self.run(["remove", app_id])

    def update(self, app_id: str) -> str:
        return self.run(["update", app_id])

    def update_all(self) -> str:
        return self.run(["update"])

    # ---- read-only ----------------------------------------------------------
    def repositories(self) -> list:
        return self.repo_module.RepoSet(self.paths).repos

    def sync(self) -> dict:
        keyring = self.keys_module.trusted_keys(self.paths.keys_dir)
        indexes = {}
        errors = []
        for entry in self.repositories():
            try:
                indexes[entry.name] = self.repo_module.sync_repo(entry, self.paths, keyring)
            except Exception as error:  # noqa: BLE001 - report per repository
                errors.append(f"{entry.name}: {error}")
        if errors and not indexes:
            raise StoreError("; ".join(errors))
        self._errors = errors
        return indexes

    def cached(self) -> dict:
        indexes = {}
        for entry in self.repositories():
            try:
                index = self.repo_module.cached_index(self.paths, entry.name)
            except Exception:  # noqa: BLE001 - any unreadable cache simply means offline
                index = None
            if index is not None:
                indexes[entry.name] = index
        return indexes

    def offline(self) -> bool:
        return not self.cached()

    def installed(self) -> list[dict]:
        database = self.db_module.Database(self.paths.db_file)
        return sorted(
            (
                {
                    "id": app_id,
                    "name": record.get("name", app_id),
                    "version": record.get("version", ""),
                    "kind": record.get("kind", "app"),
                }
                for app_id, record in database.apps.items()
            ),
            key=lambda item: item["name"].lower(),
        )

    def catalogue(self, query: str = "", indexes: dict | None = None) -> list[dict]:
        indexes = indexes if indexes is not None else self.cached()
        installed = {item["id"]: item["version"] for item in self.installed()}
        seen: dict[str, dict] = {}
        for repo_name, index in indexes.items():
            for package in index.get("packages", []):
                app_id = package["id"]
                current = installed.get(app_id)
                state = "new"
                if current:
                    state = "update" if _compare_versions(package["version"], current) > 0 else "installed"
                candidate = {
                    "id": app_id,
                    "name": package.get("name", app_id),
                    "version": package["version"],
                    "summary": package.get("summary", ""),
                    "description": package.get("description", ""),
                    "categories": package.get("categories", []),
                    "license": package.get("license", {}).get("spdx", ""),
                    "permissions": package.get("permissions", {}),
                    "installed_version": current,
                    "state": state,
                    "repository": repo_name,
                    "size": package.get("size", 0),
                }
                existing = seen.get(app_id)
                if existing is None or _compare_versions(candidate["version"], existing["version"]) > 0:
                    seen[app_id] = candidate
        results = list(seen.values())
        needle = query.strip().lower()
        if needle:
            results = [
                item
                for item in results
                if needle in item["name"].lower()
                or needle in item["id"].lower()
                or needle in item["summary"].lower()
                or any(needle in category.lower() for category in item["categories"])
            ]
        return sorted(results, key=lambda item: item["name"].lower())

    def details(self, app_id: str) -> dict:
        for item in self.catalogue():
            if item["id"] == app_id:
                return item
        raise StoreError(f"{app_id} is not in the store index")

    def updates_available(self) -> list[dict]:
        return [item for item in self.catalogue() if item["state"] == "update"]

    def permission_summary(self, item: dict) -> list[str]:
        permissions = item.get("permissions") or {}
        summary = []
        if permissions.get("network"):
            summary.append("network access")
        for folder in permissions.get("filesystem", []) or []:
            summary.append(f"files: {folder}")
        for device in permissions.get("devices", []) or []:
            summary.append(f"device: {device}")
        return summary or ["no extra permissions"]

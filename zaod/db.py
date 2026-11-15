"""The installed-package database.

A single JSON document below ``<root>/var/lib/zaod``. Writes are atomic
(temp file plus ``os.replace``) so an interrupted install cannot leave a
half-written database behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PackageError

DB_RELATIVE_PATH = "var/lib/zaod/db.json"
DB_FORMAT = 1


@dataclass
class InstalledPackage:
    """One record in the database."""

    id: str
    version: str
    kind: str
    name: str
    installed_at: str
    files: list = field(default_factory=list)
    key_id: str | None = None
    payload_bytes: int = 0
    previous_version: str | None = None
    signature_verified: bool = False

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "version": self.version,
            "kind": self.kind,
            "name": self.name,
            "installed_at": self.installed_at,
            "files": list(self.files),
            "payload_bytes": self.payload_bytes,
            "signature_verified": self.signature_verified,
        }
        if self.key_id:
            data["key_id"] = self.key_id
        if self.previous_version:
            data["previous_version"] = self.previous_version
        return data

    @classmethod
    def from_dict(cls, data: dict) -> InstalledPackage:
        try:
            return cls(
                id=data["id"],
                version=data["version"],
                kind=data["kind"],
                name=data["name"],
                installed_at=data["installed_at"],
                files=list(data.get("files", [])),
                key_id=data.get("key_id"),
                payload_bytes=int(data.get("payload_bytes", 0)),
                previous_version=data.get("previous_version"),
                signature_verified=bool(data.get("signature_verified", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PackageError(f"corrupt database record: {exc}") from exc


class Database:
    """Read and write the installed-package database under one root."""

    def __init__(self, root: str | os.PathLike[str] = "/") -> None:
        self.root = Path(root)
        self.path = self.root / DB_RELATIVE_PATH
        self.packages: dict = {}

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict:
        if not self.path.is_file():
            self.packages = {}
            return self.packages
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PackageError(f"{self.path} is not valid JSON: {exc}") from exc
        if document.get("format") != DB_FORMAT:
            raise PackageError(
                f"{self.path} has format {document.get('format')!r}, expected {DB_FORMAT}"
            )
        self.packages = {
            record["id"]: InstalledPackage.from_dict(record)
            for record in document.get("packages", [])
        }
        return self.packages

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "format": DB_FORMAT,
            "packages": [
                self.packages[key].to_dict() for key in sorted(self.packages)
            ],
        }
        payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(dir=str(self.path.parent), prefix=".db-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except Exception:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise

    # -- operations --------------------------------------------------------

    def get(self, package_id: str) -> InstalledPackage | None:
        return self.packages.get(package_id)

    def require(self, package_id: str) -> InstalledPackage:
        record = self.packages.get(package_id)
        if record is None:
            raise PackageError(f"{package_id} is not installed")
        return record

    def put(self, record: InstalledPackage) -> None:
        self.packages[record.id] = record

    def remove(self, package_id: str) -> InstalledPackage:
        record = self.require(package_id)
        del self.packages[package_id]
        return record

    def dependents(self, package_id: str) -> list:
        """Installed packages whose version of a runtime this one satisfies."""
        return [
            record.id
            for record in self.packages.values()
            if record.id != package_id and package_id in _runtime_ids(record)
        ]


def _runtime_ids(record: InstalledPackage) -> list:
    """Runtime ids a record depends on, taken from its manifest when available."""
    return list(getattr(record, "runtime_ids", []) or [])

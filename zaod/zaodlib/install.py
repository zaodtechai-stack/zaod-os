"""Transactional installation, update and removal of ``.zaod`` packages."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import archive, desktop, keys, util
from . import db as db_module
from .errors import StateError
from .verify import VerifiedPackage, verify_staged


@dataclass
class InstallResult:
    manifest: object
    version: str
    target: Path
    previous_version: str | None = None
    signed: bool = False
    files: int = 0
    warnings: list[str] = field(default_factory=list)


class Installer:
    """Install packages below ``paths`` with staged verification and rollback."""

    def __init__(self, paths, database=None, keyring=None):
        self.paths = paths
        self.db = database or db_module.open_database(paths)
        self._keyring = keyring

    # ---------------------------------------------------------------- helpers
    def keyring(self) -> dict[str, bytes]:
        if self._keyring is None:
            self._keyring = keys.trusted_keys(self.paths.keys_dir)
        return self._keyring

    def current_version(self, app_id: str) -> str | None:
        record = self.db.get(app_id)
        return record["version"] if record else None

    def installed(self) -> list[dict]:
        return [self.db.apps[app_id] for app_id in self.db.installed_ids()]

    # -------------------------------------------------------------- operations
    def install(
        self,
        package: Path,
        *,
        source: str = "local",
        allow_unsigned: bool = False,
        force: bool = False,
    ) -> InstallResult:
        package = Path(package)
        if not package.is_file():
            raise StateError(f"package not found: {package}")

        self.paths.apps_dir.mkdir(parents=True, exist_ok=True)
        staging = self.paths.apps_dir / f".staging-{uuid.uuid4().hex}"
        target: Path | None = None
        previous_record: dict | None = None
        symlink_changed = False
        desktop_written: Path | None = None

        try:
            archive.extract_tree(package, staging)
            verified = verify_staged(
                staging,
                keyring=self.keyring(),
                allow_unsigned=allow_unsigned,
                os_version=self.paths.os_version(),
            )
            manifest = verified.manifest
            previous_record = self.db.get(manifest.id)
            target = self.paths.app_version_dir(manifest.id, manifest.version)
            target.parent.mkdir(parents=True, exist_ok=True)

            if (
                previous_record
                and util.compare_semver(manifest.version, previous_record["version"]) < 0
                and not force
            ):
                raise StateError(
                    f"refusing to downgrade {manifest.id} from {previous_record['version']} "
                    f"to {manifest.version} (use --force)"
                )

            if previous_record and previous_record["version"] == manifest.version:
                if not force:
                    raise StateError(
                        f"{manifest.id} {manifest.version} is already installed "
                        "(use --force to reinstall)"
                    )
                util.remove_tree(target)

            if target.exists():
                raise StateError(f"{target} already exists; run 'zaod gc' and retry")

            os.replace(staging, target)
            util.make_read_only(target)

            util.atomic_symlink(self.paths.app_current(manifest.id), manifest.version)
            symlink_changed = True
            desktop_written = desktop.install_desktop_entry(self.paths, manifest)

            with self.db.locked():
                self.db.record_install(
                    manifest,
                    target=manifest.version,
                    source=source,
                    key_id=verified.key_id,
                    files=len(verified.checksums),
                )
        except BaseException:
            self._rollback(manifest_id=getattr(locals().get("manifest"), "id", None),
                           target=target, previous=previous_record,
                           symlink_changed=symlink_changed, desktop_written=desktop_written)
            raise
        finally:
            util.remove_tree(staging)

        return InstallResult(
            manifest=manifest,
            version=manifest.version,
            target=target,
            previous_version=previous_record["version"] if previous_record else None,
            signed=verified.signed,
            files=len(verified.checksums),
            warnings=[] if verified.signed else ["installed unsigned developer package"],
        )

    def _rollback(self, *, manifest_id, target, previous, symlink_changed, desktop_written) -> None:
        if target is not None and target.exists():
            util.remove_tree(target)
        if manifest_id is None:
            return
        current = self.paths.app_current(manifest_id)
        if symlink_changed:
            if previous is not None:
                util.atomic_symlink(current, previous["path"])
            elif current.is_symlink():
                current.unlink()
        if desktop_written is not None:
            desktop_written.unlink(missing_ok=True)
        app_dir = self.paths.app_dir(manifest_id)
        if app_dir.is_dir() and not any(app_dir.iterdir()):
            app_dir.rmdir()

    def remove(self, app_id: str, *, purge_data: bool = False) -> str:
        record = self.db.get(app_id)
        if record is None:
            raise StateError(f"{app_id} is not installed")
        with self.db.locked():
            desktop.remove_desktop_entry(self.paths, app_id)
            util.remove_tree(self.paths.app_dir(app_id))
            if purge_data:
                util.remove_tree(self.paths.app_data_dir(app_id))
            self.db.forget(app_id)
        return record["version"]

    def info(self, app_id: str) -> dict:
        record = self.db.get(app_id)
        if record is None:
            raise StateError(f"{app_id} is not installed")
        manifest_file = self.paths.app_current(app_id) / "MANIFEST.json"
        info = dict(record)
        if manifest_file.is_file():
            from .manifest import load_manifest

            manifest = load_manifest(manifest_file)
            info.update(
                {
                    "summary": manifest.summary,
                    "description": manifest.description,
                    "author": manifest.author["name"],
                    "license": manifest.license["spdx"],
                    "permissions": manifest.permissions,
                    "min_os": manifest.min_os,
                }
            )
        return info

    def gc(self) -> list[str]:
        """Drop superseded versions, stale staging directories and cache files."""
        removed: list[str] = []
        for app_id in self.db.installed_ids():
            record = self.db.get(app_id) or {}
            keep = {record.get("path", "")}
            app_dir = self.paths.app_dir(app_id)
            if not app_dir.is_dir():
                continue
            for entry in app_dir.iterdir():
                if entry.name == "current":
                    continue
                if entry.name not in keep:
                    util.remove_tree(entry)
                    removed.append(str(entry))
        if self.paths.apps_dir.is_dir():
            for entry in self.paths.apps_dir.glob(".staging-*"):
                util.remove_tree(entry)
                removed.append(str(entry))
        return removed


def verify_package(paths, package: Path, *, allow_unsigned: bool = False) -> VerifiedPackage:
    """Verify a package file without installing it (``zaod verify``)."""
    staging = paths.apps_dir / f".verify-{uuid.uuid4().hex}"
    try:
        archive.extract_tree(package, staging)
        return verify_staged(
            staging,
            keyring=keys.trusted_keys(paths.keys_dir),
            allow_unsigned=allow_unsigned,
            os_version=paths.os_version(),
        )
    finally:
        util.remove_tree(staging)

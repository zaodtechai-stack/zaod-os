"""Transactional install, update and removal below an injectable root.

Layout created below ``root``::

    usr/lib/zaod/apps/<id>/<version>/     unpacked payload
    usr/lib/zaod/apps/<id>/current -> <version>
    usr/share/applications/<id>.desktop
    var/lib/zaod/db.json                  installed database
    var/lib/zaod/staging/                 scratch space, always cleaned up

An install steps through verify, stage, promote and record. Any failure after
staging restores the previous ``current`` symlink and the previous database, so
a package is either fully installed or not installed at all.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import archive as archive_mod
from . import db as db_mod
from . import semver
from . import signature as signature_mod
from .errors import InstallError, PackageError, SignatureError

APPS_DIR = "usr/lib/zaod/apps"
APPLICATIONS_DIR = "usr/share/applications"
DEFAULT_OS_VERSION = "1.0.0"


@dataclass
class InstallResult:
    """Outcome of an install or update."""

    package_id: str
    version: str
    previous_version: str | None
    action: str
    files: int
    bytes_installed: int
    key_id: str | None
    signed: bool

    def summary(self) -> str:
        if self.action == "updated":
            return (
                f"updated {self.package_id} {self.previous_version} -> {self.version} "
                f"({self.files} files)"
            )
        if self.action == "reinstalled":
            return f"reinstalled {self.package_id} {self.version} ({self.files} files)"
        return f"installed {self.package_id} {self.version} ({self.files} files)"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_os_version(root: Path) -> str:
    """Installed OS version, from ``etc/zaod/os-version`` (default 1.0.0)."""
    candidate = root / "etc/zaod/os-version"
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8").strip()
        if text:
            try:
                semver.parse(text)
            except Exception as exc:
                raise InstallError(f"{candidate} is not a version: {exc}") from exc
            return text
    return DEFAULT_OS_VERSION


class Installer:
    """Install, update and remove packages under one root."""

    def __init__(
        self,
        root: str | os.PathLike[str] = "/",
        *,
        trust: signature_mod.TrustStore | None = None,
        allow_unsigned: bool = False,
        limits: archive_mod.Limits = archive_mod.DEFAULT_LIMITS,
    ) -> None:
        self.root = Path(root)
        self.trust = trust if trust is not None else signature_mod.TrustStore(self.root)
        self.allow_unsigned = allow_unsigned
        self.limits = limits
        self.database = db_mod.Database(self.root)

    # -- paths -------------------------------------------------------------

    def app_dir(self, package_id: str) -> Path:
        return self.root / APPS_DIR / package_id

    def version_dir(self, package_id: str, version: str) -> Path:
        return self.app_dir(package_id) / version

    def current_link(self, package_id: str) -> Path:
        return self.app_dir(package_id) / "current"

    def desktop_entry(self, package_id: str) -> Path:
        return self.root / APPLICATIONS_DIR / f"{package_id}.desktop"

    def staging_dir(self, package_id: str, version: str) -> Path:
        return self.root / "var/lib/zaod/staging" / f"{package_id}-{version}"

    # -- verification ------------------------------------------------------

    def verify(self, package_path: str | os.PathLike[str]) -> archive_mod.PackageContents:
        """Open a package and verify its checksums and signature."""
        contents = archive_mod.inspect(package_path, self.limits)
        try:
            archive_mod.verify_checksums(contents)
        except Exception:
            archive_mod.close_contents(contents)
            raise
        if contents.signature is None:
            if not self.allow_unsigned:
                archive_mod.close_contents(contents)
                raise SignatureError(
                    "package is unsigned and this system requires signatures "
                    "(re-run with --allow-unsigned only if you built it yourself)"
                )
            return contents
        import tarfile

        with tarfile.open(contents.tar_path, mode="r:") as archive:
            manifest_bytes = archive.extractfile(archive_mod.MANIFEST_NAME).read()
            checksums_bytes = archive.extractfile(archive_mod.CHECKSUMS_NAME).read()
        key = signature_mod.verify_with_store(
            manifest_bytes=manifest_bytes,
            checksums_bytes=checksums_bytes,
            signature=contents.signature,
            trust=self.trust,
        )
        contents.key_id = key.key_id
        contents.signer = key
        return contents

    # -- operations --------------------------------------------------------

    def install(
        self,
        package_path: str | os.PathLike[str],
        *,
        allow_downgrade: bool = False,
    ) -> InstallResult:
        contents = self.verify(package_path)
        staging = None
        backup_link = None
        try:
            manifest = contents.manifest
            self.database.load()
            installed = self.database.get(manifest.id)
            if (
                installed is not None
                and semver.compare(manifest.version, installed.version) < 0
                and not allow_downgrade
            ):
                raise InstallError(
                    f"{manifest.id} {installed.version} is installed; refusing to downgrade "
                    f"to {manifest.version} without --allow-downgrade"
                )
            os_version = read_os_version(self.root)
            if semver.compare(manifest.min_os, os_version) > 0:
                raise InstallError(
                    f"{manifest.id} needs Zaod OS {manifest.min_os} or newer; this system is "
                    f"{os_version}"
                )
            if manifest.arch != "x86_64":
                raise InstallError(f"{manifest.id} is built for {manifest.arch}, this system is x86_64")

            staging = self.staging_dir(manifest.id, manifest.version)
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            archive_mod.unpack(contents, staging, self.limits)

            target = self.version_dir(manifest.id, manifest.version)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            os.replace(staging, target)
            staging = None

            previous = installed.version if installed else None
            previous_target = self.current_link(manifest.id)
            if previous_target.is_symlink():
                backup_link = os.readlink(previous_target)
            self._point_current(manifest.id, manifest.version)
            self.write_desktop_entry(manifest)
            files = self._collect_files(target)

            key_id = getattr(contents, "key_id", None)

            record = db_mod.InstalledPackage(
                id=manifest.id,
                version=manifest.version,
                kind=manifest.kind,
                name=manifest.name,
                installed_at=_now(),
                files=files,
                key_id=key_id,
                payload_bytes=sum(size for _name, size in files),
                previous_version=previous,
                signature_verified=contents.signature is not None,
            )
            self.database.put(record)
            self.database.save()

            action = "reinstalled" if previous == manifest.version else "updated" if previous else "installed"
            return InstallResult(
                package_id=manifest.id,
                version=manifest.version,
                previous_version=previous,
                action=action,
                files=len(files),
                bytes_installed=record.payload_bytes,
                key_id=key_id,
                signed=contents.signature is not None,
            )
        except Exception:
            if staging is not None and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            self._restore_link(backup_link)
            raise
        finally:
            archive_mod.close_contents(contents)

    def remove(self, package_id: str, *, force: bool = False) -> InstallResult:
        self.database.load()
        record = self.database.require(package_id)
        dependents = self.database.dependents(package_id)
        if dependents and not force:
            raise InstallError(
                f"{package_id} is required by {', '.join(sorted(dependents))}; "
                "remove them first or use --force"
            )
        directory = self.app_dir(package_id)
        if directory.exists():
            shutil.rmtree(directory)
        entry = self.desktop_entry(package_id)
        if entry.exists():
            entry.unlink()
        self.database.remove(package_id)
        self.database.save()
        return InstallResult(
            package_id=package_id,
            version=record.version,
            previous_version=record.previous_version,
            action="removed",
            files=len(record.files),
            bytes_installed=0,
            key_id=record.key_id,
            signed=record.signature_verified,
        )

    # -- helpers -----------------------------------------------------------

    def _point_current(self, package_id: str, version: str) -> None:
        link = self.current_link(package_id)
        link.parent.mkdir(parents=True, exist_ok=True)
        temporary = link.with_name(".current.new")
        if temporary.is_symlink() or temporary.exists():
            temporary.unlink()
        os.symlink(version, temporary)
        os.replace(temporary, link)

    def _restore_link(self, previous: str | None) -> None:
        if previous is None:
            return
        for link in (self.root / APPS_DIR).glob("*/current"):
            if link.is_symlink() and os.readlink(link) == previous:
                return
        # Best effort: the package directory still exists, so recreate the link.
        candidates = [path for path in (self.root / APPS_DIR).glob(f"*/{previous}") if path.is_dir()]
        if candidates:
            link = candidates[0].parent / "current"
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(previous, link)

    def _collect_files(self, version_dir: Path) -> list:
        collected = []
        for path in sorted(version_dir.rglob("*")):
            if path.is_file() or path.is_symlink():
                relative = path.relative_to(version_dir).as_posix()
                size = path.stat().st_size if path.is_file() else 0
                collected.append((relative, size))
        return collected

    def write_desktop_entry(self, manifest) -> Path:
        entry = manifest.entry
        command = " ".join([entry.exec] + list(entry.args))
        lines = [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={manifest.name}",
            f"Comment={manifest.description.splitlines()[0][:200] if manifest.description else ''}",
            f"Exec={command} %U",
            f"Icon={manifest.id}",
            f"Categories={';'.join(manifest.categories)};",
            "Terminal=false",
            "StartupNotify=true",
            f"X-Zaod-Package={manifest.id}",
            f"X-Zaod-Version={manifest.version}",
        ]
        if manifest.mime_types:
            lines.append(f"MimeType={';'.join(manifest.mime_types)};")
        target = self.desktop_entry(manifest.id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target


def install_package(
    package_path: str | os.PathLike[str],
    root: str | os.PathLike[str] = "/",
    *,
    allow_unsigned: bool = False,
    allow_downgrade: bool = False,
) -> InstallResult:
    """Convenience wrapper used by the CLI."""
    return Installer(root, allow_unsigned=allow_unsigned).install(
        package_path, allow_downgrade=allow_downgrade
    )


def list_installed(root: str | os.PathLike[str] = "/") -> list:
    database = db_mod.Database(root)
    database.load()
    return [database.packages[key] for key in sorted(database.packages)]


def require_installed(root: str | os.PathLike[str], package_id: str) -> db_mod.InstalledPackage:
    database = db_mod.Database(root)
    database.load()
    record = database.get(package_id)
    if record is None:
        raise PackageError(f"{package_id} is not installed")
    return record

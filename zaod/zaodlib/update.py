"""Signed, rollback-capable update bundles.

A bundle is a ``.zaodbundle`` archive holding the packages of one release step:

```
bundle.json      format, base_version, target_version, notes, packages[]
CHECKSUMS        sha256 of bundle.json and every package file
SIGNATURE        Ed25519 over bundle.json + CHECKSUMS (same scheme as packages)
packages/*.zaod  the packages this step installs
```

Applying a bundle is a transaction over the *system state*: before each package is
installed, the currently installed version is repacked into the journal directory.
If any package fails, everything already installed in this run is restored from the
journal, so a half-applied update is impossible.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import archive, keys, pack, util, verify
from .errors import HashError, RepoError, SignatureError, StateError

BUNDLE_FORMAT = 1


@dataclass
class Bundle:
    path: Path
    base_version: str
    target_version: str
    notes: str
    packages: list = field(default_factory=list)
    sha256: str = ""
    key_id: str | None = None

    @property
    def signed(self) -> bool:
        return self.key_id is not None


@dataclass
class ApplyReport:
    target_version: str
    installed: list = field(default_factory=list)
    journal: Path | None = None


def _write_checksums(root: Path, names: list[str]) -> tuple[dict, bytes]:
    checksums = {name: util.sha256_file(root / name) for name in sorted(names)}
    text = "".join(f"{digest}  {name}\n" for name, digest in checksums.items())
    data = text.encode("utf-8")
    (root / "CHECKSUMS").write_bytes(data)
    return checksums, data


def create_bundle(
    packages: list,
    output: Path,
    *,
    base_version: str,
    target_version: str,
    notes: str = "",
    key: Path | None = None,
    level: int = 12,
) -> Bundle:
    """Create a bundle from package files, signed when ``key`` (a private key path) is given."""
    packages = [Path(package) for package in packages]
    if not packages:
        raise StateError("a bundle needs at least one package")
    for package in packages:
        if not package.is_file():
            raise StateError(f"package not found: {package}")
    output = Path(output)
    staging = Path(tempfile.mkdtemp(prefix="zaodbundle-"))
    try:
        root = staging / "bundle"
        (root / "packages").mkdir(parents=True)
        entries = []
        for package in packages:
            target = root / "packages" / package.name
            shutil.copy2(package, target)
            entries.append({"file": f"packages/{package.name}", "sha256": util.sha256_file(target)})
        document = {
            "format": BUNDLE_FORMAT,
            "base_version": base_version,
            "target_version": target_version,
            "notes": notes,
            "packages": entries,
        }
        bundle_bytes = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        (root / "bundle.json").write_bytes(bundle_bytes)
        _checksums, checksums_bytes = _write_checksums(
            root, ["bundle.json"] + [entry["file"] for entry in entries]
        )
        key_id = None
        if key is not None:
            keypair = keys.load_private_key(Path(key))
            signature = keys.signature_document(keypair, verify.signable_bytes(bundle_bytes, checksums_bytes))
            (root / "SIGNATURE").write_text(json.dumps(signature, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            key_id = keypair.key_id
        output.parent.mkdir(parents=True, exist_ok=True)
        archive.compress_tree(root, output, level=level)
        return Bundle(
            path=output,
            base_version=base_version,
            target_version=target_version,
            notes=notes,
            packages=entries,
            sha256=util.sha256_file(output),
            key_id=key_id if key_id else None,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_bundle(path: Path, keyring: dict | None = None, *, allow_unsigned: bool = False) -> Bundle:
    """Check the archive contents, hashes and signature of a bundle."""
    path = Path(path)
    keyring = keyring or {}
    staging = Path(tempfile.mkdtemp(prefix="zaodbundle-verify-"))
    try:
        archive.extract_tree(path, staging)
        document_file = staging / "bundle.json"
        if not document_file.is_file():
            raise RepoError("bundle has no bundle.json")
        document = json.loads(document_file.read_text(encoding="utf-8"))
        if document.get("format") != BUNDLE_FORMAT:
            raise RepoError(f"unsupported bundle format {document.get('format')!r}")
        checksums_file = staging / "CHECKSUMS"
        if not checksums_file.is_file():
            raise HashError("bundle has no CHECKSUMS")
        expected = verify.parse_checksums(checksums_file.read_text(encoding="utf-8"))
        for name, digest in expected.items():
            target = staging / name
            if not target.is_file():
                raise HashError(f"bundle is missing {name}")
            if util.sha256_file(target) != digest:
                raise HashError(f"bundle file {name} does not match its checksum")
        signature_file = staging / "SIGNATURE"
        key_id = None
        if signature_file.is_file():
            key_id, signature = keys.parse_signature(json.loads(signature_file.read_text(encoding="utf-8")))
            if key_id not in keyring:
                if not allow_unsigned:
                    raise SignatureError(f"bundle signing key {key_id} is not trusted on this system")
            else:
                keys.verify_with_keyring(
                    keyring,
                    key_id,
                    verify.signable_bytes(document_file.read_bytes(), checksums_file.read_bytes()),
                    signature,
                )
        elif not allow_unsigned:
            raise SignatureError("bundle is unsigned; signed update bundles are required")
        return Bundle(
            path=path,
            base_version=document.get("base_version", ""),
            target_version=document.get("target_version", ""),
            notes=document.get("notes", ""),
            packages=document.get("packages", []),
            sha256=util.sha256_file(path),
            key_id=key_id,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _journal_for(paths, target_version: str) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    journal = paths.state_dir / "updates" / f"{stamp}-{target_version or 'unknown'}"
    journal.mkdir(parents=True, exist_ok=True)
    return journal


def _installed_version_dir(paths, app_id: str) -> Path | None:
    current = paths.app_dir(app_id) / "current"
    return current.resolve() if current.exists() else None


def _repack_installed(paths, app_id: str, version: str, target: Path) -> None:
    """Copy an installed version back into a package file so it can be restored."""
    source = paths.app_dir(app_id) / version
    if not source.is_dir():
        raise StateError(f"cannot snapshot {app_id} {version}: the installed tree is missing")
    staging = Path(tempfile.mkdtemp(prefix="zaod-rollback-"))
    try:
        copy = staging / "app"
        shutil.copytree(source, copy, symlinks=False)
        # The installed tree is read-only; the snapshot has to be rewritten before
        # it can be repacked, which fails with EACCES for a normal user otherwise.
        util.make_writable(copy)
        pack.build_package(copy, target, level=6)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _write_journal(journal: Path, data: dict) -> None:
    (journal / "journal.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def apply_bundle(
    paths,
    bundle_path: Path,
    *,
    installer=None,
    allow_unsigned: bool = False,
    keyring=None,
) -> ApplyReport:
    """Install every package of a bundle, rolling back if any step fails."""
    from .install import Installer, verify_package

    keyring = keyring or keys.trusted_keys(paths.keys_dir)
    bundle = verify_bundle(bundle_path, keyring, allow_unsigned=allow_unsigned)
    installer = installer or Installer(paths, keyring=keyring)
    journal = _journal_for(paths, bundle.target_version)
    staging = Path(tempfile.mkdtemp(prefix="zaodbundle-apply-"))
    journal_data = {"bundle": str(bundle_path), "target": bundle.target_version, "previous": [], "installed": []}
    try:
        archive.extract_tree(bundle_path, staging)
        installed_now = []
        try:
            for entry in bundle.packages:
                package = staging / entry["file"]
                verified_app = verify_package(paths, package, allow_unsigned=allow_unsigned)
                app_id = verified_app.manifest.id
                previous_version = installer.current_version(app_id)
                if previous_version:
                    snapshot = journal / f"{app_id}-{previous_version}.zaod"
                    _repack_installed(paths, app_id, previous_version, snapshot)
                    journal_data["previous"].append(
                        {"id": app_id, "version": previous_version, "package": snapshot.name}
                    )
                else:
                    journal_data["previous"].append({"id": app_id, "version": None, "package": None})
                _write_journal(journal, journal_data)
                installer.install(package, source="bundle", allow_unsigned=allow_unsigned, force=True)
                installed_now.append(app_id)
                journal_data["installed"] = installed_now
                _write_journal(journal, journal_data)
        except Exception as error:
            journal_data["error"] = str(error)
            _write_journal(journal, journal_data)
            rollback_journal(paths, journal, installer=installer)
            raise StateError(f"update failed and was rolled back: {error}") from error
        return ApplyReport(target_version=bundle.target_version, installed=installed_now, journal=journal)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def rollback_journal(paths, journal: Path, *, installer=None) -> list:
    """Restore the versions recorded in a journal, newest change first."""
    from .install import Installer

    journal = Path(journal)
    data_file = journal / "journal.json"
    if not data_file.is_file():
        raise StateError(f"no journal at {journal}")
    data = json.loads(data_file.read_text(encoding="utf-8"))
    installer = installer or Installer(paths)
    restored = []
    for entry in reversed(data.get("previous", [])):
        app_id = entry["id"]
        if entry.get("version") is None:
            if installer.current_version(app_id):
                installer.remove(app_id)
                restored.append(f"removed {app_id}")
            continue
        version = entry["version"]
        version_dir = paths.app_dir(app_id) / version
        if version_dir.is_dir():
            # The old version was never deleted, so rollback is a pointer change:
            # switch `current` back and restore the database record.
            util.atomic_symlink(paths.app_current(app_id), version)
            record = installer.db.get(app_id) or {}
            record.update({"version": version, "path": version, "source": "rollback"})
            with installer.db.locked():
                installer.db.record(app_id, record)
            restored.append(f"{app_id} {version}")
            continue
        package = journal / entry["package"]
        if not package.is_file():
            raise StateError(f"rollback snapshot for {app_id} is missing: {package}")
        installer.install(package, source="rollback", allow_unsigned=True, force=True)
        restored.append(f"{app_id} {version}")
    data["rolled_back"] = True
    data["restored"] = restored
    _write_journal(journal, data)
    return restored

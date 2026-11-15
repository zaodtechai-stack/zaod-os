"""Verification of an extracted ``.zaod`` package before it is installed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import keys, util
from .errors import HashError, ManifestError, SignatureError
from .manifest import Manifest, load_manifest

RESERVED = {"MANIFEST.json", "CHECKSUMS", "SIGNATURE"}


@dataclass
class VerifiedPackage:
    manifest: Manifest
    root: Path
    key_id: str | None
    checksums: dict[str, str]

    @property
    def signed(self) -> bool:
        return self.key_id is not None

    @property
    def payload_dir(self) -> Path:
        return self.root / "payload"

    def payload_path(self, relative: str) -> Path:
        return self.root / util.ensure_safe_relative(relative)


def parse_checksums(text: str) -> dict[str, str]:
    """Parse a sorted ``<sha256>  <path>`` checksum list."""
    result: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            raise ManifestError(f"CHECKSUMS line {number}: expected '<sha256>  <path>'")
        digest, path = parts[0].lower(), parts[1].strip()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ManifestError(f"CHECKSUMS line {number}: {digest!r} is not a sha256 digest")
        safe = util.ensure_safe_relative(path, f"CHECKSUMS line {number}")
        if safe in result:
            raise ManifestError(f"CHECKSUMS line {number}: duplicate entry for {safe}")
        result[safe] = digest
    if not result:
        raise ManifestError("CHECKSUMS is empty")
    return result


def signable_bytes(manifest_bytes: bytes, checksums_bytes: bytes) -> bytes:
    """Data covered by a package signature: raw MANIFEST.json plus CHECKSUMS."""
    return manifest_bytes + b"\n" + checksums_bytes


def _payload_files(root: Path) -> set[str]:
    found: set[str] = set()
    for item in sorted(root.rglob("*")):
        if item.is_dir() and not item.is_symlink():
            continue
        found.add(item.relative_to(root).as_posix())
    return found


def verify_staged(
    root: Path,
    *,
    keyring: dict[str, bytes] | None = None,
    allow_unsigned: bool = False,
    os_version: str = "0.7.0",
    arch: str = "x86_64",
) -> VerifiedPackage:
    """Verify manifest, checksums and signature of an extracted package."""
    root = Path(root)
    manifest_file = root / "MANIFEST.json"
    if not manifest_file.is_file():
        raise ManifestError("package has no MANIFEST.json")
    manifest_bytes = manifest_file.read_bytes()
    manifest = load_manifest(manifest_file)

    checksums_file = root / "CHECKSUMS"
    if not checksums_file.is_file():
        raise ManifestError(f"{manifest.id}: package has no CHECKSUMS file")
    checksums_bytes = checksums_file.read_bytes()
    checksums = parse_checksums(checksums_bytes.decode("utf-8"))

    signature_file = root / "SIGNATURE"
    key_id: str | None = None
    if signature_file.is_file():
        try:
            document = json.loads(signature_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SignatureError(f"{manifest.id}: SIGNATURE is not valid JSON: {exc}") from exc
        key_id, signature = keys.parse_signature(document)
        keys.verify_with_keyring(
            keyring or {}, key_id, signable_bytes(manifest_bytes, checksums_bytes), signature
        )
    elif not allow_unsigned:
        raise SignatureError(
            f"{manifest.id} {manifest.version} is unsigned; signed store packages are required "
            "and unsigned developer packages need explicit confirmation"
        )

    present = _payload_files(root) - RESERVED
    listed = set(checksums)
    missing = sorted(listed - present)
    if missing:
        raise HashError(f"{manifest.id}: files listed in CHECKSUMS are missing: {', '.join(missing[:5])}")
    extra = sorted(present - listed)
    if extra:
        raise HashError(f"{manifest.id}: files not listed in CHECKSUMS: {', '.join(extra[:5])}")
    for relative, digest in checksums.items():
        actual = util.sha256_file(root / relative)
        if actual != digest:
            raise HashError(f"{manifest.id}: {relative} is tampered or corrupt (sha256 {actual}, expected {digest})")

    if manifest.kind in ("app", "project"):
        entry = manifest.entry.get("exec")
        if not entry or entry not in checksums:
            raise ManifestError(f"{manifest.id}: entry.exec {entry!r} is not part of the package payload")
    manifest.check_compatibility(os_version, arch)
    return VerifiedPackage(manifest=manifest, root=root, key_id=key_id, checksums=checksums)

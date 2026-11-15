"""Build and sign ``.zaod`` packages from a prepared source directory."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from . import archive, keys, util
from .errors import ManifestError, UsageError
from .manifest import Manifest, load_manifest
from .verify import signable_bytes, verify_staged

RESERVED = {"MANIFEST.json", "CHECKSUMS", "SIGNATURE"}


def write_checksums(source: Path) -> tuple[dict[str, str], bytes]:
    """Write a sorted ``CHECKSUMS`` file into ``source`` and return its data."""
    entries: list[tuple[str, str]] = []
    for item in sorted(Path(source).rglob("*")):
        if item.is_dir() and not item.is_symlink():
            continue
        relative = item.relative_to(source).as_posix()
        if relative in RESERVED:
            continue
        entries.append((util.sha256_file(item), relative))
    if not entries:
        raise ManifestError(f"{source}: nothing to package (payload is empty)")
    entries.sort(key=lambda pair: pair[1])
    text = "".join(f"{digest}  {path}\n" for digest, path in entries)
    target = Path(source) / "CHECKSUMS"
    target.write_text(text, encoding="utf-8")
    return {path: digest for digest, path in entries}, text.encode()


def build_package(
    source: Path,
    output: Path,
    *,
    manifest_path: Path | None = None,
    private_key: Path | None = None,
    level: int = 19,
) -> tuple[Path, Manifest, dict[str, str]]:
    """Validate ``source``, write CHECKSUMS, optionally sign, and compress."""
    source = Path(source)
    output = Path(output)
    manifest_file = Path(manifest_path) if manifest_path else source / "MANIFEST.json"
    if not manifest_file.is_file():
        raise ManifestError(f"manifest not found: {manifest_file}")
    manifest = load_manifest(manifest_file)
    # Normalise the stored manifest so packaging is byte-reproducible, then
    # sign exactly the bytes that ship inside the archive.
    normalised = json.dumps(manifest.raw, indent=2, sort_keys=True).encode() + b"\n"
    manifest_target = source / "MANIFEST.json"
    manifest_target.write_bytes(normalised)
    manifest = load_manifest(manifest_target)
    manifest_bytes = manifest_target.read_bytes()

    if manifest.kind in ("app", "project"):
        entry = source / manifest.entry["exec"]
        if not entry.is_file():
            raise ManifestError(f"{manifest.id}: entry.exec {manifest.entry['exec']} does not exist in the source")
        if not (entry.stat().st_mode & 0o111):
            raise UsageError(f"{manifest.id}: entry.exec {manifest.entry['exec']} is not executable")

    checksums, checksums_bytes = write_checksums(source)
    keyring: dict[str, bytes] = {}
    if private_key is not None:
        key = keys.load_private_key(private_key)
        signature = keys.signature_document(key, signable_bytes(manifest_bytes, checksums_bytes))
        (source / "SIGNATURE").write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")
        keyring[key.key_id] = key.public
    else:
        (source / "SIGNATURE").unlink(missing_ok=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zaod-pack-") as tmp:
        staging = Path(tmp) / "staging"
        staging.mkdir()
        for item in sorted(source.iterdir()):
            target = staging / item.name
            if item.is_dir():
                shutil.copytree(item, target, symlinks=True)
            else:
                shutil.copy2(item, target)
        archive.compress_tree(staging, output, level=level)

    with tempfile.TemporaryDirectory(prefix="zaod-selfcheck-") as check:
        archive.extract_tree(output, Path(check))
        verify_staged(
            Path(check),
            keyring=keyring,
            allow_unsigned=private_key is None,
            os_version=max(manifest.min_os, util_full_version(manifest)),
        )
    return output, manifest, checksums


def util_full_version(manifest: Manifest) -> str:
    """Return the manifest's own ``min_os`` so the self-check never rejects it."""
    return manifest.min_os


def sign_existing(package: Path, private_key: Path) -> Path:
    """Sign an already-built ``.zaod`` archive in place."""
    package = Path(package)
    key = keys.load_private_key(private_key)
    with tempfile.TemporaryDirectory(prefix="zaod-sign-") as tmp:
        work = Path(tmp) / "pkg"
        archive.extract_tree(package, work)
        manifest = load_manifest(work / "MANIFEST.json")
        manifest_bytes = (work / "MANIFEST.json").read_bytes()
        checksums_bytes = (work / "CHECKSUMS").read_bytes()
        signature = keys.signature_document(key, signable_bytes(manifest_bytes, checksums_bytes))
        (work / "SIGNATURE").write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")
        archive.compress_tree(work, package, level=19)
        with tempfile.TemporaryDirectory(prefix="zaod-signcheck-") as check:
            archive.extract_tree(package, Path(check))
            verify_staged(Path(check), keyring={key.key_id: key.public}, os_version=manifest.min_os)
    return package

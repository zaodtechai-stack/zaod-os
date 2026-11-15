"""Build a ``.zaod`` package from a source directory.

Source layout::

    MANIFEST.json          required, validated by :mod:`zaod.manifest`
    icon.svg | icon.png    optional but referenced by the manifest by default
    screenshots/*.png      optional
    payload/**             everything that gets installed

Passing a private key signs the package. The archive is deterministic: fixed
member metadata, sorted member order, canonical MANIFEST.json.
"""

from __future__ import annotations

from pathlib import Path

from . import archive as archive_mod
from . import manifest as manifest_mod
from . import signature as signature_mod
from .errors import PackageError

EXTRA_ROOTS = ("screenshots",)


def collect_extra_files(source: Path, manifest) -> dict:
    """Manifest-referenced files that live outside ``payload/``."""
    extras = {}
    icon = source / manifest.icon
    if icon.is_file():
        extras[manifest.icon] = icon
    for relative in manifest.screenshots:
        candidate = source / relative
        if candidate.is_file():
            extras[relative] = candidate
    return extras


def build_package(
    source: str | Path,
    output: str | Path,
    *,
    private_key: bytes | None = None,
    compressor=None,
) -> Path:
    """Pack ``source`` into ``output`` and return the archive path."""
    directory = Path(source)
    if not directory.is_dir():
        raise PackageError(f"source directory does not exist: {directory}")
    manifest_path = directory / manifest_mod.MANIFEST_NAME
    if not manifest_path.is_file():
        raise PackageError(f"{manifest_path} is missing")
    manifest = manifest_mod.load(manifest_path)
    payload = directory / "payload"
    payload_dir = payload if payload.is_dir() and manifest.has_payload else None

    manifest_bytes = manifest.canonical_bytes()
    signature = None
    if private_key is not None:
        checksums_bytes = archive_mod.build_checksums(
            payload_dir=payload_dir,
            extra_files=collect_extra_files(directory, manifest),
        )
        signature = signature_mod.sign_package(manifest_bytes, checksums_bytes, private_key)

    return archive_mod.build_archive(
        manifest_bytes=manifest_bytes,
        payload_dir=payload_dir,
        output=output,
        extra_files=collect_extra_files(directory, manifest),
        compressor=compressor,
        signature=signature,
    )

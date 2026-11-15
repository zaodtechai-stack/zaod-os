"""Small helpers shared across the package manager."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

from .errors import ManifestError, UsageError

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(obj) -> bytes:
    """Stable JSON encoding used for signing and hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_semver(value: str, field: str = "version") -> tuple[int, int, int]:
    if not isinstance(value, str) or not SEMVER_RE.match(value):
        raise ManifestError(f"{field}: expected MAJOR.MINOR.PATCH, got {value!r}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def compare_semver(left: str, right: str) -> int:
    a, b = parse_semver(left), parse_semver(right)
    return (a > b) - (a < b)


def atomic_write_bytes(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def atomic_symlink(link: Path, target: str) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    tmp = link.with_name(f".{link.name}.tmp-{os.getpid()}")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, link)


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"  # pragma: no cover - unreachable


def remove_tree(path: Path) -> None:
    """Remove a file, symlink or directory tree, tolerating missing paths."""
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink(missing_ok=True)
        return
    if not path.is_dir():
        return

    def restore_write(function, target, _error) -> None:
        # Installed applications live in a read-only store, so removal has to
        # make each directory writable on the way down instead of failing with
        # EACCES for an unprivileged user.
        mode = stat.S_IMODE(os.lstat(target).st_mode)
        os.chmod(target, mode | 0o200)
        function(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=restore_write)
    else:  # pragma: no cover - the shipped image is Python 3.13
        shutil.rmtree(path, onerror=lambda func, target, _info: restore_write(func, target, None))


def make_read_only(root: Path) -> None:
    """Drop write permission from every directory and file below ``root``."""
    for current, dirs, files in os.walk(root, topdown=False):
        for name in files:
            target = Path(current) / name
            if target.is_symlink():
                continue
            mode = stat.S_IMODE(target.stat().st_mode)
            os.chmod(target, mode & ~0o222)
        for name in dirs:
            target = Path(current) / name
            if target.is_symlink():
                continue
            mode = stat.S_IMODE(target.stat().st_mode)
            os.chmod(target, mode & ~0o222)
    os.chmod(root, stat.S_IMODE(root.stat().st_mode) & ~0o222)


def ensure_safe_relative(path: str, field: str = "path") -> str:
    """Reject absolute paths and parent traversal in manifest-provided paths."""
    if not isinstance(path, str) or not path:
        raise UsageError(f"{field}: expected a non-empty relative path")
    if path.startswith("/") or "\\" in path:
        raise UsageError(f"{field}: must be a relative POSIX path, got {path!r}")
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise UsageError(f"{field}: must not contain '..', got {path!r}")
    return "/".join(parts)

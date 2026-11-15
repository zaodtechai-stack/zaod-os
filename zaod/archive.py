"""``.zaod`` archive construction, inspection and safe extraction.

Layout of a v1 package (a zstd-compressed POSIX tar)::

    MANIFEST.json      canonical UTF-8 JSON, see :mod:`zaod.manifest`
    CHECKSUMS          every member except MANIFEST.json and SIGNATURE
    SIGNATURE          128 hex characters, Ed25519 over the signed document
    icon.svg | icon.png
    screenshots/*.png
    payload/**         the files that are installed

Safety rules enforced here, not by convention:

* member names must be relative, forward-slash separated, free of ``..``,
  backslashes, drive letters and control characters
* only regular files, directories and symlinks are allowed; hard links,
  devices and FIFOs are rejected
* symlink targets must stay inside the package
* archive bombs are bounded by member count, per-file size, total size and a
  compression-ratio ceiling
* extraction writes regular files and directories first and symlinks last,
  each with ``O_NOFOLLOW | O_EXCL``
"""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import checksums as checksums_mod
from . import compress as compress_mod
from .errors import ArchiveError, UnsafeArchiveError

MANIFEST_NAME = "MANIFEST.json"
CHECKSUMS_NAME = "CHECKSUMS"
SIGNATURE_NAME = "SIGNATURE"
PAYLOAD_PREFIX = "payload/"

#: Fixed member metadata, so two builds of the same input are byte identical.
SOURCE_DATE_EPOCH = 1_704_067_200  # 2024-01-01T00:00:00Z
FIXED_UID = 0
FIXED_GID = 0


@dataclass(frozen=True)
class Limits:
    """Hard bounds applied to any archive we read."""

    max_members: int = 20_000
    max_file_bytes: int = 2 * 1024**3
    max_total_bytes: int = 8 * 1024**3
    max_ratio: int = 400

    def check_members(self, count: int) -> None:
        if count > self.max_members:
            raise UnsafeArchiveError(f"archive has {count} members, limit is {self.max_members}")

    def check_file(self, size: int, name: str) -> None:
        if size > self.max_file_bytes:
            raise UnsafeArchiveError(f"member {name} is {size} bytes, per-file limit is {self.max_file_bytes}")

    def check_total(self, total: int, compressed: int) -> None:
        if total > self.max_total_bytes:
            raise UnsafeArchiveError(f"uncompressed size {total} exceeds {self.max_total_bytes}")
        if compressed > 0 and total / compressed > self.max_ratio:
            raise UnsafeArchiveError(
                f"compression ratio {total // max(compressed, 1)}:1 exceeds {self.max_ratio}:1"
            )


DEFAULT_LIMITS = Limits()


def safe_member_name(name: str) -> str:
    """Validate and normalise one archive member name."""
    if not name or name in {".", "./"}:
        raise UnsafeArchiveError("empty member name")
    normalised = name.replace("\\", "/")
    if "\\" in name:
        raise UnsafeArchiveError(f"backslash in member name: {name!r}")
    if normalised.startswith("/"):
        raise UnsafeArchiveError(f"absolute member path: {name!r}")
    if len(normalised) > 1 and normalised[1] == ":":
        raise UnsafeArchiveError(f"drive-letter member path: {name!r}")
    parts = []
    for part in normalised.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise UnsafeArchiveError(f"parent traversal in member path: {name!r}")
        if any(ord(char) < 32 for char in part):
            raise UnsafeArchiveError(f"control character in member path: {name!r}")
        parts.append(part)
    if not parts:
        raise UnsafeArchiveError(f"member path resolves to nothing: {name!r}")
    return "/".join(parts)


def _tarinfo(name: str, mode: int, *, size: int = 0, kind: bytes = tarfile.REGTYPE) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = mode
    info.uid = FIXED_UID
    info.gid = FIXED_GID
    info.uname = "root"
    info.gname = "root"
    info.mtime = SOURCE_DATE_EPOCH
    info.type = kind
    return info


def _iter_payload(payload_dir: Path) -> list:
    """Sorted relative paths of everything under ``payload_dir``."""
    entries = []
    for path in sorted(payload_dir.rglob("*")):
        relative = path.relative_to(payload_dir).as_posix()
        entries.append((relative, path))
    return sorted(entries, key=lambda item: item[0])


def build_checksums(*, payload_dir, extra_files=None) -> bytes:
    """Compute the CHECKSUMS document for a package without writing an archive.

    Signing needs the checksum document before the archive exists, so this
    mirrors the collection half of :func:`build_archive`.
    """
    collected = _collect_files(payload_dir, extra_files)
    entries = []
    for name, source in collected:
        data = bytes(source) if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
        entries.append(
            checksums_mod.ChecksumEntry(
                path=name, size=len(data), sha256=checksums_mod.sha256_bytes(data)
            )
        )
    return checksums_mod.format_checksums(entries)


def _collect_files(payload_dir, extra_files) -> list:
    """``[(archive_name, bytes | Path)]`` in sorted archive order."""
    collected = []
    if payload_dir is not None:
        root = Path(payload_dir)
        if not root.is_dir():
            raise ArchiveError(f"payload directory does not exist: {root}")
        for relative, path in _iter_payload(root):
            if path.is_symlink() or path.is_dir():
                continue
            collected.append((f"{PAYLOAD_PREFIX}{relative}", path))
    for name, source in (extra_files or {}).items():
        collected.append((safe_member_name(name), source))
    collected.sort(key=lambda item: item[0])
    return collected


def build_archive(
    *,
    manifest_bytes: bytes,
    payload_dir: Path | str | None,
    output: Path | str,
    extra_files: dict | None = None,
    compressor=None,
    signature: bytes | None = None,
) -> Path:
    """Write a deterministic ``.zaod`` archive and return its path.

    ``extra_files`` maps an archive-relative name (for example ``icon.svg`` or
    ``screenshots/main.png``) to file contents or a source path.
    ``signature`` is the raw 64-byte Ed25519 signature; when omitted the archive
    is written unsigned and carries no SIGNATURE member.
    """
    output_path = Path(output)
    extra_files = dict(extra_files or {})
    collected: list = []

    if payload_dir is not None:
        root = Path(payload_dir)
        if not root.is_dir():
            raise ArchiveError(f"payload directory does not exist: {root}")
        for relative, path in _iter_payload(root):
            if path.is_symlink():
                target = os.readlink(path)
                if os.path.isabs(target) or ".." in Path(target).parts:
                    raise UnsafeArchiveError(f"payload symlink escapes the package: {relative}")
                collected.append((f"{PAYLOAD_PREFIX}{relative}", "symlink", target))
            elif path.is_dir():
                collected.append((f"{PAYLOAD_PREFIX}{relative}", "dir", None))
            elif path.is_file():
                collected.append((f"{PAYLOAD_PREFIX}{relative}", "file", path))
            else:
                raise ArchiveError(f"unsupported payload entry: {relative}")

    for name, source in extra_files.items():
        safe_member_name(name)
        collected.append((safe_member_name(name), "file", source))

    collected.sort(key=lambda item: item[0])

    entries = []
    for name, kind, source in collected:
        if kind != "file":
            continue
        if isinstance(source, (bytes, bytearray)):
            data = bytes(source)
        else:
            data = Path(source).read_bytes()
        entries.append(
            checksums_mod.ChecksumEntry(
                path=name,
                size=len(data),
                sha256=checksums_mod.sha256_bytes(data),
            )
        )
    checksums_bytes = checksums_mod.format_checksums(entries)

    members: list = [
        (MANIFEST_NAME, "file", manifest_bytes),
        (CHECKSUMS_NAME, "file", checksums_bytes),
    ]
    if signature is not None:
        if len(signature) != 64:
            raise ArchiveError("signature must be 64 raw bytes")
        members.append((SIGNATURE_NAME, "file", signature.hex().encode("ascii")))

    for name, kind, source in collected:
        if kind == "file":
            if isinstance(source, (bytes, bytearray)):
                members.append((name, "file", bytes(source)))
            else:
                members.append((name, "file", Path(source)))
        elif kind == "dir":
            members.append((name, "dir", None))
        else:
            members.append((name, "symlink", source))

    members.sort(key=lambda item: item[0])

    with tempfile.TemporaryDirectory(prefix="zaod-pack-") as scratch:
        tar_path = Path(scratch) / "package.tar"
        with tarfile.open(tar_path, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, kind, source in members:
                if kind == "dir":
                    archive.addfile(_tarinfo(name, 0o755, kind=tarfile.DIRTYPE))
                elif kind == "symlink":
                    info = _tarinfo(name, 0o777, kind=tarfile.SYMTYPE)
                    info.linkname = str(source)
                    archive.addfile(info)
                else:
                    if isinstance(source, (bytes, bytearray)):
                        import io

                        data = bytes(source)
                        archive.addfile(_tarinfo(name, 0o644, size=len(data)), io.BytesIO(data))
                    else:
                        file_path = Path(source)
                        data = file_path.read_bytes()
                        archive.addfile(_tarinfo(name, 0o644, size=len(data)), io.BytesIO(data))

        chosen = compressor or compress_mod.auto_compressor()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial = output_path.with_suffix(output_path.suffix + ".partial")
        chosen.compress_file(str(tar_path), str(partial))
        os.replace(partial, output_path)
    return output_path


@dataclass
class PackageContents:
    """Everything a verified read of an archive yields."""

    manifest: object
    checksums: list
    signature: bytes | None
    members: dict
    tar_path: Path

    def payload_root(self) -> Path:
        """Directory holding the unpacked payload (or an empty temp dir)."""
        raise NotImplementedError


def _open_tar(archive_path: Path | str) -> tuple:
    """Decompress into a temporary tar and return ``(path, tempdir, compressed)``."""
    source = Path(archive_path)
    if not source.is_file():
        raise ArchiveError(f"no such package: {source}")
    with source.open("rb") as handle:
        head = handle.read(512)
    try:
        kind = compress_mod.detect_format(head)
    except Exception as exc:
        raise ArchiveError(str(exc)) from exc
    compressed_size = source.stat().st_size
    scratch = tempfile.mkdtemp(prefix="zaod-read-")
    tar_path = Path(scratch) / "package.tar"
    if kind == "zstd":
        compress_mod.auto_compressor().decompress_file(str(source), str(tar_path))
    else:
        shutil.copyfile(source, tar_path)
    return tar_path, Path(scratch), compressed_size


def inspect(archive_path: Path | str, limits: Limits = DEFAULT_LIMITS) -> PackageContents:
    """Read an archive, validate every member and return its contents.

    The caller owns the returned ``tar_path``; use :func:`close_contents` when
    finished so the temporary directory is removed.
    """
    from . import manifest as manifest_mod

    tar_path, scratch, compressed_size = _open_tar(archive_path)
    try:
        with tarfile.open(tar_path, mode="r:") as archive:
            members = archive.getmembers()
            limits.check_members(len(members))
            seen = set()
            total = 0
            resolved = {}
            for member in members:
                name = safe_member_name(member.name)
                if name in seen:
                    raise UnsafeArchiveError(f"duplicate member: {name}")
                seen.add(name)
                if member.isdir():
                    resolved[name] = ("dir", None)
                elif member.issym():
                    target = member.linkname
                    if os.path.isabs(target) or ".." in Path(target).parts:
                        raise UnsafeArchiveError(f"symlink {name} points outside the package")
                    resolved[name] = ("symlink", target)
                elif member.isfile():
                    limits.check_file(member.size, name)
                    total += member.size
                    resolved[name] = ("file", member.size)
                else:
                    raise UnsafeArchiveError(f"unsupported member type for {name}")
            limits.check_total(total, compressed_size)

            if MANIFEST_NAME not in resolved:
                raise ArchiveError("package has no MANIFEST.json")
            manifest_bytes = archive.extractfile(MANIFEST_NAME).read()
            checksum_bytes = (
                archive.extractfile(CHECKSUMS_NAME).read() if CHECKSUMS_NAME in resolved else b""
            )
            signature = None
            if SIGNATURE_NAME in resolved:
                raw = archive.extractfile(SIGNATURE_NAME).read().strip()
                try:
                    signature = bytes.fromhex(raw.decode("ascii"))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ArchiveError(f"SIGNATURE is not hex: {exc}") from exc
    except tarfile.TarError as exc:
        shutil.rmtree(scratch, ignore_errors=True)
        raise ArchiveError(f"archive is not a readable tar: {exc}") from exc
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise

    manifest = manifest_mod.loads(manifest_bytes)
    checksum_entries = checksums_mod.parse_checksums(checksum_bytes) if checksum_bytes else []
    return PackageContents(
        manifest=manifest,
        checksums=checksum_entries,
        signature=signature,
        members=resolved,
        tar_path=tar_path,
    )


def close_contents(contents: PackageContents) -> None:
    """Remove the temporary directory created by :func:`inspect`."""
    shutil.rmtree(contents.tar_path.parent, ignore_errors=True)


def verify_checksums(contents: PackageContents) -> None:
    """Verify every CHECKSUMS entry against the archive payload."""
    listed = {entry.path for entry in contents.checksums}
    present = {
        name
        for name, (kind, _) in contents.members.items()
        if kind == "file" and name not in {MANIFEST_NAME, CHECKSUMS_NAME, SIGNATURE_NAME}
    }
    missing = present - listed
    if missing:
        raise ArchiveError(f"members missing from CHECKSUMS: {sorted(missing)}")
    extra = listed - present
    if extra:
        raise ArchiveError(f"CHECKSUMS lists files not in the archive: {sorted(extra)}")

    with tarfile.open(contents.tar_path, mode="r:") as archive:
        for entry in contents.checksums:
            extracted = archive.extractfile(entry.path)
            if extracted is None:
                raise ArchiveError(f"cannot read {entry.path}")
            data = extracted.read()
            checksums_mod.verify_entry(
                entry,
                checksums_mod.sha256_bytes(data),
                len(data),
            )


def unpack(
    contents: PackageContents,
    destination: Path | str,
    limits: Limits = DEFAULT_LIMITS,
) -> Path:
    """Extract the payload of a verified package below ``destination``.

    Regular files and directories are created first, symlinks last. Every file
    is opened with ``O_CREAT | O_EXCL | O_NOFOLLOW`` so an existing symlink at
    the destination can never be followed.
    """
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    root_resolved = root.resolve()
    deferred_links = []

    with tarfile.open(contents.tar_path, mode="r:") as archive:
        for member in archive.getmembers():
            name = safe_member_name(member.name)
            target_path = root / name
            resolved = target_path.resolve() if target_path.parent.exists() else None
            if resolved is not None and root_resolved not in resolved.parents and resolved != root_resolved:
                raise UnsafeArchiveError(f"{name} escapes the destination")

            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                deferred_links.append((name, member.linkname, target_path))
            elif member.isfile():
                limits.check_file(member.size, name)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ArchiveError(f"cannot read member {name}")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                try:
                    descriptor = os.open(target_path, flags, 0o644)
                except FileExistsError as exc:
                    raise UnsafeArchiveError(f"refusing to overwrite {name}") from exc
                with os.fdopen(descriptor, "wb") as handle:
                    shutil.copyfileobj(source, handle)

    for name, link_target, target_path in deferred_links:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.is_symlink() or target_path.exists():
            raise UnsafeArchiveError(f"refusing to overwrite symlink {name}")
        os.symlink(link_target, target_path)
    return root


def read_icon(contents: PackageContents) -> bytes | None:
    """Return the archive icon bytes when the package ships one."""
    name = contents.manifest.icon
    if name not in contents.members:
        return None
    with tarfile.open(contents.tar_path, mode="r:") as archive:
        extracted = archive.extractfile(name)
        return extracted.read() if extracted else None

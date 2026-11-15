"""zstd-compressed tar handling for the ``.zaod`` package format.

Compression is provided by the system ``zstd`` binary when present, then by
the optional ``zstandard`` module, then by calling ``libzstd`` through
``ctypes``. The final fallback keeps the manager usable on a bare Zaod image
that only ships ``libzstd``.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import importlib.util
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .errors import PackageError

CONTENTSIZE_UNKNOWN = (1 << 64) - 1
CONTENTSIZE_ERROR = (1 << 64) - 2


def backend() -> str:
    if shutil.which("zstd"):
        return "cli"
    if importlib.util.find_spec("zstandard") is not None:  # pragma: no cover - optional module
        return "zstandard"
    if _load_libzstd() is not None:
        return "ctypes"
    raise PackageError("no zstd backend available: install the 'zstd' package or libzstd")


def _load_libzstd():
    for name in ("libzstd.so.1", "libzstd.so", ctypes.util.find_library("zstd")):
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            continue
        lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
        lib.ZSTD_compressBound.restype = ctypes.c_size_t
        lib.ZSTD_compress.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_int,
        ]
        lib.ZSTD_compress.restype = ctypes.c_size_t
        lib.ZSTD_decompress.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        lib.ZSTD_decompress.restype = ctypes.c_size_t
        lib.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
        lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        lib.ZSTD_isError.restype = ctypes.c_uint
        lib.ZSTD_getErrorName.argtypes = [ctypes.c_size_t]
        lib.ZSTD_getErrorName.restype = ctypes.c_char_p
        return lib
    return None


def _check(lib, code: int) -> int:
    if lib.ZSTD_isError(code):
        raise PackageError(f"libzstd error: {lib.ZSTD_getErrorName(code).decode()}")
    return code


def _run_zstd(args: list[str]) -> None:
    result = subprocess.run(["zstd", "-q", *args], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "unknown zstd failure").strip().splitlines()
        raise PackageError(f"zstd failed: {message[0] if message else 'unknown error'}")


def compress_file(source: Path, destination: Path, level: int = 19) -> None:
    source, destination = Path(source), Path(destination)
    kind = backend()
    if kind == "cli":
        _run_zstd(["-f", f"-{level}", "-T0", "-o", str(destination), str(source)])
        return
    if kind == "zstandard":
        import zstandard

        data = source.read_bytes()
        destination.write_bytes(zstandard.ZstdCompressor(level=level).compress(data))
        return
    lib = _load_libzstd()
    data = source.read_bytes()
    bound = lib.ZSTD_compressBound(len(data))
    buffer = ctypes.create_string_buffer(bound)
    written = _check(lib, lib.ZSTD_compress(buffer, bound, data, len(data), level))
    destination.write_bytes(buffer.raw[:written])


def decompress_file(source: Path, destination: Path) -> None:
    source, destination = Path(source), Path(destination)
    kind = backend()
    if kind == "cli":
        _run_zstd(["-f", "-d", "-o", str(destination), str(source)])
        return
    data = source.read_bytes()
    if kind == "zstandard":
        import zstandard

        destination.write_bytes(zstandard.ZstdDecompressor().decompress(data, max_output_size=1 << 34))
        return
    lib = _load_libzstd()
    size = lib.ZSTD_getFrameContentSize(data, len(data))
    if size in (CONTENTSIZE_UNKNOWN, CONTENTSIZE_ERROR):
        raise PackageError(
            f"{source.name}: zstd frame has no content size and no 'zstd' binary is available to stream it"
        )
    buffer = ctypes.create_string_buffer(size)
    written = _check(lib, lib.ZSTD_decompress(buffer, size, data, len(data)))
    destination.write_bytes(buffer.raw[:written])


def _safe_members(archive: tarfile.TarFile, destination: Path):
    root = destination.resolve()
    for member in archive.getmembers():
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            raise PackageError(f"archive member escapes the package root: {name!r}")
        if member.isdev():
            raise PackageError(f"archive member is a device or fifo: {name!r}")
        if member.issym() or member.islnk():
            target = Path(member.linkname)
            if target.is_absolute():
                raise PackageError(f"archive link is absolute: {name!r} -> {member.linkname!r}")
            resolved = (destination / Path(name).parent / target).resolve()
            if not str(resolved).startswith(str(root)):
                raise PackageError(f"archive link escapes the package root: {name!r}")
        yield member


def compress_tree(staging: Path, package: Path, level: int = 19) -> None:
    """Create ``package`` (a ``.zaod`` archive) from the contents of ``staging``."""
    staging, package = Path(staging), Path(package)
    with tempfile.NamedTemporaryFile(prefix="zaod-tar-", suffix=".tar", delete=False) as handle:
        tar_path = Path(handle.name)
    try:
        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
            for entry in sorted(staging.iterdir(), key=lambda item: item.name):
                archive.add(entry, arcname=entry.name, recursive=True, filter=_tar_filter)
        compress_file(tar_path, package, level=level)
    finally:
        tar_path.unlink(missing_ok=True)


def _tar_filter(info: tarfile.TarInfo):
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 1763200000  # fixed build stamp keeps archives reproducible
    return info


def extract_tree(package: Path, destination: Path) -> None:
    """Extract a ``.zaod`` archive into ``destination`` with path checks."""
    package, destination = Path(package), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="zaod-untar-", suffix=".tar", delete=False) as handle:
        tar_path = Path(handle.name)
    try:
        decompress_file(package, tar_path)
        try:
            with tarfile.open(tar_path, "r") as archive:
                members = list(_safe_members(archive, destination))
                archive.extractall(destination, members=members, filter="tar")
        except tarfile.TarError as exc:
            raise PackageError(f"{package.name} is not a valid tar archive: {exc}") from exc
    finally:
        tar_path.unlink(missing_ok=True)
    # Keep the executable bits the package shipped, but never keep group or
    # world write permission.
    for item in [destination, *destination.rglob("*")]:
        if item.is_symlink():
            continue
        mode = item.stat().st_mode
        if not (item.is_file() or item.is_dir()):
            continue
        cleaned = stat.S_IMODE(mode) & ~0o022
        if item.is_dir():
            cleaned |= 0o111
        os.chmod(item, cleaned)

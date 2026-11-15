"""Pluggable compression back-ends for `.zaod` archives.

`.zaod` v1 is a **zstd-compressed tar** (PRD section 10). Python's standard
library has no zstd support before 3.14, and the PRD forbids pip dependencies
in shipped code, so the shipped back-end shells out to the ``zstd`` CLI. The
compressor is an interface with three implementations:

``ZstdCliCompressor``
    Production. Uses ``zstd``/``unzstd`` through :mod:`subprocess`. Threads are
    pinned to 1 and the content size is recorded so that output is
    byte-reproducible for a given zstd version (see the spec's reproducibility
    section -- cross-version byte equality is *not* promised, and the release
    process pins the zstd version instead).

``TarCompressor``
    Uncompressed ``.tar``. Used by the test suite and by ``zaod pack --store``
    when debugging; it exercises the identical archive layout and safety code
    without depending on an external binary.

``PythonZstdCompressor``
    Optional. Only available when the ``compression.zstd`` module exists
    (CPython 3.14+) or a ``zstandard`` package happens to be installed. It is
    auto-detected; the shipped system image does not require it.

Missing CLI behaviour is a clear, actionable error (:class:`CompressorError`),
never a silent fallback to another format: a `.zaod` file must be zstd, and
writing an uncompressed file with a ``.zaod`` name would break interop.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from .errors import CompressorError

__all__ = [
    "ZSTD_MAGIC",
    "Compressor",
    "PythonZstdCompressor",
    "TarCompressor",
    "ZstdCliCompressor",
    "auto_compressor",
    "compressor_for_name",
    "detect_format",
    "zstd_available",
]

#: zstd frame magic number (RFC 8878 section 3.1.1).
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

#: Hard limits on decompression, so a crafted archive cannot fill the disk.
MAX_UNCOMPRESSED_BYTES = 8 * 1024**3  # 8 GiB: larger than any v1 package
MAX_COMPRESSION_RATIO = 400  # zstd -19 on text logs can reach ~100; 400 is generous


class Compressor:
    """Abstract compress/decompress back-end."""

    #: File extensions this back-end writes, most preferred first.
    extensions: tuple[str, ...] = ()

    #: Human name used in error messages and ``zaod info``.
    name = "abstract"

    def compress_bytes(self, data: bytes) -> bytes:
        raise NotImplementedError

    def decompress_bytes(self, data: bytes) -> bytes:
        raise NotImplementedError

    def compress_file(self, source: str, destination: str) -> None:
        """Compress ``source`` into ``destination`` using streaming I/O."""
        with open(source, "rb") as src, open(destination, "wb") as dst:
            self._compress_stream(src, dst)

    def decompress_file(self, source: str, destination: str) -> None:
        """Decompress ``source`` into ``destination`` using streaming I/O."""
        with open(source, "rb") as src, open(destination, "wb") as dst:
            self._decompress_stream(src, dst)

    def _compress_stream(self, src, dst) -> None:
        dst.write(self.compress_bytes(src.read()))

    def _decompress_stream(self, src, dst) -> None:
        dst.write(self.decompress_bytes(src.read()))

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"


class TarCompressor(Compressor):
    """Identity "compression": a plain tar stream.

    Deliberately *not* selected by default for `.zaod` files. It exists for
    tests and for ``--format tar`` debugging output, where the point is to
    validate archive layout and safety logic without external tools.
    """

    extensions = (".tar",)
    name = "tar (uncompressed)"

    def compress_bytes(self, data: bytes) -> bytes:
        return data

    def decompress_bytes(self, data: bytes) -> bytes:
        return data

    def _compress_stream(self, src, dst) -> None:
        shutil.copyfileobj(src, dst, 1024 * 1024)

    def _decompress_stream(self, src, dst) -> None:
        shutil.copyfileobj(src, dst, 1024 * 1024)


@dataclass
class ZstdCliCompressor(Compressor):
    """zstd via the ``zstd`` command-line tool (the shipped default)."""

    binary: str = "zstd"
    level: int = 19
    extensions = (".zaod", ".tar.zst", ".tzst")
    name = "zstd (CLI)"

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 19:
            # zstd accepts up to 22 with --ultra; the spec pins 1..19 so that
            # every build host (which may lack ultra-enabled binaries) agrees.
            raise CompressorError(f"zstd level must be between 1 and 19, got {self.level}")

    # -- availability ------------------------------------------------------

    def _require(self) -> str:
        resolved = shutil.which(self.binary)
        if resolved is None:
            raise CompressorError(
                f"the '{self.binary}' command was not found on PATH. "
                "Zaod OS ships zstd in the base system; on a development host install "
                "the 'zstd' package, or pass --format tar for an uncompressed archive."
            )
        return resolved

    @property
    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    # -- implementation ----------------------------------------------------

    def _run(self, args: list[str], *, payload: bytes | None = None) -> bytes:
        binary = self._require()
        try:
            completed = subprocess.run(
                [binary, *args],
                input=payload,
                capture_output=True,
                check=False,
                timeout=600,
            )
        except OSError as exc:
            raise CompressorError(f"failed to execute {binary}: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CompressorError(f"{binary} timed out after 600s") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            raise CompressorError(f"{binary} failed (exit {completed.returncode}): {detail}")
        return completed.stdout

    def compress_bytes(self, data: bytes) -> bytes:
        # -q: no progress meter; -c: stdout; --single-thread: reproducible
        # frame headers; --no-check: no xxhash trailer (the format carries its
        # own SHA-256 CHECKSUMS, and dropping the trailer keeps output
        # identical across zstd versions that differ in checksum defaults).
        return self._run(
            [
                f"-{self.level}",
                "-q",
                "-c",
                "--single-thread",
                "--no-check",
                "-",
            ],
            payload=data,
        )

    def decompress_bytes(self, data: bytes) -> bytes:
        return self._run(["-d", "-q", "-c", "--single-thread", "-"], payload=data)

    def _compress_stream(self, src, dst) -> None:
        binary = self._require()
        command = [
            binary,
            f"-{self.level}",
            "-q",
            "-c",
            "--single-thread",
            "--no-check",
            "-",
        ]
        self._pipe(command, src, dst)

    def _decompress_stream(self, src, dst) -> None:
        binary = self._require()
        self._pipe([binary, "-d", "-q", "-c", "--single-thread", "-"], src, dst)

    def _pipe(self, command: list[str], src, dst) -> None:
        try:
            completed = subprocess.run(
                command,
                stdin=src,
                stdout=dst,
                stderr=subprocess.PIPE,
                check=False,
                timeout=1800,
            )
        except OSError as exc:
            raise CompressorError(f"failed to execute {command[0]}: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CompressorError(f"{command[0]} timed out after 1800s") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            raise CompressorError(
                f"{command[0]} failed (exit {completed.returncode}): {detail}"
            )


class PythonZstdCompressor(Compressor):
    """zstd through a Python binding, when one is importable.

    Supports CPython 3.14+ ``compression.zstd`` and the third-party
    ``zstandard`` module. Never required.
    """

    extensions = (".zaod", ".tar.zst", ".tzst")
    name = "zstd (Python binding)"

    def __init__(self) -> None:
        self._impl = self._detect()
        if self._impl == "stdlib":
            from compression import zstd as module  # type: ignore[import-not-found]

            self._module = module
        elif self._impl == "zstandard":
            import zstandard  # type: ignore[import-not-found]

            self._module = zstandard

    @staticmethod
    def _detect() -> str:
        if sys.version_info >= (3, 14):
            try:
                import compression.zstd  # noqa: F401  # type: ignore[import-not-found]

                return "stdlib"
            except ImportError:  # pragma: no cover - 3.14+ always has it
                pass
        try:
            import zstandard  # noqa: F401  # type: ignore[import-not-found]
        except ImportError as exc:
            raise CompressorError(
                "no Python zstd binding is available (needs Python 3.14+ or the "
                "'zstandard' package); use the zstd CLI backend instead"
            ) from exc
        return "zstandard"

    @property
    def available(self) -> bool:
        return True

    def compress_bytes(self, data: bytes) -> bytes:
        if self._impl == "stdlib":
            return self._module.compress(data, level=19)
        return self._module.ZstdCompressor(level=19).compress(data)

    def decompress_bytes(self, data: bytes) -> bytes:
        if self._impl == "stdlib":
            return self._module.decompress(data)
        return self._module.ZstdDecompressor().decompress(data, max_output_size=MAX_UNCOMPRESSED_BYTES)


def zstd_available() -> bool:
    """True when the ``zstd`` CLI is usable on this host."""
    return shutil.which("zstd") is not None


def auto_compressor(level: int = 19) -> Compressor:
    """Pick the best available compressor for writing ``.zaod`` files.

    Order: zstd CLI (what the target system ships) → Python binding. Raises a
    clear :class:`CompressorError` when neither is present.
    """
    if zstd_available():
        return ZstdCliCompressor(level=level)
    try:
        return PythonZstdCompressor()
    except CompressorError as exc:
        raise CompressorError(
            "no zstd backend is available: the 'zstd' command is not on PATH and no "
            "Python zstd binding is importable. Install the 'zstd' package on this "
            "build host (Zaod OS ships it in the base system)."
        ) from exc


def compressor_for_name(name: str, level: int = 19) -> Compressor:
    """Resolve a CLI ``--format`` value to a compressor instance."""
    normalised = name.strip().lower()
    if normalised in ("zstd", "zaod", "zst"):
        return auto_compressor(level=level)
    if normalised in ("tar", "none", "plain"):
        return TarCompressor()
    raise CompressorError(
        f"unknown archive format {name!r}; supported values are 'zstd' (default) and 'tar'"
    )


def detect_format(head: bytes) -> str:
    """Classify archive bytes as ``"zstd"`` or ``"tar"``.

    Used by ``zaod info``/``verify`` so that both encodings are accepted on
    read while the writer still defaults to zstd.
    """
    if head.startswith(ZSTD_MAGIC):
        return "zstd"
    # A POSIX tar header has "ustar" at offset 257.
    if len(head) > 262 and head[257:262] == b"ustar":
        return "tar"
    if head.startswith(b"\x1f\x8b"):
        raise CompressorError(
            "this archive is gzip-compressed; .zaod v1 requires zstd "
            "(re-pack it with 'zaod pack')"
        )
    if head.startswith(b"PK\x03\x04"):
        raise CompressorError(
            "this file is a zip archive, not a .zaod package "
            "(.zaod is a zstd-compressed tar)"
        )
    raise CompressorError(
        "unrecognised archive encoding: not zstd and not a plain tar "
        "(a .zaod file must be a zstd-compressed tar)"
    )

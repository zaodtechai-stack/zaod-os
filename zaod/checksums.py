"""``CHECKSUMS`` generation and verification for `.zaod` format v1.

File format (normative, see ``docs/zaod-format-v1.md`` section 4)::

    sha256:<64 lowercase hex>  <size>  <path>
    sha256:<64 lowercase hex>  <size>  <path>

* one entry per payload file (and per auxiliary file listed in the manifest);
* UTF-8, LF line endings, no BOM;
* records sorted by ``path`` using byte-wise ascending order;
* exactly one literal space between the three fields (non-ambiguous, unlike
  ``sha256sum`` output which uses two);
* ``size`` is the decimal byte length of the file and must match the content;
* the list covers **every** file in the archive except ``MANIFEST.json``,
  ``CHECKSUMS`` and ``SIGNATURE`` themselves; entries for files that are not
  present and files that are present but not listed are both errors.

Because ``MANIFEST.json`` is not inside ``CHECKSUMS``, the signature in
``SIGNATURE`` covers ``sha256(MANIFEST.json + CHECKSUMS)`` (see
:mod:`zaod.signature`), so the two documents are bound together.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .errors import ChecksumError

__all__ = [
    "CHECKSUMS_NAME",
    "DEFAULT_CHUNK_SIZE",
    "ChecksumEntry",
    "format_checksums",
    "parse_checksums",
    "sha256_bytes",
    "sha256_file",
    "verify_entry",
]

CHECKSUMS_NAME = "CHECKSUMS"

#: 1 MiB read chunks: enough throughput, small enough memory footprint.
DEFAULT_CHUNK_SIZE = 1024 * 1024

_LINE_RE = re.compile(r"^sha256:(?P<digest>[0-9a-f]{64}) (?P<size>0|[1-9][0-9]{0,17}) (?P<path>\S.*)$")


@dataclass(frozen=True)
class ChecksumEntry:
    """One line of a CHECKSUMS file."""

    path: str
    size: int
    sha256: str

    def line(self) -> str:
        return f"sha256:{self.sha256} {self.size} {self.path}"


def sha256_bytes(data: bytes) -> str:
    """Lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> tuple[str, int]:
    """Return ``(hex_digest, size_in_bytes)`` for a file, hashing in chunks."""
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), total


def format_checksums(entries: list[ChecksumEntry] | tuple[ChecksumEntry, ...]) -> bytes:
    """Serialise entries into canonical CHECKSUMS bytes.

    Duplicate paths are a hard error: a duplicated line would let one of two
    different digests win depending on which line a verifier reads.
    """
    seen: dict[str, str] = {}
    for entry in entries:
        if entry.path in seen:
            raise ChecksumError(f"duplicate CHECKSUMS entry for {entry.path!r}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry.sha256):
            raise ChecksumError(f"invalid sha256 for {entry.path!r}")
        if entry.size < 0:
            raise ChecksumError(f"negative size for {entry.path!r}")
        seen[entry.path] = entry.sha256
    ordered = sorted(entries, key=lambda item: item.path.encode("utf-8"))
    return "".join(entry.line() + "\n" for entry in ordered).encode("utf-8")


def parse_checksums(raw: bytes | str) -> list[ChecksumEntry]:
    """Parse CHECKSUMS bytes, rejecting anything malformed.

    The parser is strict on purpose: an archive with a hand-edited, duplicate
    or unsorted CHECKSUMS file is rejected rather than silently normalised,
    because normalising would mean the signature no longer covers what was
    distributed.
    """
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ChecksumError(f"CHECKSUMS is not valid UTF-8: {exc}") from exc
    else:
        text = raw
    if text.startswith("\ufeff"):
        raise ChecksumError("CHECKSUMS must not start with a byte-order mark")
    if "\r" in text:
        raise ChecksumError("CHECKSUMS must use LF line endings, not CRLF")
    if not text.endswith("\n"):
        raise ChecksumError("CHECKSUMS must end with a newline")
    entries: list[ChecksumEntry] = []
    seen: set[str] = set()
    previous: bytes | None = None
    for number, line in enumerate(text.split("\n")[:-1], start=1):
        match = _LINE_RE.match(line)
        if match is None:
            raise ChecksumError(
                f"CHECKSUMS line {number} is malformed: expected "
                "'sha256:<hex> <size> <path>'"
            )
        path = match.group("path")
        if path in seen:
            raise ChecksumError(f"CHECKSUMS lists {path!r} more than once")
        encoded = path.encode("utf-8")
        if previous is not None and encoded < previous:
            raise ChecksumError(
                f"CHECKSUMS is not sorted by path: {path!r} appears after a greater path"
            )
        previous = encoded
        seen.add(path)
        entries.append(
            ChecksumEntry(path=path, size=int(match.group("size")), sha256=match.group("digest"))
        )
    if not entries:
        raise ChecksumError("CHECKSUMS is empty; every package must list at least one file")
    return entries


def verify_entry(entry: ChecksumEntry, actual_digest: str, actual_size: int) -> None:
    """Raise :class:`ChecksumError` unless the entry matches the actual file."""
    if entry.size != actual_size:
        raise ChecksumError(
            f"size mismatch for {entry.path}: CHECKSUMS says {entry.size} bytes, "
            f"archive has {actual_size}"
        )
    if entry.sha256 != actual_digest:
        raise ChecksumError(
            f"SHA-256 mismatch for {entry.path}: CHECKSUMS says {entry.sha256}, "
            f"computed {actual_digest}"
        )

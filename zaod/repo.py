"""Signed package index (the store repository).

An index is one JSON document, signed with the same Ed25519 key material as the
packages themselves::

    {
      "format_version": 1,
      "repo": "zaod-main",
      "generated": "2026-11-15T00:00:00Z",
      "expires": "2026-12-15T00:00:00Z",
      "packages": [ {id, version, channel, sha256, size, url, permissions, ...} ],
      "signature": {"algorithm": "ed25519", "key_id": "…", "value": "…"}
    }

The signature covers the canonical form of the document **without** the
``signature`` member, so a mirror can re-serve the file but cannot alter it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import semver
from . import signature as signature_mod
from .errors import PackageError, SignatureError

FORMAT_VERSION = 1
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CHANNELS = ("stable", "beta")


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def canonical(document: dict) -> bytes:
    """Canonical bytes of an index, excluding its signature."""
    body = {key: value for key, value in document.items() if key != "signature"}
    return (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


@dataclass
class IndexPackage:
    """One package entry in the index."""

    id: str
    version: str
    channel: str
    sha256: str
    size: int
    url: str
    permissions: list = field(default_factory=list)
    published: str | None = None
    changelog_url: str | None = None
    min_os: str = "1.0.0"

    @classmethod
    def from_dict(cls, data: dict) -> IndexPackage:
        missing = {"id", "version", "sha256", "size", "url"} - set(data)
        if missing:
            raise PackageError(f"index entry is missing {', '.join(sorted(missing))}")
        digest = str(data["sha256"]).lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise PackageError(f"index entry {data['id']} has an invalid sha256")
        try:
            semver.parse(str(data["version"]))
        except Exception as exc:
            raise PackageError(f"index entry {data['id']} has an invalid version: {exc}") from exc
        channel = str(data.get("channel", "stable"))
        if channel not in CHANNELS:
            raise PackageError(f"index entry {data['id']} has an unknown channel {channel!r}")
        return cls(
            id=str(data["id"]),
            version=str(data["version"]),
            channel=channel,
            sha256=digest,
            size=int(data["size"]),
            url=str(data["url"]),
            permissions=list(data.get("permissions", [])),
            published=data.get("published"),
            changelog_url=data.get("changelog_url"),
            min_os=str(data.get("min_os", "1.0.0")),
        )

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "version": self.version,
            "channel": self.channel,
            "sha256": self.sha256,
            "size": self.size,
            "url": self.url,
            "permissions": list(self.permissions),
            "min_os": self.min_os,
        }
        if self.published:
            data["published"] = self.published
        if self.changelog_url:
            data["changelog_url"] = self.changelog_url
        return data


def build_index(
    packages: list,
    *,
    repo: str = "zaod-main",
    ttl_days: int = 30,
    generated: datetime | None = None,
) -> dict:
    """Build an unsigned index document."""
    stamp = (generated or _now()).strftime(TIME_FORMAT)
    expires = ((generated or _now()) + timedelta(days=ttl_days)).strftime(TIME_FORMAT)
    entries = [package.to_dict() if isinstance(package, IndexPackage) else dict(package) for package in packages]
    entries.sort(key=lambda entry: (entry["id"], semver.parse(entry["version"])))
    # Fail early rather than shipping an index the client will reject.
    for entry in entries:
        IndexPackage.from_dict(entry)
    return {
        "format_version": FORMAT_VERSION,
        "repo": repo,
        "generated": stamp,
        "expires": expires,
        "packages": entries,
    }


def sign_index(document: dict, private_key: bytes, key_id: str | None = None) -> dict:
    """Return the document with a signature member attached."""
    if document.get("format_version") != FORMAT_VERSION:
        raise PackageError(f"cannot sign format {document.get('format_version')!r}")
    value = signature_mod.ed25519.sign(private_key, canonical(document))
    return {
        **document,
        "signature": {
            "algorithm": "ed25519",
            "key_id": key_id or signature_mod.key_id_for(
                signature_mod.ed25519.public_key_from_seed(private_key[:32])
            ),
            "value": value.hex(),
        },
    }


def verify_index(document: dict, trust: signature_mod.TrustStore, now: datetime | None = None) -> dict:
    """Verify an index and return it, or raise."""
    if document.get("format_version") != FORMAT_VERSION:
        raise PackageError(f"index format {document.get('format_version')!r} is not supported")
    block = document.get("signature")
    if not isinstance(block, dict) or block.get("algorithm") != "ed25519":
        raise SignatureError("index is not signed with ed25519")
    raw = block.get("value", "")
    try:
        value = bytes.fromhex(raw)
    except ValueError as exc:
        raise SignatureError(f"index signature is not hex: {exc}") from exc
    key = trust.require(str(block.get("key_id", "")))
    try:
        signature_mod.ed25519.verify(key.public_key, canonical(document), value)
    except Exception as exc:
        raise SignatureError(f"index signature does not verify: {exc}") from exc

    moment = now or _now()
    expires = _parse_time(document.get("expires"), "expires")
    if moment > expires:
        raise SignatureError(
            f"index expired on {document.get('expires')}; refresh it before installing"
        )
    generated = _parse_time(document.get("generated"), "generated")
    if generated > moment + timedelta(days=1):
        raise SignatureError(f"index is dated in the future ({document.get('generated')})")

    for entry in document.get("packages", []):
        IndexPackage.from_dict(entry)
    return document


def _parse_time(value, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise PackageError(f"index {field_name} is missing")
    try:
        return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise PackageError(f"index {field_name} is not {TIME_FORMAT}: {value!r}") from exc


def write_index(document: dict, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def read_index(path: str | Path) -> dict:
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackageError(f"no index at {source}") from exc
    except json.JSONDecodeError as exc:
        raise PackageError(f"{source} is not valid JSON: {exc}") from exc


def entries(document: dict) -> list:
    return [IndexPackage.from_dict(entry) for entry in document.get("packages", [])]


def latest(document: dict, package_id: str, channel: str = "stable") -> IndexPackage | None:
    """Newest version of a package on a channel."""
    candidates = [
        entry
        for entry in entries(document)
        if entry.id == package_id and (channel == "beta" or entry.channel == channel)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: semver.parse(entry.version) if isinstance(entry.version, str) else entry.version)


def channels_for(document: dict, package_id: str) -> list:
    return sorted({entry.channel for entry in entries(document) if entry.id == package_id})

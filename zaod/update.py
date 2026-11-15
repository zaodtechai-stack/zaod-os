"""OS update feed client.

The control center publishes OS releases; this module is the other end of that
pipe. A feed is a signed JSON document::

    {
      "format_version": 1,
      "generated": "2026-11-15T00:00:00Z",
      "expires":   "2026-12-15T00:00:00Z",
      "releases": [
        {"version": "1.1.0", "channel": "stable", "status": "published",
         "iso_url": "https://…/zaod-os-1.1.0-x86_64.iso",
         "sha256": "<64 hex>", "size": 2411724800,
         "min_supported_version": "1.0.0", "rollout_percent": 100,
         "blocker": false, "notes_url": "https://…/notes/1.1.0"}
      ],
      "signature": {"algorithm": "ed25519", "key_id": "…", "value": "…"}
    }

Design decisions that matter:

* **Rollout is per machine and stable.** A device gets the same answer every time
  it asks, because the bucket is a hash of its own id and the version, not a
  random draw.
* **A release is only offered when its channel includes this machine's channel.**
  ``beta`` machines see beta and stable; ``stable`` machines see stable and lts.
* **Downgrades are never offered.** The feed describes where the OS may go, and
  that is forward only.
* **``blocker`` wins over rollout.** A release marked as a blocker is offered to
  every machine on the channel regardless of the rollout percentage, and
  ``min_supported_version`` makes an update mandatory for anything older.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import semver
from . import signature as signature_mod
from .errors import NetworkError, PackageError, SignatureError

FORMAT_VERSION = 1
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CHANNEL_VISIBILITY = {
    "beta": ("beta", "stable", "lts"),
    "stable": ("stable", "lts"),
    "lts": ("lts",),
}


def canonical(document: dict) -> bytes:
    body = {key: value for key, value in document.items() if key != "signature"}
    return (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


@dataclass(frozen=True)
class Release:
    version: str
    channel: str
    status: str
    iso_url: str
    sha256: str
    size: int
    min_supported_version: str = "1.0.0"
    rollout_percent: int = 100
    blocker: bool = False
    notes_url: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Release:
        missing = {"version", "channel", "sha256", "iso_url"} - set(data)
        if missing:
            raise PackageError(f"release is missing {', '.join(sorted(missing))}")
        digest = str(data["sha256"]).lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise PackageError(f"release {data.get('version')} has an invalid sha256")
        channel = str(data["channel"])
        if channel not in CHANNEL_VISIBILITY:
            raise PackageError(f"release {data['version']} has an unknown channel {channel!r}")
        status = str(data.get("status", "published"))
        if status not in ("draft", "published", "paused", "archived"):
            raise PackageError(f"release {data['version']} has an unknown status {status!r}")
        if status == "published" and not str(data["iso_url"]).startswith("https://"):
            raise PackageError(f"release {data['version']} must be served over https")
        rollout = int(data.get("rollout_percent", 100))
        if not 0 <= rollout <= 100:
            raise PackageError(f"release {data['version']} has a rollout outside 0-100")
        try:
            semver.parse(str(data["version"]))
            semver.parse(str(data.get("min_supported_version", "1.0.0")))
        except Exception as exc:  # noqa: BLE001 - normalised
            raise PackageError(f"release {data['version']} has an invalid version: {exc}") from exc
        return cls(
            version=str(data["version"]),
            channel=channel,
            status=status,
            iso_url=str(data["iso_url"]),
            sha256=digest,
            size=int(data.get("size", 0)),
            min_supported_version=str(data.get("min_supported_version", "1.0.0")),
            rollout_percent=rollout,
            blocker=bool(data.get("blocker", False)),
            notes_url=data.get("notes_url"),
        )


@dataclass
class UpdatePlan:
    """What the OS should do about updates, and why."""

    current: str
    channel: str
    release: Release | None = None
    mandatory: bool = False
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.release is not None

    def summary(self) -> str:
        if not self.available:
            return f"no update ({self.reason or 'up to date'})"
        prefix = "mandatory update" if self.mandatory else "update"
        return f"{prefix} {self.current} -> {self.release.version} ({self.reason})"


def _parse_time(value, field_name: str) -> datetime:
    try:
        return datetime.strptime(str(value), TIME_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise PackageError(f"feed {field_name} is not {TIME_FORMAT}") from exc


def verify_feed(document: dict, trust: signature_mod.TrustStore, now: datetime | None = None) -> dict:
    """Verify the feed signature, its freshness, and every release in it."""
    if document.get("format_version") != FORMAT_VERSION:
        raise PackageError(f"feed format {document.get('format_version')!r} is not supported")
    block = document.get("signature")
    if not isinstance(block, dict) or block.get("algorithm") != "ed25519":
        raise SignatureError("the update feed is not signed with ed25519")
    try:
        value = bytes.fromhex(str(block.get("value", "")))
    except ValueError as exc:
        raise SignatureError(f"feed signature is not hex: {exc}") from exc
    key = trust.require(str(block.get("key_id", "")))
    try:
        signature_mod.ed25519.verify(key.public_key, canonical(document), value)
    except Exception as exc:  # noqa: BLE001 - normalised
        raise SignatureError(f"feed signature does not verify: {exc}") from exc

    moment = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    if moment > _parse_time(document.get("expires"), "expires"):
        raise SignatureError("the update feed has expired; refresh it before offering updates")
    for entry in document.get("releases", []):
        Release.from_dict(entry)
    return document


def bucket(device_id: str, version: str) -> int:
    """Deterministic 0-99 bucket for rollout decisions."""
    digest = hashlib.sha256(f"{device_id}:{version}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


def releases(document: dict, channel: str) -> list:
    visible = CHANNEL_VISIBILITY.get(channel)
    if visible is None:
        raise PackageError(f"unknown update channel {channel!r}")
    entries = [Release.from_dict(entry) for entry in document.get("releases", [])]
    entries = [entry for entry in entries if entry.channel in visible and entry.status == "published"]
    entries.sort(key=lambda entry: semver.parse(entry.version))
    return entries


def plan(
    current_version: str,
    document: dict,
    *,
    channel: str = "stable",
    device_id: str = "",
    now: datetime | None = None,
) -> UpdatePlan:
    """Decide whether this machine should update, and to what."""
    candidates = releases(document, channel)
    ahead = [entry for entry in candidates if semver.compare(entry.version, current_version) > 0]
    latest = candidates[-1] if candidates else None
    if latest is None:
        return UpdatePlan(current_version, channel, reason="the feed has no release on this channel")
    if not ahead:
        return UpdatePlan(
            current_version,
            channel,
            reason=f"{current_version} is current on {channel} (latest {latest.version})",
        )

    newest = ahead[-1]
    mandatory = newest.blocker or semver.compare(current_version, newest.min_supported_version) < 0
    if mandatory:
        return UpdatePlan(
            current_version,
            channel,
            release=newest,
            mandatory=True,
            reason="older than the minimum supported version" if not newest.blocker else "flagged as required",
        )

    position = bucket(device_id or "unassigned", newest.version)
    if position >= newest.rollout_percent:
        return UpdatePlan(
            current_version,
            channel,
            reason=f"{newest.version} is at {newest.rollout_percent}% rollout, this device is outside it for now",
        )
    return UpdatePlan(
        current_version,
        channel,
        release=newest,
        reason=f"inside the {newest.rollout_percent}% rollout",
    )


def fetch(url: str, timeout: int = 30) -> bytes:
    """Read a feed from ``file://`` or https."""
    import urllib.parse
    import urllib.request

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        request = urllib.request.Request(url, headers={"User-Agent": "zaod-update/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked
                return response.read()
        except Exception as exc:  # noqa: BLE001 - normalised
            raise NetworkError(f"cannot fetch {url}: {exc}") from exc
    path = Path(urllib.request.url2pathname(parsed.path)) if parsed.scheme == "file" else Path(url)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise NetworkError(f"cannot read {path}: {exc}") from exc


def load(path_or_url: str, trust: signature_mod.TrustStore, now: datetime | None = None) -> dict:
    payload = fetch(path_or_url)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"the update feed is not JSON: {exc}") from exc
    return verify_feed(document, trust, now=now)


def verify_image(path: str | Path, release: Release) -> Path:
    """Check a downloaded ISO against the feed before the installer sees it."""
    image = Path(path)
    try:
        payload = image.read_bytes()
    except OSError as exc:
        raise PackageError(f"cannot read {image}: {exc}") from exc
    digest = hashlib.sha256(payload).hexdigest()
    if digest != release.sha256:
        raise PackageError(
            f"{image} failed its SHA-256 check: expected {release.sha256}, got {digest}"
        )
    if release.size and len(payload) != release.size:
        raise PackageError(f"{image} is {len(payload)} bytes, the feed promised {release.size}")
    return image

#!/usr/bin/env python3
"""zaod-update - receive signed updates without touching a person's data.

A Zaod system must be able to move forward without being reinstalled. Nothing in
this file goes near a home directory: it only ever writes the update state file and
the journal the signed bundle already keeps, so projects, accounts, wallpapers and
installed apps stay exactly where they are.

The channel is one small JSON document, so publishing an update is a release asset
and a version bump, not a new ISO:

```json
{
  "format": 1,
  "version": "0.4.3",
  "published": "2026-11-20T10:00:00Z",
  "summary": "Studio saves faster; store cards answer first click",
  "bundle": {"url": "https://host/zaod-0.4.3.zaodbundle", "sha256": "…", "size": 1234}
}
```

The bundle itself is verified and applied by ``zaodlib``, which repacks the current
version into a journal before every package and restores it if anything fails, so a
half-applied update is impossible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

FORMAT = 1
CHANNEL_CONFIG = Path(os.environ.get("ZAOD_UPDATE_CONFIG", "/etc/zaod/update-channel.json"))
STATE_PATH = Path(os.environ.get("ZAOD_UPDATE_STATE", "/var/lib/zaod/update-state.json"))
TIMEOUT = 60


class UpdateError(RuntimeError):
    """Something the person can act on: bad channel, bad checksum, nothing to do."""


@dataclass
class Release:
    version: str
    summary: str
    published: str
    url: str
    sha256: str
    size: int


def channel_url(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if os.environ.get("ZAOD_UPDATE_CHANNEL"):
        return os.environ["ZAOD_UPDATE_CHANNEL"]
    if CHANNEL_CONFIG.is_file():
        try:
            data = json.loads(CHANNEL_CONFIG.read_text())
        except ValueError as exc:
            raise UpdateError("the update channel file is not valid JSON") from exc
        url = data.get("url")
        if not url:
            raise UpdateError("the update channel file has no url")
        return str(url)
    raise UpdateError("no update channel is configured on this system")


def installed_version(state: Path | None = None) -> str:
    path = state or STATE_PATH
    if path.is_file():
        try:
            return str(json.loads(path.read_text()).get("version") or "")
        except ValueError:
            return ""
    return ""


def parse_channel(document: dict) -> Release:
    if int(document.get("format", 0)) != FORMAT:
        raise UpdateError("this channel uses a newer format than this system understands")
    version = str(document.get("version") or "").strip()
    bundle = document.get("bundle") or {}
    url = str(bundle.get("url") or "")
    digest = str(bundle.get("sha256") or "").lower()
    if not version:
        raise UpdateError("the channel does not name a version")
    if not url:
        raise UpdateError("the channel does not point at a bundle")
    if len(digest) != 64:
        raise UpdateError("the channel does not carry a sha256 for the bundle")
    return Release(
        version=version,
        summary=str(document.get("summary") or document.get("notes") or "").strip(),
        published=str(document.get("published") or ""),
        url=url,
        sha256=digest,
        size=int(bundle.get("size") or 0),
    )


def fetch(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:  # the channel URL comes from the system's own configuration
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(f"cannot reach {url}: {exc}") from exc


def check(version_installed: str, channel: str | None = None) -> tuple[Release, bool]:
    """Read the channel; the flag says whether it is worth downloading."""
    release = parse_channel(json.loads(fetch(channel_url(channel))))
    newer = release.version != version_installed
    return release, newer


def download(release: Release, into: Path, channel: str | None = None) -> Path:
    """Fetch the bundle and refuse it unless it is exactly the published file."""
    into.mkdir(parents=True, exist_ok=True)
    target = into / f"zaod-{release.version}.zaodbundle"
    digest = hashlib.sha256()
    written = 0
    with tempfile.NamedTemporaryFile(delete=False, dir=str(into)) as temp:
        try:
            with urllib.request.urlopen(release.url, timeout=TIMEOUT) as response:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    digest.update(chunk)
                    written += len(chunk)
                    temp.write(chunk)
        except (urllib.error.URLError, OSError) as exc:
            temp.close()
            Path(temp.name).unlink(missing_ok=True)
            raise UpdateError(f"the download stopped: {exc}") from exc
        temp.flush()
        os.fsync(temp.fileno())
    if digest.hexdigest() != release.sha256:
        Path(temp.name).unlink(missing_ok=True)
        raise UpdateError("the bundle does not match the checksum the channel published")
    if release.size and written != release.size:
        Path(temp.name).unlink(missing_ok=True)
        raise UpdateError("the bundle is not the size the channel published")
    shutil.move(temp.name, target)
    target.chmod(0o644)
    return target


def record(version: str, release: Release, state: Path | None = None) -> Path:
    path = state or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": version,
                "applied_at": release.published or "",
                "summary": release.summary,
                "bundle_sha256": release.sha256,
            },
            indent=2,
        )
        + "\n"
    )
    return path


def apply(release: Release, bundle: Path, applier) -> str:
    """Hand the verified bundle to libzaod, which journals and rolls back.

    ``applier`` is injected so the logic above can be tested without a system to
    upgrade; in the real command it is ``zaod bg-apply`` (zaodlib's own rollback
    path). The state file is written only after the applier returns.
    """
    try:
        applier(bundle)
    except Exception as exc:  # the applier's own error type is not ours to know
        raise UpdateError(f"the update could not be applied: {exc}") from exc
    record(release.version, release)
    return release.version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Receive signed Zaod updates")
    parser.add_argument("--channel", help="channel.json to read instead of the configured one")
    parser.add_argument("--check", action="store_true", help="only look, do not download")
    parser.add_argument("--bundle", help="apply this bundle instead of downloading")
    parser.add_argument("--version", default=installed_version(), help="the version installed now")
    parser.add_argument("--force", action="store_true", help="apply even when the version matches")
    args = parser.parse_args(argv)

    try:
        release, newer = check(args.version, args.channel)
        print(f"channel offers {release.version}" + ("" if newer else " (already installed)"))
        if release.summary:
            print(f"  {release.summary}")
        if args.check:
            return 0
        if not newer and not args.force and not args.bundle:
            print("nothing to do")
            return 0

        def applier(bundle: Path) -> None:
            import subprocess

            subprocess.run(["/usr/bin/zaod", "bg-apply", str(bundle)], check=True)

        bundle = Path(args.bundle) if args.bundle else download(release, Path(tempfile.mkdtemp()))
        version = apply(release, bundle, applier)
        print(f"updated to {version}")
        return 0
    except UpdateError as error:
        print(f"zaod-update: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

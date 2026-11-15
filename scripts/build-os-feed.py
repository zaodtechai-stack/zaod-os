#!/usr/bin/env python3
"""Build and sign the OS update feed.

The control center publishes releases; this turns the releases you exported from
it (or a hand-written list) into a signed ``os-release-feed.json`` that every
Zaod machine reads.

    scripts/build-os-feed.py --releases releases.json \
        --key build/keys/main.seed --out build/repo/os-release-feed.json

``releases.json`` is either ``{"releases": [...]}`` or a bare list, with the
fields the control center's OsRelease entity uses: ``version``, ``channel``,
``status``, ``iso_url``, ``sha256``, ``size``, ``min_supported_version``,
``rollout_percent``, ``blocker``, ``notes_url``. Draft releases are kept in the
document (so the feed can be regenerated as they are published) but the client
never offers them.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zaod import signature, update  # noqa: E402
from zaod.errors import ZaodError  # noqa: E402


def load_releases(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"no releases file at {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from None
    entries = data.get("releases", []) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise SystemExit("releases must be a list")
    return entries


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--releases", default="build/os-releases.json")
    parser.add_argument("--key", default="build/keys/main.seed")
    parser.add_argument("--out", default="build/repo/os-release-feed.json")
    parser.add_argument("--ttl-days", type=int, default=30)
    args = parser.parse_args(argv)

    entries = load_releases(Path(args.releases))
    if not entries:
        raise SystemExit(f"{args.releases} contains no releases")

    # Normalising every entry now means a bad release fails the build, not the
    # machine that later tries to update.
    normalised = []
    for entry in entries:
        try:
            release = update.Release.from_dict(entry)
        except ZaodError as exc:
            raise SystemExit(f"invalid release {entry.get('version', '?')}: {exc}") from exc
        record = {
            "version": release.version,
            "channel": release.channel,
            "status": release.status,
            "iso_url": release.iso_url,
            "sha256": release.sha256,
            "size": release.size,
            "min_supported_version": release.min_supported_version,
            "rollout_percent": release.rollout_percent,
            "blocker": release.blocker,
        }
        if release.notes_url:
            record["notes_url"] = release.notes_url
        normalised.append(record)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    document = {
        "format_version": update.FORMAT_VERSION,
        "generated": now.strftime(update.TIME_FORMAT),
        "expires": (now + timedelta(days=args.ttl_days)).strftime(update.TIME_FORMAT),
        "releases": sorted(normalised, key=lambda item: (item["channel"], item["version"])),
    }

    seed_bytes = bytes.fromhex(Path(args.key).read_text(encoding="ascii").strip())
    value = signature.ed25519.sign(seed_bytes, update.canonical(document))
    key_id = signature.key_id_for(signature.ed25519.public_key_from_seed(seed_bytes[:32]))
    document["signature"] = {
        "algorithm": "ed25519",
        "key_id": key_id,
        "value": value.hex(),
    }

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    published = [item for item in normalised if item["status"] == "published"]
    print(f"[feed] wrote {target} with {len(normalised)} release(s), {len(published)} published")
    print(f"[feed] signing key id {key_id}, expires {document['expires']}")
    for item in sorted(published, key=lambda entry: entry["version"]):
        print(f"  {item['channel']:<7} {item['version']:<10} rollout {item['rollout_percent']:>3}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())

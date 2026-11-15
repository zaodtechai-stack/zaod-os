#!/usr/bin/env python3
"""Repackage Firefox ESR as a signed .zaod package.

The tarball is downloaded from Mozilla, verified against the pinned SHA-256 in
``apps/firefox/pin.json``, and unpacked unchanged. The only addition is
``distribution/policies.json``, which makes Google the default search engine.

Usage:
    python3 apps/firefox/build.py [--key signing.key] [--level 12] [--offline]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "zaod"))

from zaodlib import pack

POLICIES = {
    "policies": {
        "SearchEngines": {
            "Default": "Google",
            "Remove": ["Bing", "DuckDuckGo", "Wikipedia (en)"],
        },
        "OverrideFirstRunPage": "",
        "OverridePostUpdatePage": "",
        "DisableProfileImport": True,
    }
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size > 0:
        print(f"cached  {target.name}")
        return
    print(f"fetch   {url}")
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=180) as response, partial.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    partial.replace(target)


def verify_pinned_checksum(tarball: Path, expected: str) -> None:
    actual = sha256_of(tarball)
    if actual != expected:
        raise SystemExit(f"checksum mismatch: expected {expected}, got {actual}")


def verify_mozilla_manifest(sha256sums: Path, relative_path: str, expected: str) -> None:
    """Confirm our pin matches the exact platform path in Mozilla's SHA256SUMS."""
    for line in sha256sums.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if name.strip() == relative_path:
            if digest.strip() != expected:
                raise SystemExit(f"{relative_path} is not the release Mozilla published ({digest.strip()})")
            return
    raise SystemExit(f"{relative_path} is missing from Mozilla's SHA256SUMS")


def unpack(tarball: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with tarfile.open(tarball, "r:xz") as archive:
        for member in archive.getmembers():
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise SystemExit(f"refusing unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                link = Path(member.linkname)
                if link.is_absolute():
                    raise SystemExit(f"refusing absolute link: {member.name} -> {member.linkname}")
        archive.extractall(destination, filter="data")


def original_members(tarball: Path) -> set[str]:
    """Relative paths shipped by Mozilla, so the repackage can prove itself clean."""
    members = set()
    with tarfile.open(tarball, "r:xz") as archive:
        for member in archive.getmembers():
            if member.isfile() or member.issym() or member.islnk():
                members.add(member.name.rstrip("/"))
    return members


def verify_unchanged(payload: Path, original: set[str], added: Path) -> None:
    shipped = {
        str(path.relative_to(payload))
        for path in payload.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    extra = shipped - original - {str(added.relative_to(payload))}
    missing = {name for name in original if name not in shipped}
    if extra:
        raise SystemExit(f"unexpected files added by the repackage: {sorted(extra)[:5]}")
    if missing:
        raise SystemExit(f"files missing from the repackage: {sorted(missing)[:5]}")
    print(f"unchanged {len(original)} upstream files, one policy file added")


def write_policies(payload: Path) -> Path:
    distribution = payload / "distribution"
    distribution.mkdir(parents=True, exist_ok=True)
    target = distribution / "policies.json"
    target.write_text(json.dumps(POLICIES, indent=2) + "\n", encoding="utf-8")
    return target


def build(key: Path | None, level: int, offline: bool, output: Path) -> Path:
    pin = json.loads((APP_DIR / "pin.json").read_text(encoding="utf-8"))
    cache = REPO_ROOT / "build" / "cache" / "firefox"
    tarball = cache / pin["tarball"]
    sha256sums = cache / "SHA256SUMS"
    if not offline:
        download(f"{pin['base_url']}/SHA256SUMS", sha256sums)
    if not tarball.is_file():
        if offline:
            raise SystemExit(f"{tarball} is not cached; run without --offline first")
        download(f"{pin['base_url']}/{pin['platform']}/{pin['locale']}/{pin['tarball']}", tarball)
    relative_path = f"{pin['platform']}/{pin['locale']}/{pin['tarball']}"
    if sha256sums.is_file():
        verify_mozilla_manifest(sha256sums, relative_path, pin["sha256"])
    verify_pinned_checksum(tarball, pin["sha256"])

    staging = REPO_ROOT / "build" / "staging" / "firefox"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copy2(APP_DIR / "MANIFEST.json", staging / "MANIFEST.json")
    shutil.copy2(APP_DIR / "icon.svg", staging / "icon.svg")
    payload = staging / "payload"
    original = original_members(tarball)
    unpack(tarball, payload)
    policies = write_policies(payload / "firefox")
    print(f"policy  {policies.relative_to(staging)}")
    verify_unchanged(payload, original, policies)

    output.parent.mkdir(parents=True, exist_ok=True)
    pack.build_package(staging, output, private_key=key, level=level)
    print(f"built   {output} ({output.stat().st_size / (1024 ** 2):.1f} MiB)")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, help="Ed25519 private key used to sign the package")
    parser.add_argument("--level", type=int, default=12, help="zstd compression level (default 12)")
    parser.add_argument("--offline", action="store_true", help="use the cached tarball only")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "build" / "out" / "apps" / "firefox-153.7.0.zaod")
    args = parser.parse_args()
    build(args.key, args.level, args.offline, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

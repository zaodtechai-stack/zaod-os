#!/usr/bin/env python3
"""Static checks for the Phase 8 deliverables.

Covers the Firefox repackaging inputs, the store index builder and the pieces of
the store client that must not regress: signature verification, expiry, digest
checking and offline fallback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIREFOX = REPO_ROOT / "apps/firefox"
REPO_SCRIPT = REPO_ROOT / "scripts/build-repo.sh"

sys.path.insert(0, str(REPO_ROOT))


class Report:
    def __init__(self, verbose: bool = False) -> None:
        self.run = 0
        self.failures = []
        self.verbose = verbose

    def check(self, condition: bool, description: str, detail: str = "") -> bool:
        self.run += 1
        if not condition:
            self.failures.append(f"{description}{f' ({detail})' if detail else ''}")
        elif self.verbose:
            print(f"  ok   {description}")
        return bool(condition)

    def contains(self, text: str, needle: str, description: str) -> bool:
        return self.check(needle in text, description, f"missing {needle!r}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def check_firefox(report: Report) -> None:
    script = FIREFOX / "build-firefox-zaod.sh"
    text = read(script)
    if not report.check(bool(text), "apps/firefox/build-firefox-zaod.sh exists"):
        return
    report.check(script.stat().st_mode & 0o111 != 0, "the Firefox build script is executable")
    report.contains(text, "set -euo pipefail", "the Firefox build script is strict")
    report.contains(text, "--check", "the Firefox build script supports a dry run")
    report.contains(text, "SHA512SUMS", "the upstream checksum list is consulted")
    report.contains(text, "sha512sum", "the tarball digest is verified")
    report.contains(text, "SHA-512 mismatch", "the build stops on a digest mismatch")
    report.contains(text, "153.7.0esr", "the pinned ESR version is recorded")
    report.contains(text, "distribution/policies.json", "enterprise policies are installed")
    report.contains(text, "ZAOD-PROVENANCE.txt", "provenance is recorded inside the payload")
    report.contains(text, "python3 -m zaod.cli", "packaging goes through the zaod CLI")
    report.contains(text, "--sign-with", "the package can be signed")
    report.check(
        "curl -f" in text,
        "downloads fail on HTTP errors",
    )
    report.check(
        "SIGNING_KEY" in text and "unsigned package" in text,
        "an unsigned build is reported as a warning, not hidden",
    )

    policies_text = read(FIREFOX / "policies.json")
    report.check(bool(policies_text), "policies.json is shipped")
    try:
        policies = json.loads(policies_text).get("policies", {})
    except json.JSONDecodeError:
        report.check(False, "policies.json is valid JSON")
        return
    report.check(bool(policies), "policies.json has a policies object")
    for key in (
        "DisableTelemetry",
        "DisableFirefoxStudies",
        "DisablePocket",
        "DisableAppUpdate",
        "PasswordManagerEnabled",
        "DontCheckDefaultBrowser",
    ):
        report.check(policies.get(key) in (True, False), f"policy {key} is set")
    preferences = policies.get("Preferences", {})
    report.check(
        preferences.get("toolkit.telemetry.enabled") is False,
        "telemetry is off in preferences",
    )
    report.check(
        preferences.get("datareporting.healthreport.uploadEnabled") is False,
        "health reports are off",
    )
    report.check(
        preferences.get("widget.use-xdg-desktop-portal.file-picker") == 1,
        "the portal file picker is used so the sandbox can show dialogs",
    )

    desktop = read(FIREFOX / "os.zaod.firefox.desktop")
    report.check(bool(desktop), "the Firefox desktop entry is shipped")
    report.contains(desktop, "[Desktop Entry]", "the desktop entry has its group header")
    report.contains(desktop, "Type=Application", "the desktop entry is an application")
    report.contains(desktop, "Exec=payload/firefox/firefox", "the entry runs the payload")
    report.contains(desktop, "X-Zaod-Package=os.zaod.firefox", "the entry names its package")
    report.check(
        "%" in desktop and "%u" in desktop,
        "the entry passes a URL argument",
    )


def check_repo_script(report: Report, tmp_path: Path) -> None:
    text = read(REPO_SCRIPT)
    if not report.check(bool(text), "scripts/build-repo.sh exists"):
        return
    report.check(REPO_SCRIPT.stat().st_mode & 0o111 != 0, "build-repo.sh is executable")
    report.contains(text, "set -euo pipefail", "build-repo.sh is strict")
    report.contains(text, "--check", "build-repo.sh supports a dry run")
    report.contains(text, "SIGNING_KEY is required", "an unsigned index is refused")
    report.contains(text, "repo.sign_index", "the index is signed")
    report.contains(text, "sha256sum", "the index digest is published")
    report.contains(text, "archive.inspect", "each package manifest is read before indexing")
    report.contains(text, "is unsigned", "an unsigned package is reported")
    report.contains(text, "IndexPackage", "entries are validated through the index model")


def check_store_behaviour(report: Report, tmp_path: Path) -> None:
    from zaod import repo, signature, store
    from zaod.errors import ZaodError

    seed, public = signature.generate_keypair(seed=bytes(range(32)))
    trust = signature.TrustStore(tmp_path)
    trust.add(public)

    entry = {
        "id": "os.zaod.notes",
        "version": "1.0.0",
        "channel": "stable",
        "sha256": "a" * 64,
        "size": 10,
        "url": "file:///tmp/notes.zaod",
    }
    document = repo.build_index([entry])
    signed = repo.sign_index(document, seed)

    report.check(bool(signed.get("signature")), "a built index can be signed")
    verified = repo.verify_index(signed, trust)
    report.check(verified["repo"] == "zaod-main", "a signed index verifies")

    broken = json.loads(json.dumps(signed))
    broken["packages"][0]["size"] = 999
    try:
        repo.verify_index(broken, trust)
        report.check(False, "a tampered index is rejected")
    except ZaodError:
        report.check(True, "a tampered index is rejected")

    from datetime import UTC, datetime, timedelta

    stale = repo.sign_index(
        repo.build_index([entry], generated=datetime.now(UTC) - timedelta(days=90), ttl_days=1),
        seed,
    )
    try:
        repo.verify_index(stale, trust)
        report.check(False, "an expired index is rejected")
    except ZaodError:
        report.check(True, "an expired index is rejected")

    empty = signature.TrustStore(tmp_path / "empty")
    try:
        repo.verify_index(signed, empty)
        report.check(False, "an untrusted signing key is rejected")
    except ZaodError:
        report.check(True, "an untrusted signing key is rejected")

    index_path = repo.write_index(signed, tmp_path / "index.json")
    client = store.Store(trust=trust, root=tmp_path / "root", url=f"file://{index_path}")
    report.check(len(client.updates()) == 1, "the client plans an install for an absent package")
    client.refresh()
    client.document = None
    client.url = f"file://{tmp_path / 'gone.json'}"
    report.check(client.load() is not None and client.offline, "the client falls back to its cache")

    report.check(
        hasattr(store.Update, "summary"),
        "update objects explain themselves to the user",
    )


def main(argv=None) -> int:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    report = Report(verbose=args.verbose)
    with tempfile.TemporaryDirectory() as scratch:
        tmp_path = Path(scratch)
        check_firefox(report)
        check_repo_script(report, tmp_path)
        check_store_behaviour(report, tmp_path)

    for failure in report.failures:
        print(f"  FAIL {failure}")
    print(f"apps config checks: {report.run} run, {len(report.failures)} failed")
    if report.failures:
        print("apps config checks: FAIL")
        return 1
    print("apps config checks: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

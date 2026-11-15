#!/usr/bin/env python3
"""Scan the repository for vendor assets, trademarks and unlicensed artwork.

Phase 6 acceptance requires a Microsoft asset scan. The rule is absolute: no
Microsoft or Windows artwork, font, sound, icon, logo or trademark may enter
the tree, and every binary asset must sit under a directory that documents its
licence.

Usage:
    python3 desktop/design/tools/scan_assets.py            # scan, report, exit 1 on findings
    python3 desktop/design/tools/scan_assets.py --json     # machine readable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# The scan covers the surfaces this project draws: the shell, applications, the
# package repo and the rootfs overlay. The Linux kernel tree, the PRD and the
# devcontainer are excluded because they legitimately name vendors the OS must
# interoperate with (Hyper-V drivers, for example).
SCAN_ROOTS = ("desktop", "apps", "repo", "rootfs")
ASSET_ROOTS = ("desktop", "apps")

SCAN_SUFFIXES = {
    "",
    ".md",
    ".qml",
    ".css",
    ".json",
    ".svg",
    ".py",
    ".sh",
    ".txt",
    ".desktop",
    ".conf",
    ".service",
    ".list",
    ".js",
    ".toml",
    ".ini",
}

SKIP_DIRS = {".git", "__pycache__", "build", ".ruff_cache", ".pytest_cache", ".venv", "node_modules"}

# Files that state or enforce the exclusion rule necessarily name the excluded
# vendors. This is the complete exemption list; anything else is a finding.
PROVENANCE_ALLOWLIST = {
    "desktop/design/LICENSE.md",
    "desktop/design/tools/scan_assets.py",
    "tests/check_design_tokens.py",
    "tests/check_desktop_config.py",
    "tests/test_design_tools.py",
    "docs/design-system.md",
    "docs/reports/phase-6.md",
}

VENDOR_TERMS = (
    "microsoft",
    "windows 10",
    "windows 11",
    "windows-11",
    "windows logo",
    "segoe",
    "calibri",
    "tahoma",
    "cortana",
    "ms-settings:",
    "acrylic material",
)

ASSET_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".ico", ".ttf", ".otf", ".wav", ".ogg"}
LICENCE_MARKERS = ("license", "licence", "copyright")


def _walk(roots) -> list:
    files = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
                continue
            files.append(path)
    return files


def iter_files() -> list:
    """Every scannable file below the project's own asset-bearing directories."""
    return _walk(SCAN_ROOTS)


def iter_asset_files() -> list:
    """Files whose binary assets must have a documented licence."""
    return _walk(ASSET_ROOTS)


def scan_text(files: list) -> list:
    findings = []
    for path in files:
        relative = path.relative_to(REPO_ROOT)
        if str(relative) in PROVENANCE_ALLOWLIST:
            continue
        if path.suffix not in SCAN_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lowered = text.lower()
        for term in VENDOR_TERMS:
            for match in re.finditer(re.escape(term), lowered):
                line = lowered.count("\n", 0, match.start()) + 1
                findings.append({"file": str(relative), "line": line, "term": term})
    return findings


def licence_declared_for(path: Path) -> bool:
    """True when an ancestor directory holds a licence/copyright document."""
    directory = path.parent
    while True:
        for candidate in directory.glob("*"):
            if (
                candidate.is_file()
                and candidate.suffix in {".md", ".txt"}
                and any(marker in candidate.name.lower() for marker in LICENCE_MARKERS)
            ):
                return True
        if directory == REPO_ROOT or directory.parent == directory:
            return False
        directory = directory.parent


def scan_assets(files: list) -> list:
    undocumented = []
    for path in files:
        if path.suffix not in ASSET_SUFFIXES:
            continue
        if not licence_declared_for(path):
            undocumented.append(str(path.relative_to(REPO_ROOT)))
    return undocumented


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine readable output")
    args = parser.parse_args(argv)

    files = iter_files()
    findings = scan_text(files)
    undocumented = scan_assets(iter_asset_files())
    clean = not findings and not undocumented

    if args.json:
        print(
            json.dumps(
                {
                    "files_scanned": len(files),
                    "vendor_findings": findings,
                    "undocumented_assets": undocumented,
                    "status": "pass" if clean else "fail",
                },
                indent=2,
            )
        )
    else:
        print(f"asset scan: {len(files)} files scanned")
        for finding in findings:
            print(f"  VENDOR {finding['file']}:{finding['line']} -> {finding['term']}")
        for path in undocumented:
            print(f"  UNDOCUMENTED ASSET {path}")
        if clean:
            print("asset scan: PASS (no vendor assets, every asset directory declares a licence)")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Package Zaod Studio: the window plus the zaodstudio library it runs on.

Studio is optional: it is written to build/out/optional so the default store index
(repo/build-store.sh, which globs build/out/apps) never ships it.

Usage: python3 apps/studio/build.py [--key signing.key] [--level 10] [--out path]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "zaod"))

from zaodlib import pack

VENDORED = ("zaodstudio",)


def build(key: Path | None, level: int, output: Path) -> Path:
    staging = REPO_ROOT / "build" / "staging" / "studio"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "payload").mkdir(parents=True)
    shutil.copy2(APP_DIR / "MANIFEST.json", staging / "MANIFEST.json")
    shutil.copy2(APP_DIR / "icon.svg", staging / "icon.svg")
    shutil.copy2(APP_DIR / "payload" / "main.py", staging / "payload" / "main.py")
    (staging / "payload" / "main.py").chmod(0o755)
    for name in VENDORED:
        shutil.copytree(
            REPO_ROOT / "studio" / name,
            staging / "payload" / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    manifest = json.loads((APP_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    pack.build_package(staging, output, private_key=key, level=level)
    print(f"built {output.name} ({output.stat().st_size / 1024:.1f} KiB, {manifest['id']} {manifest['version']})")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, help="Ed25519 private key used to sign the package")
    parser.add_argument("--level", type=int, default=10)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "build" / "out" / "optional" / "studio-0.9.0.zaod")
    args = parser.parse_args()
    build(args.key, args.level, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

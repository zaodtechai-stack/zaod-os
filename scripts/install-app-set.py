#!/usr/bin/env python3
"""Install the first-party app set into a root filesystem.

An image that boots to a desktop with no applications is not a desktop: the app
grid reads /usr/share/applications, so every app the system ships has to have an
entry there before the image is squashed. The store installs *third-party*
packages through the zaod helper; this script installs the apps that are part of
the OS itself, straight from apps/, so the first boot already has them.

Usage: install-app-set.py --root DIR [--apps DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP = {"studio"}  # built by 'make studio', deliberately not part of the image


def categories(manifest: dict) -> str:
    cats = manifest.get("categories") or ["Utility"]
    return ";".join(cats) + ";"


def install(root: Path, apps_dir: Path, dry_run: bool) -> list[str]:
    installed: list[str] = []
    shared_lib = apps_dir / "lib" / "zaodapp.py"
    for app in sorted(apps_dir.iterdir()):
        if not app.is_dir() or app.name in SKIP:
            continue
        manifest_path = app / "MANIFEST.json"
        payload = app / "payload"
        if not manifest_path.is_file() or not payload.is_dir():
            continue
        manifest = json.loads(manifest_path.read_text())
        app_id = manifest["id"]
        slug = app.name
        target = root / "opt/zaod/apps" / slug
        entry = manifest.get("entry") or {}
        exe = entry.get("exec") or "payload/main.py"
        if dry_run:
            print(f"  {app_id} -> {target}")
            installed.append(app_id)
            continue
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(payload, target / "payload")
        (target / "payload/lib").mkdir(parents=True, exist_ok=True)
        if shared_lib.is_file():
            shutil.copy2(shared_lib, target / "payload/lib/zaodapp.py")
        shutil.copy2(manifest_path, target / "MANIFEST.json")
        icon = app / "icon.svg"
        icon_target = root / "usr/share/icons/hicolor/scalable/apps" / f"{app_id}.svg"
        icon_target.parent.mkdir(parents=True, exist_ok=True)
        if icon.is_file():
            shutil.copy2(icon, icon_target)
            shutil.copy2(icon, target / "icon.svg")
        desktop = root / "usr/share/applications" / f"{app_id}.desktop"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={manifest.get('name', slug)}\n"
            f"Comment={manifest.get('summary', '')}\n"
            f"Exec=/usr/bin/python3 {target}/payload/{Path(exe).name}\n"
            f"Icon={app_id}\n"
            "Terminal=false\n"
            f"Categories={categories(manifest)}\n"
            "StartupNotify=true\n"
            f"X-Zaod-AppId={app_id}\n"
        )
        installed.append(app_id)
    return installed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/", help="target root filesystem")
    parser.add_argument("--apps", default=str(REPO / "apps"), help="apps directory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "etc").is_dir():
        print(f"install-app-set: {root} is not a root filesystem", file=sys.stderr)
        return 1
    installed = install(root, Path(args.apps), args.dry_run)
    if not installed:
        print("install-app-set: no apps with a payload found", file=sys.stderr)
        return 1
    print(f"install-app-set: {'would install' if args.dry_run else 'installed'} {len(installed)} apps: {', '.join(installed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

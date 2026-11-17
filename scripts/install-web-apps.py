#!/usr/bin/env python3
"""Install the built-in web apps (YouTube, WhatsApp, Instagram, …).

Each one becomes a normal launcher entry that opens in its own Chromium window,
so the app grid, the panel and the store all see it without knowing what a
browser is.

Usage: install-web-apps.py --root DIR [--manifest PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def install(root: Path, manifest_path: Path, dry_run: bool) -> list[str]:
    apps = json.loads(manifest_path.read_text())["apps"]
    installed: list[str] = []
    for app in apps:
        app_id = app["id"]
        if dry_run:
            installed.append(app_id)
            continue
        desktop = root / "usr/share/applications" / f"{app_id}.desktop"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={app['name']}\n"
            f"Comment={app.get('summary', '')}\n"
            f"Exec=/usr/local/bin/zaod-webapp {app['url']}\n"
            f"Icon={app['icon']}\n"
            "Terminal=false\n"
            f"Categories=Network;{app.get('category', 'Utility')};\n"
            "StartupNotify=true\n"
            f"X-Zaod-AppId={app_id}\n"
            f"X-Zaod-WebApp={app['url']}\n"
        )
        icon_src = manifest_path.parent / "icons" / f"{app_id}.svg"
        if not icon_src.is_file():
            print(f"install-web-apps: missing icon {icon_src}", file=sys.stderr)
            return []
        target = root / "usr/share/icons/hicolor/scalable/apps" / f"{app_id}.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon_src, target)
        installed.append(app_id)
    return installed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/")
    parser.add_argument("--manifest", default=str(REPO / "desktop/webapps/webapps.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "etc").is_dir():
        print(f"install-web-apps: {root} is not a root filesystem", file=sys.stderr)
        return 1
    installed = install(root, Path(args.manifest), args.dry_run)
    if not installed:
        print("install-web-apps: nothing installed", file=sys.stderr)
        return 1
    print(f"install-web-apps: installed {len(installed)} web apps: {', '.join(installed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Capture every Zaod surface at 1366x768 in both themes.

The visual audit needs real renders, not descriptions. This tool produces them
from the actual sources: Qt Quick surfaces are loaded with the real engine, and
each first-party app is launched in its own subprocess (so the per-package
`main`/`backend` module names cannot collide) and grabbed at the hardware floor.

Output: docs/reports/phase-6-screenshots/<surface>-<theme>.png

Usage:
  python3 desktop/design/tools/capture_surfaces.py            # every surface
  python3 desktop/design/tools/capture_surfaces.py --only kit # one surface
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DESIGN_ROOT = REPO_ROOT / "desktop" / "design"
SURFACE_DIR = DESIGN_ROOT / "tools" / "surfaces"
OUTPUT_ROOT = REPO_ROOT / "docs" / "reports" / "phase-6-screenshots"
RENDER_APP = DESIGN_ROOT / "tools" / "_render_app.py"

WIDTH, HEIGHT = 1366, 768
THEMES = ("light", "dark")

# Qt Quick surfaces, in the order the brief lists them.
QML_SURFACES = ("desktop", "startmenu", "quicksettings", "notifications", "kit")


def app_ids() -> list[str]:
    apps = []
    for manifest in sorted((REPO_ROOT / "apps").glob("*/payload/main.py")):
        apps.append(manifest.parent.parent.name)
    return apps


def capture_qml(name: str, theme: str, out_path: Path, lite: bool = False, scale: float = 1.0) -> str:
    """Render a Qt Quick surface with the real engine and grab the window."""
    env = dict(os.environ)
    env.update(
        QT_QPA_PLATFORM="offscreen",
        QT_QUICK_BACKEND="software",
        QT_ENABLE_HIGHDPI_SCALING="0",
    )
    script = f"""
import os, sys
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # registers QQuickWindow so the grab works

app = QGuiApplication([])
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("zaodMode", {theme!r})
engine.rootContext().setContextProperty("zaodLite", {str(lite).lower()!r} == "true")
engine.rootContext().setContextProperty("zaodScale", {scale!r})
engine.load(os.path.abspath({str(SURFACE_DIR / (name + '.qml'))!r}))
roots = engine.rootObjects()
if not roots:
    sys.exit("surface did not load: " + {name!r})
window = roots[0]
window.resize({WIDTH}, {HEIGHT})
window.show()
for _ in range(5):
    app.processEvents()
image = window.grabWindow()
if image.isNull():
    sys.exit("empty grab: " + {name!r})
if not image.save({str(out_path)!r}):
    sys.exit("could not save: " + {str(out_path)!r})
print({name!r}, {theme!r}, image.width(), "x", image.height())
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip().splitlines()[-1])
    return result.stdout.strip()


def capture_app(app_id: str, theme: str, out_path: Path, lite: bool = False, scale: float = 1.0) -> str:
    env = dict(os.environ)
    if lite:
        env["ZAOD_LITE"] = "1"
    env["ZAOD_TEXT_SCALE"] = str(round(scale * 100))
    result = subprocess.run(
        [sys.executable, str(RENDER_APP), app_id, theme, str(out_path)],
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip().splitlines()[-1])
    return result.stdout.strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", default=None, help="limit to these surfaces")
    parser.add_argument(
        "--lite",
        action="store_true",
        help="also capture the lite profile at 150%% text, as -lite150 images",
    )
    parser.add_argument("--out", default=str(OUTPUT_ROOT))
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    wanted = set(args.only) if args.only else None
    captured, failed = [], []
    manifest = {}

    for name in QML_SURFACES:
        if wanted and name not in wanted:
            continue
        for theme in THEMES:
            path = out_root / f"{name}-{theme}.png"
            try:
                captured.append(capture_qml(name, theme, path))
                manifest.setdefault(name, {"kind": "qml"})[theme] = path.name
            except RuntimeError as error:
                failed.append(f"qml/{name}/{theme}: {error}")

    for app_id in app_ids():
        if wanted and app_id not in wanted:
            continue
        for theme in THEMES:
            path = out_root / f"{app_id}-{theme}.png"
            try:
                captured.append(capture_app(app_id, theme, path))
                manifest.setdefault(app_id, {"kind": "app"})[theme] = path.name
            except RuntimeError as error:
                failed.append(f"app/{app_id}/{theme}: {error}")

    if args.lite:
        # Evidence for the lite-mode and text-scale sections of the report.
        lite_surfaces = ("desktop", "startmenu", "kit")
        for name in lite_surfaces:
            for theme in THEMES:
                path = out_root / f"{name}-lite150-{theme}.png"
                try:
                    captured.append(capture_qml(name, theme, path, lite=True, scale=1.5))
                except RuntimeError as error:
                    failed.append(f"qml/{name}/lite150/{theme}: {error}")
        for app_id in ("notes", "tasks", "control-center"):
            if not (REPO_ROOT / "apps" / app_id / "payload" / "main.py").is_file():
                continue
            for theme in THEMES:
                path = out_root / f"{app_id}-lite150-{theme}.png"
                try:
                    captured.append(capture_app(app_id, theme, path, lite=True, scale=1.5))
                except RuntimeError as error:
                    failed.append(f"app/{app_id}/lite150/{theme}: {error}")

    for line in captured:
        print(f"  captured {line}")
    for line in failed:
        print(f"  FAILED   {line}")

    (out_root / "manifest.json").write_text(
        json.dumps(
            {
                "meta": {
                    "generator": "desktop/design/tools/capture_surfaces.py",
                    "resolution": f"{WIDTH}x{HEIGHT}",
                    "themes": list(THEMES),
                    "note": "Rendered from source. Qt Quick surfaces use the real engine; apps are launched per package in their own process.",
                },
                "surfaces": manifest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"capture_surfaces: {len(captured)} images, {len(failed)} failed -> {out_root}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

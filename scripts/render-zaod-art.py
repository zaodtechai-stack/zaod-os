#!/usr/bin/env python3
"""Render the image's SVG art to PNG so nothing depends on an SVG loader.

Run inside the built root filesystem: ``python3 /tmp/render-zaod-art.py``.

Icons and wallpaper were both blank on hardware because the only copies in the
image were SVG, and loading those needs librsvg's gdk-pixbuf loader to be built
into the loader cache. Rendering once, at build time, means the panel, the app
grid, GTK and swaybg all find a PNG and cannot fail that way again.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ICON_SIZES = (64, 128, 256)
ICON_ROOT = Path("/usr/share/icons/hicolor")
WALLPAPER_ROOT = Path("/usr/share/wallpapers/zaod")
WALLPAPER_SIZE = (2560, 1440)


def render(svg: Path, target: Path, size) -> bool:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        print(f"  FAIL {svg.name}: the renderer rejected it", file=sys.stderr)
        return False
    width, height = size if isinstance(size, tuple) else (size, size)
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(target), "PNG"):
        print(f"  FAIL {target}: could not be written", file=sys.stderr)
        return False
    return True


def main() -> int:
    failures = 0
    rendered = 0

    for svg in sorted((ICON_ROOT / "scalable" / "apps").glob("*.svg")):
        for size in ICON_SIZES:
            target = ICON_ROOT / f"{size}x{size}" / "apps" / f"{svg.stem}.png"
            if render(svg, target, size):
                rendered += 1
            else:
                failures += 1
    print(f"  icons: {rendered} PNG files rendered, {failures} failed")

    for svg in sorted(WALLPAPER_ROOT.glob("*.svg")):
        target = svg.with_suffix(".png")
        if render(svg, target, WALLPAPER_SIZE):
            rendered += 1
            print(f"  wallpaper {svg.name} -> {target.name}")
        else:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

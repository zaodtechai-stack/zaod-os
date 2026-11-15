#!/usr/bin/env python3
"""Render one first-party app window to a PNG at the 1366x768 floor.

Run in a subprocess by capture_surfaces.py so that every app gets a clean import
namespace (each `.zaod` package ships its own `backend`/`main` module names) and
a fresh QApplication, exactly like the package launcher does.

Usage: python3 _render_app.py <app-id> <light|dark> <output.png>
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    app_id, theme, out_path = sys.argv[1:4]
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["ZAOD_THEME"] = theme
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

    # Apps that shell out to zaodlib (Store) can be rendered from a checkout by
    # pointing at the in-tree library; on a real system it lives in /usr/lib/zaod.
    bundled = REPO_ROOT / "zaod"
    if (bundled / "zaodlib" / "__init__.py").is_file():
        os.environ.setdefault("ZAOD_LIB", str(bundled))

    sys.path.insert(0, str(REPO_ROOT / "apps" / "lib"))
    import zaodapp

    app = zaodapp.make_app([])

    payload_dir = REPO_ROOT / "apps" / app_id / "payload"
    sys.path.insert(0, str(payload_dir))
    spec = importlib.util.spec_from_file_location(f"zaod_app_{app_id.replace('-', '_')}", payload_dir / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    window = module.build_window()
    window.resize(1366, 768)
    window.show()
    for _ in range(4):
        app.processEvents()

    image = window.grab()
    saved = image.save(out_path)
    window.close()
    for _ in range(2):
        app.processEvents()
    sys.stdout.write(f"{app_id} {theme} {image.width()}x{image.height()}\n")
    sys.stdout.flush()
    if not saved:
        sys.stderr.write(f"could not write {out_path}\n")
        sys.stderr.flush()
        os._exit(1)
    # Qt teardown segfaults under the offscreen plugin once the window is gone;
    # the image is already on disk, so leave the process deliberately.
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())

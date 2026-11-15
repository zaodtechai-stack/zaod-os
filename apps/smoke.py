"""Offscreen smoke test: build every first-party app window and screenshot it.

Runs without a display (``QT_QPA_PLATFORM=offscreen``), so CI can prove that
each shipped app constructs its window and paints. Screenshots land in
``build/out/screens/``.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "lib"))

from PySide6.QtWidgets import QApplication  # noqa: E402 - environment set above


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    app = QApplication.instance() or QApplication([])
    screens = ROOT.parent / "build" / "out" / "screens"
    screens.mkdir(parents=True, exist_ok=True)
    failures = []
    windows = []
    for directory in sorted(ROOT.iterdir()):
        entry = directory / "payload" / "main.py"
        if not entry.is_file():
            continue
        try:
            module = load_module(entry, f"zaod_app_{directory.name.replace('-', '_')}")
            window = module.build_window()
            window.show()
            app.processEvents()
            pixmap = window.grab()
            target = screens / f"{directory.name}.png"
            pixmap.save(str(target))
            print(f"ok    {directory.name:12s} {pixmap.width()}x{pixmap.height()} -> {target.name}")
            windows.append(window)
        except Exception as error:  # noqa: BLE001 - report every app, not just the first
            failures.append((directory.name, error))
            print(f"FAIL  {directory.name:12s} {type(error).__name__}: {error}")
    for window in windows:
        window.deleteLater()
    app.processEvents()
    if failures:
        print(f"\n{len(failures)} app(s) failed to start")
        return 1
    print("\nall first-party app windows started and painted")
    return 0


if __name__ == "__main__":
    sys.exit(main())

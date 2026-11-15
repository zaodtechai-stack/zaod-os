#!/usr/bin/env python3
"""Compile every Zaod QML surface and report errors.

The Phase 6 gate validated tokens, generated artefacts and contrast, but it never
asked a QML engine whether the files parse. That is how a `ZaodTheme.qml` that
could not compile, and a `ZaodButton` that overrode a final property, both
shipped while `check_design_tokens.py` stayed green.

This checker loads each component with QQmlComponent and fails on `Status.Error`.
It needs PySide6 (already the application runtime); when Qt is absent it skips
with a clear message instead of pretending the surfaces were checked.

Usage: python3 desktop/design/tools/check_qml.py [--verbose]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DESIGN_ROOT = REPO_ROOT / "desktop" / "design"

# Directories whose .qml files are surfaces in their own right.
SURFACE_DIRS = (
    DESIGN_ROOT / "qml",
    DESIGN_ROOT / "shell",
    DESIGN_ROOT / "tools" / "surfaces",
)
# desktop/sddm/themes/zaod/Main.qml is deliberately excluded: it imports the
# SddmComponents module that only exists inside the greeter runtime, so it can
# only be compiled on a booted image. docs/reports/phase-6.md records it as
# unverified here.


def qml_files() -> list[Path]:
    files = []
    for directory in SURFACE_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.qml")):
            files.append(path)
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine
    except ImportError:
        print(
            "check_qml: PySide6 is not installed on this host, QML compilation NOT checked",
            file=sys.stderr,
        )
        return 0

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(DESIGN_ROOT))

    failures = []
    checked = 0
    for path in qml_files():
        checked += 1
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
        if component.status() == QQmlComponent.Status.Error:
            detail = "; ".join(error.toString() for error in component.errors())
            failures.append((path, detail))
            print(f"FAIL {path.relative_to(REPO_ROOT)}: {detail}")
        elif args.verbose:
            print(f"ok   {path.relative_to(REPO_ROOT)}")

    print(f"check_qml: {checked} surfaces compiled, {len(failures)} failed")
    del app
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

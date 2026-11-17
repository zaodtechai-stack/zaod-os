#!/usr/bin/env python3
"""Prove every app the image ships can actually open its window.

Run inside the built image (``python3 /usr/local/lib/zaod/smoke-apps.py``) or on
a staging root with ``--root``. Each app is imported the way its launcher runs it
and its ``build_window`` is called with an offscreen Qt platform, so a missing
module, a broken import or a widget that cannot construct fails here instead of
on someone's laptop.

The image already shipped this failure twice: every app died with
"ModuleNotFoundError: No module named 'zaod_tokens'" because the shared helper was
copied without the module it imports, and the checkout had no way to catch it.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def load_app(main_py: Path, name: str):
    payload = main_py.parent
    for entry in (str(payload), str(payload / "lib")):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location(f"zaod_app_{name.replace('-', '_')}", main_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/", help="root filesystem holding /opt/zaod/apps")
    parser.add_argument(
        "--only",
        metavar="APP",
        help="check a single app (each app gets its own process: every one ships a "
        "module called backend, so a shared interpreter would test the wrong file)",
    )
    args = parser.parse_args()

    apps_dir = Path(args.root) / "opt/zaod/apps"
    if not apps_dir.is_dir():
        print(f"smoke-apps: no apps at {apps_dir}", file=sys.stderr)
        return 1

    if args.only:
        app_dir = apps_dir / args.only
        main_py = app_dir / "payload" / "main.py"
        if not main_py.is_file():
            print(f"smoke-apps: no app at {app_dir}", file=sys.stderr)
            return 1
        return check_one(main_py, app_dir.name)

    failures = 0
    checked = 0
    for app_dir in sorted(apps_dir.iterdir()):
        main_py = app_dir / "payload" / "main.py"
        if not main_py.is_file():
            continue
        checked += 1
        parent = Path(__file__).resolve()
        result = subprocess.run(
            [sys.executable, str(parent), "--root", str(Path(args.root).resolve()), "--only", app_dir.name],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"  ok   {app_dir.name:<16} {(result.stdout.strip().splitlines() or [''])[-1].strip()}")
        else:
            failures += 1
            print(f"  FAIL {app_dir.name}", file=sys.stderr)
            if result.stdout.strip():
                print(result.stdout.rstrip(), file=sys.stderr)
            if result.stderr.strip():
                print(result.stderr.rstrip(), file=sys.stderr)

    print(f"smoke-apps: {checked} apps checked, {failures} failed")
    return 1 if failures or checked == 0 else 0


def check_one(main_py: Path, name: str) -> int:
    """Import one app and build its window. Runs in its own process."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    try:
        module = load_app(main_py, name)
        build = getattr(module, "build_window", None)
        if build is None:
            print(f"{name}: no build_window()")
            return 0
        window = build()
        if window is None:
            raise RuntimeError("build_window() returned nothing")
        width = window.width() or window.sizeHint().width()
        height = window.height() or window.sizeHint().height()
        if width <= 0 or height <= 0:
            raise RuntimeError("window has no size")
        print(f"{width}x{height}")
        app.processEvents()
        return 0
    except Exception:  # noqa: BLE001 - any failure is the point of the check
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Start a launcher entry the way the panel does.

The panel calls ``Gio.AppInfo.launch([], None)``. This runs the same call for one
.desktop entry so a build can prove that clicking an icon starts the app - the
executable being startable on its own is a different thing.

Usage: gio-launch-entry.py APP.desktop
"""

from __future__ import annotations

import sys

from gi.repository import Gio


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    info = Gio.DesktopAppInfo.new(argv[1])
    if info is None:
        print(f"gio-launch-entry: no desktop entry {argv[1]}", file=sys.stderr)
        return 1
    info.launch([], None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

#!/usr/bin/env python3
"""Emit the Python token module the first-party applications import.

The Qt Quick surfaces read colours from the generated `ZaodTheme` singleton.
The first-party apps are PySide6 widgets, so they need the same tokens in
Python; before this generator existed they carried a hand-copied palette that
had drifted from `tokens.json` (different accent, borders far below the 3:1 UI
contrast floor, and no dark-mode-safe `onAccent`).

Output: apps/lib/zaod_tokens.py  (generated, never edited by hand)
"""

from __future__ import annotations

import argparse
import pprint
import sys
from pathlib import Path

DESIGN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DESIGN_ROOT.parents[1]
sys.path.insert(0, str(DESIGN_ROOT / "tools"))

from tokens_to_qml import COLOR_ROLES, TYPE_NAMES, load_tokens  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "apps" / "lib" / "zaod_tokens.py"

# Short names the app code has always used, mapped onto real colour roles.
ALIASES = {
    "window": "background",
    "text": "textPrimary",
    "muted": "textSecondary",
    "overlay": "surfaceOverlay",
}


def render_module(tokens: dict) -> str:
    themes = {
        name: {role: tokens["themes"][name][role] for role in COLOR_ROLES}
        for name in ("light", "dark")
    }
    scale = {
        TYPE_NAMES[step["name"]]: {
            "size": step["size"],
            "lineHeight": step["lineHeight"],
            "weight": step["weight"],
            "tracking": step["tracking"],
        }
        for step in tokens["typography"]["scale"]
    }
    bodies = [
        ("ROLES", tuple(COLOR_ROLES)),
        ("ALIASES", ALIASES),
        ("THEMES", themes),
        ("SPACING", {str(k): v for k, v in tokens["spacing"].items()}),
        ("RADII", tokens["radii"]),
        ("BORDERS", tokens["borders"]),
        ("MOTION", tokens["motion"]),
        ("ELEVATION", tokens["elevation"]),
        ("TYPE_SCALE", scale),
        ("FOCUS", tokens["focus"]),
        ("OPACITY", tokens["opacity"]),
        ("LITE", tokens["lite"]),
        ("FONT_FAMILIES", tokens["typography"]["families"]),
        ("SCALE_RANGE", tokens["typography"]["scaleRange"]),
    ]
    lines = [
        '"""Zaod Fluent tokens for the PySide6 first-party applications.',
        "",
        "GENERATED FILE - do not edit.",
        "Source: desktop/design/tokens/tokens.json",
        "Generator: desktop/design/tools/tokens_to_python.py",
        "",
        "Colours, spacing, radii, type sizes and motion all come from the design",
        "tokens, so an app can never drift from the Qt Quick surfaces.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
    ]
    for name, value in bodies:
        lines.append(f"{name} = {pprint.pformat(value, width=96, sort_dicts=False)}")
        lines.append("")
    lines.append("")
    lines.append("def role_map(theme: str = 'light') -> dict[str, str]:")
    lines.append('    """Colour roles plus the short aliases app code uses."""')
    lines.append("    colours = dict(THEMES[theme])")
    lines.append("    for alias, role in ALIASES.items():")
    lines.append("        colours[alias] = colours[role]")
    lines.append("    return colours")
    lines.append("")
    return "\n".join(lines)


def write_output(tokens: dict, path: Path = OUTPUT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_module(tokens), encoding="utf-8")
    return path


def is_stale(tokens: dict, path: Path = OUTPUT_PATH) -> bool:
    if not path.is_file():
        return True
    return path.read_text(encoding="utf-8") != render_module(tokens)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed module is stale")
    args = parser.parse_args(argv)
    tokens = load_tokens()
    if args.check:
        if is_stale(tokens):
            print(f"tokens_to_python: {OUTPUT_PATH} is stale, run the generator", file=sys.stderr)
            return 1
        print(f"tokens_to_python: {OUTPUT_PATH} is up to date")
        return 0
    write_output(tokens)
    print(f"tokens_to_python: wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

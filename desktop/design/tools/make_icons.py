#!/usr/bin/env python3
"""Generate the Zaod icon set from the design tokens.

The Phase 6 delivery shipped nine stroke glyphs, which cannot cover thirteen
applications plus the shell navigation the taskbar, start menu and quick
settings actually need. This generator produces two families from one geometry
vocabulary:

* ``nav``  - 24 px stroke glyphs for every shell action, in a light and a dark
             file so an ``Image`` can pick the right one without a tint effect.
* ``app``  - 64 px application tiles built from three token-only treatments
             (accent fill, accent-subtle fill, bordered surface).

Every colour is read from ``tokens.json``. Nothing here introduces a hue, a font
or a dependency, and the output is deterministic: the same tokens always produce
byte-identical SVG.

Usage:
  python3 desktop/design/tools/make_icons.py            # write the icons
  python3 desktop/design/tools/make_icons.py --check     # fail when stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DESIGN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_ROOT / "tools"))

from tokens_to_qml import load_tokens

ICON_ROOT = DESIGN_ROOT / "icons"
NAV_DIR = ICON_ROOT / "nav"
APP_DIR = ICON_ROOT / "app"
MANIFEST_PATH = ICON_ROOT / "icons.json"

NAV_SIZE = 24

# Geometry vocabulary on a 24 px grid. Each primitive is one of:
#   ("c", cx, cy, r)          circle
#   ("r", x, y, w, h, rx)     rounded rectangle
#   ("l", x1, y1, x2, y2)     line
#   ("p", "d")                path
#   ("q", "d")                filled path
NAV_GLYPHS: dict[str, list] = {
    "logo": [("q", "M12 3 21 8v8l-9 5-9-5V8z"), ("p", "M12 8v5l4 2")],
    "app-grid": [
        ("r", 3.5, 3.5, 7, 7, 2), ("r", 13.5, 3.5, 7, 7, 2),
        ("r", 3.5, 13.5, 7, 7, 2), ("r", 13.5, 13.5, 7, 7, 2),
    ],
    "search": [("c", 11, 11, 6.5), ("l", 15.5, 15.5, 20.5, 20.5)],
    "settings": [("c", 12, 12, 3), ("c", 12, 12, 8),
                 ("l", 12, 1.5, 12, 4), ("l", 12, 20, 12, 22.5),
                 ("l", 2.6, 6.75, 4.9, 8), ("l", 19.1, 16, 21.4, 17.25)],
    "network": [("p", "M2.5 8.5a14 14 0 0 1 19 0"), ("p", "M5.5 12a9.5 9.5 0 0 1 13 0"),
                ("p", "M8.5 15.5a5 5 0 0 1 7 0"), ("q", "M12 19.5a1.6 1.6 0 1 0 0 .1z")],
    "network-off": [("p", "M2.5 8.5a14 14 0 0 1 19 0"), ("l", 4, 20, 20, 4),
                    ("p", "M8.5 15.5a5 5 0 0 1 7 0")],
    "bluetooth": [("p", "M8 7.5 16 16.5 12 20V4l4 3.5L8 16.5")],
    "volume": [("p", "M4 9.5h3.5L13 5v14l-5.5-4.5H4z"),
               ("p", "M16.5 9a4.5 4.5 0 0 1 0 6"), ("p", "M19 6.5a8 8 0 0 1 0 11")],
    "volume-off": [("p", "M4 9.5h3.5L13 5v14l-5.5-4.5H4z"), ("l", 16.5, 9.5, 21, 14),
                   ("l", 21, 9.5, 16.5, 14)],
    "brightness": [("c", 12, 12, 4.5), ("l", 12, 1.5, 12, 3.5), ("l", 12, 20.5, 12, 22.5),
                   ("l", 1.5, 12, 3.5, 12), ("l", 20.5, 12, 22.5, 12),
                   ("l", 4.2, 4.2, 5.6, 5.6), ("l", 18.4, 18.4, 19.8, 19.8),
                   ("l", 4.2, 19.8, 5.6, 18.4), ("l", 18.4, 5.6, 19.8, 4.2)],
    "night-light": [("p", "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z")],
    "airplane": [("p", "M12 3c1 0 1.5 1 1.5 2.5V9l7 4v2.5l-7-2v4l2.5 2V21L12 19.5 8 21v-1.5l2.5-2v-4l-7 2V13l7-4V5.5C10.5 4 11 3 12 3z")],
    "battery": [("r", 2.5, 8, 17, 8, 2.5), ("l", 21.5, 10.5, 21.5, 13.5), ("l", 5, 10.5, 5, 13.5)],
    "battery-charging": [("r", 2.5, 8, 17, 8, 2.5), ("l", 21.5, 10.5, 21.5, 13.5),
                         ("p", "M12.5 9 9 12.5h3l-1 3 3.5-3.5h-3z")],
    "power": [("c", 12, 13, 7.5), ("l", 12, 2.5, 12, 10)],
    "restart": [("p", "M20 12a8 8 0 1 1-2.6-5.9"), ("p", "M20 3.5V9h-5.5")],
    "lock": [("r", 4.5, 10.5, 15, 10, 2.5), ("p", "M8 10.5V8a4 4 0 0 1 8 0v2.5")],
    "user": [("c", 12, 8.5, 4), ("p", "M4.5 20.5a7.5 7.5 0 0 1 15 0")],
    "bell": [("p", "M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z"), ("p", "M10 20.5a2 2 0 0 0 4 0")],
    "calendar": [("r", 3.5, 5, 17, 15, 2.5), ("l", 3.5, 10, 20.5, 10),
                 ("l", 8, 2.5, 8, 6.5), ("l", 16, 2.5, 16, 6.5)],
    "chevron-right": [("p", "M9.5 5.5 16 12l-6.5 6.5")],
    "chevron-down": [("p", "M5.5 9.5 12 16l6.5-6.5")],
    "check": [("p", "M4.5 12.5 9.5 17.5 19.5 6.5")],
    "close": [("l", 5.5, 5.5, 18.5, 18.5), ("l", 18.5, 5.5, 5.5, 18.5)],
    "plus": [("l", 12, 5, 12, 19), ("l", 5, 12, 19, 12)],
    "minus": [("l", 5, 12, 19, 12)],
    "edit": [("p", "M4.5 19.5h4l10-10-4-4-10 10z"), ("l", 14.5, 5.5, 18.5, 9.5)],
    "trash": [("p", "M4.5 7.5h15"), ("p", "M6.5 7.5 8 20.5h8l1.5-13"),
              ("p", "M9.5 7.5V4.5h5v3")],
    "download": [("p", "M12 3.5v11"), ("p", "M7.5 10 12 14.5 16.5 10"),
                 ("p", "M4.5 17.5v3h15v-3")],
    "update": [("p", "M4 12a8 8 0 0 1 13.6-5.7"), ("p", "M17.5 2.5v4h-4"),
               ("p", "M20 12a8 8 0 0 1-13.6 5.7"), ("p", "M6.5 21.5v-4h4")],
    "folder": [("p", "M3 7.5a2 2 0 0 1 2-2h4l2 2.5h6a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z")],
    "terminal": [("r", 2.5, 4.5, 19, 15, 2.5), ("p", "M6.5 10 9.5 13 6.5 16"),
                 ("l", 12, 16, 17, 16)],
    "play": [("q", "M8.5 5.5 18 12l-9.5 6.5z")],
    "image": [("r", 3, 4.5, 18, 15, 2.5), ("c", 8.5, 9.5, 1.8), ("p", "M3.5 17 9 12l4 3.5 3-2.5 4.5 4")],
    "code": [("p", "M8.5 7.5 3.5 12l5 4.5"), ("p", "M15.5 7.5 20.5 12l-5 4.5"),
             ("l", 13.5, 5, 10.5, 19)],
    "shield": [("p", "M12 3 20 6v6c0 4.5-3.2 7.6-8 9-4.8-1.4-8-4.5-8-9V6z")],
    "info": [("c", 12, 12, 8.5), ("l", 12, 11, 12, 16.5), ("q", "M12 7.2a1.1 1.1 0 1 0 0 .1z")],
    "warning": [("p", "M12 3.5 21.5 20H2.5z"), ("l", 12, 9, 12, 14), ("q", "M12 16.4a1.1 1.1 0 1 0 0 .1z")],
    "search-list": [("l", 3.5, 6, 12, 6), ("l", 3.5, 12, 12, 12), ("l", 3.5, 18, 9, 18),
                    ("c", 17, 9, 3.5), ("l", 19.5, 11.5, 21.5, 13.5)],
}

# 15 application surfaces, each mapped to a glyph and a token-only treatment.
APP_TILES: dict = {
    "notes": {"glyph": "edit", "tone": "subtle"},
    "tasks": {"glyph": "check", "tone": "subtle"},
    "calculator": {"glyph": "plus", "tone": "bordered"},
    "converter": {"glyph": "update", "tone": "bordered"},
    "clock": {"glyph": "restart", "tone": "bordered"},
    "calendar": {"glyph": "calendar", "tone": "subtle"},
    "files": {"glyph": "folder", "tone": "bordered"},
    "monitor": {"glyph": "battery", "tone": "bordered"},
    "editor": {"glyph": "code", "tone": "subtle"},
    "viewer": {"glyph": "image", "tone": "solid"},
    "store": {"glyph": "download", "tone": "solid"},
    "firefox": {"glyph": "network", "tone": "solid"},
    "studio": {"glyph": "terminal", "tone": "solid"},
    "control-center": {"glyph": "settings", "tone": "solid"},
    "oobe": {"glyph": "logo", "tone": "solid"},
}

# Token treatments: each is (fill role, glyph role, border role or None).
TREATMENTS = {
    "solid": ("accent", "onAccent", None),
    "subtle": ("accentSubtle", "accent", "accent"),
    "bordered": ("surface", "accent", "border"),
}


def _primitives(glyph: list) -> tuple[list, list]:
    """Split primitives into stroked and filled SVG fragments."""
    stroked, filled = [], []
    for primitive in glyph:
        kind = primitive[0]
        if kind == "c":
            stroked.append(
                f'<circle cx="{primitive[1]}" cy="{primitive[2]}" r="{primitive[3]}"/>'
            )
        elif kind == "r":
            x, y, w, h, rx = primitive[1:]
            stroked.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')
        elif kind == "l":
            stroked.append(
                f'<line x1="{primitive[1]}" y1="{primitive[2]}" '
                f'x2="{primitive[3]}" y2="{primitive[4]}"/>'
            )
        elif kind == "p":
            stroked.append(f'<path d="{primitive[1]}"/>')
        elif kind == "q":
            filled.append(f'<path d="{primitive[1]}"/>')
    return stroked, filled


def render_nav(tokens: dict, name: str, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    stroke = theme["textPrimary"]
    stroked, filled = _primitives(NAV_GLYPHS[name])
    width = 1.75
    body = []
    if stroked:
        body.append(
            f'<g fill="none" stroke="{stroke}" stroke-width="{width}" '
            'stroke-linecap="round" stroke-linejoin="round">'
        )
        body.extend(stroked)
        body.append("</g>")
    if filled:
        body.append(f'<g fill="{stroke}" stroke="none">')
        body.extend(filled)
        body.append("</g>")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {NAV_SIZE} {NAV_SIZE}" '
        f'width="{NAV_SIZE}" height="{NAV_SIZE}" role="img">\n'
        f"<title>Zaod {name} ({theme_name})</title>\n"
        + "\n".join(body)
        + "\n</svg>\n"
    )


def render_app(tokens: dict, app_id: str, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    spec = APP_TILES[app_id]
    fill_role, glyph_role, border_role = TREATMENTS[spec["tone"]]
    size = tokens["layout"]["iconApp"]
    radius = tokens["radii"]["lg"]
    inset = tokens["spacing"]["1"]
    glyph_scale = 2.0  # 24 px glyph drawn on a 48 px box inside the 64 px tile
    offset = (size - NAV_SIZE * glyph_scale) / 2

    stroked, filled = _primitives(NAV_GLYPHS[spec["glyph"]])
    stroke_width = 1.75 / glyph_scale
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            f'width="{size}" height="{size}" role="img">'
        ),
        f"<title>Zaod {app_id} application icon ({theme_name})</title>",
        f'<rect x="{inset}" y="{inset}" width="{size - inset * 2}" height="{size - inset * 2}" '
        f'rx="{radius}" fill="{theme[fill_role]}"'
        + (f' stroke="{theme[border_role]}" stroke-width="{tokens["borders"]["hairline"]}"' if border_role else "")
        + "/>",
    ]
    if stroked:
        parts.append(
            f'<g transform="translate({offset} {offset}) scale({glyph_scale})" fill="none" '
            f'stroke="{theme[glyph_role]}" stroke-width="{stroke_width}" '
            'stroke-linecap="round" stroke-linejoin="round">'
        )
        parts.extend(stroked)
        parts.append("</g>")
    if filled:
        parts.append(
            f'<g transform="translate({offset} {offset}) scale({glyph_scale})" '
            f'fill="{theme[glyph_role]}" stroke="none">'
        )
        parts.extend(filled)
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def outputs(tokens: dict) -> dict:
    """Every generated icon, keyed by path."""
    result = {}
    for name in NAV_GLYPHS:
        for theme_name in ("light", "dark"):
            result[NAV_DIR / f"{name}-{theme_name}.svg"] = render_nav(tokens, name, theme_name)
    for app_id in APP_TILES:
        for theme_name in ("light", "dark"):
            result[APP_DIR / f"{app_id}-{theme_name}.svg"] = render_app(tokens, app_id, theme_name)
    manifest = {
        "meta": {
            "generator": "desktop/design/tools/make_icons.py",
            "source": "desktop/design/tokens/tokens.json",
            "navSize": NAV_SIZE,
            "appSize": tokens["layout"]["iconApp"],
            "note": "Every icon ships a light and a dark file because the colours are baked from the tokens; an Image picks the file for the active theme.",
        },
        "nav": {name: {"light": f"nav/{name}-light.svg", "dark": f"nav/{name}-dark.svg"} for name in NAV_GLYPHS},
        "apps": {
            app_id: {
                "glyph": spec["glyph"],
                "tone": spec["tone"],
                "light": f"app/{app_id}-light.svg",
                "dark": f"app/{app_id}-dark.svg",
            }
            for app_id, spec in APP_TILES.items()
        },
    }
    result[MANIFEST_PATH] = json.dumps(manifest, indent=2) + "\n"
    return result


def write_outputs(tokens: dict) -> list:
    written = []
    NAV_DIR.mkdir(parents=True, exist_ok=True)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs(tokens).items():
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def stale_paths(tokens: dict) -> list:
    stale = []
    for path, content in outputs(tokens).items():
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            stale.append(path)
    return stale


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if committed icons are stale")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    tokens = load_tokens()
    if args.check:
        stale = stale_paths(tokens)
        for path in stale:
            print(f"make_icons: stale {path}", file=sys.stderr)
        if stale:
            return 1
        print(f"make_icons: {len(outputs(tokens))} icon files up to date")
        return 0
    written = write_outputs(tokens)
    if not args.quiet:
        print(f"make_icons: wrote {len(written)} files ({len(NAV_GLYPHS)} nav glyphs, {len(APP_TILES)} app tiles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

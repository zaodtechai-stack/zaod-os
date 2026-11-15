#!/usr/bin/env python3
"""Generate the original Zaod OS wallpapers from the design tokens.

Every wallpaper is deterministic SVG geometry built from the 4 px grid and the
theme palette, so the artwork is reproducible and carries no third-party
material. Three designs are produced in a light and a dark variant.

Output: desktop/design/wallpapers/<id>-<theme>.svg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DESIGN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_ROOT / "tools"))

from tokens_to_qml import load_tokens

WALLPAPER_ROOT = DESIGN_ROOT / "wallpapers"
WIDTH = 2560
HEIGHT = 1440


def _svg_open(title: str, theme_name: str) -> list:
    return [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" '
            'shape-rendering="geometricPrecision">'
        ),
        f"<title>Zaod OS {title} ({theme_name})</title>",
        "<desc>Original generative artwork generated from the Zaod Fluent design tokens.</desc>",
    ]


def render_aurora(tokens: dict, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    grid = tokens["meta"]["grid"]
    dark = theme_name == "dark"
    lines = _svg_open("Aurora", theme_name)
    lines.append("<defs>")
    lines.append(
        '<linearGradient id="sky" x1="0" y1="0" x2="0.4" y2="1">'
        f'<stop offset="0" stop-color="{theme["background"]}"/>'
        f'<stop offset="1" stop-color="{theme["surface"]}"/>'
        "</linearGradient>"
    )
    for index, opacity in enumerate((0.55, 0.4, 0.28)):
        lines.append(
            f'<radialGradient id="glow{index}" cx="0.5" cy="0.5" r="0.5">'
            f'<stop offset="0" stop-color="{theme["accent"]}" stop-opacity="{opacity}"/>'
            f'<stop offset="1" stop-color="{theme["accent"]}" stop-opacity="0"/>'
            "</radialGradient>"
        )
    lines.append("</defs>")
    lines.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#sky)"/>')

    centers = ((0.28, 0.34, 1.0), (0.68, 0.6, 1.35), (0.5, 0.92, 0.85))
    for index, (cx, cy, scale) in enumerate(centers):
        radius = int(WIDTH * 0.34 * scale)
        lines.append(
            f'<circle cx="{int(WIDTH * cx)}" cy="{int(HEIGHT * cy)}" r="{radius}" '
            f'fill="url(#glow{index})"/>'
        )

    # Concentric arcs on the 4 px grid.
    base = 24 * grid
    for step, width in enumerate((12 * grid, 9 * grid, 6 * grid, 3 * grid)):
        inset = base + step * width
        radius = int(WIDTH * 0.36 - inset * 0.5)
        lines.append(
            f'<circle cx="{WIDTH // 2}" cy="{int(HEIGHT * 0.44)}" r="{radius}" fill="none" '
            f'stroke="{theme["accent"]}" stroke-opacity="{0.32 - step * 0.06:.2f}" '
            f'stroke-width="{max(grid, width // 6)}"/>'
        )
    if dark:
        lines.append(
            f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{theme["scrim"]}" opacity="0.18"/>'
        )
    lines.append("</svg>")
    return "\n".join(lines)


def render_lattice(tokens: dict, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    grid = tokens["meta"]["grid"]
    cell = 16 * grid
    lines = _svg_open("Lattice", theme_name)
    lines.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{theme["background"]}"/>')
    columns = WIDTH // cell + 1
    rows = HEIGHT // cell + 1
    for row in range(rows):
        for column in range(columns):
            cx = column * cell + cell // 2
            cy = row * cell + cell // 2
            dx = (cx - WIDTH / 2) / (WIDTH / 2)
            dy = (cy - HEIGHT / 2) / (HEIGHT / 2)
            distance = min(1.0, (dx * dx + dy * dy) ** 0.5)
            opacity = round(max(0.0, 0.5 - distance * 0.42), 3)
            if opacity <= 0.02:
                continue
            size = cell // 2
            radius = tokens["radii"]["sm"]
            lines.append(
                f'<rect x="{cx - size // 2}" y="{cy - size // 2}" width="{size}" height="{size}" '
                f'rx="{radius}" fill="{theme["accent"]}" opacity="{opacity}"/>'
            )
    lines.append(
        f'<circle cx="{WIDTH // 2}" cy="{HEIGHT // 2}" r="{int(WIDTH * 0.2)}" '
        f'fill="none" stroke="{theme["border"]}" stroke-opacity="0.25" stroke-width="{grid}"/>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


def render_horizon(tokens: dict, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    grid = tokens["meta"]["grid"]
    lines = _svg_open("Horizon", theme_name)
    lines.append("<defs>")
    lines.append(
        '<linearGradient id="band" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{theme["accent"]}" stop-opacity="0.42"/>'
        f'<stop offset="1" stop-color="{theme["accent"]}" stop-opacity="0.02"/>'
        "</linearGradient>"
    )
    lines.append("</defs>")
    lines.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{theme["background"]}"/>')
    horizon = int(HEIGHT * 0.62)
    for index in range(7):
        height = 20 * grid + index * 12 * grid
        opacity = round(0.14 - index * 0.015, 3)
        lines.append(
            f'<rect x="0" y="{horizon - height}" width="{WIDTH}" height="{height}" '
            f'fill="{theme["surfaceAlt"]}" opacity="{opacity}"/>'
        )
    lines.append(
        f'<rect x="0" y="{horizon}" width="{WIDTH}" height="{HEIGHT - horizon}" fill="url(#band)"/>'
    )
    lines.append(
        f'<rect x="0" y="{horizon}" width="{WIDTH}" height="{max(1, grid // 2)}" '
        f'fill="{theme["border"]}" opacity="0.5"/>'
    )
    lines.append(
        f'<circle cx="{int(WIDTH * 0.72)}" cy="{int(horizon - HEIGHT * 0.22)}" '
        f'r="{int(WIDTH * 0.09)}" fill="{theme["accent"]}" opacity="0.5"/>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Flat tier: the lite-profile wallpaper. Same geometry language, no radial
# gradients, no stacked translucent bands, no scrim pass and no sun disc, so a
# 2 GB machine without a GPU never composites a gradient it cannot afford.
# --------------------------------------------------------------------------


def render_aurora_flat(tokens: dict, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    grid = tokens["meta"]["grid"]
    lines = _svg_open("Aurora flat", theme_name)
    lines.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{theme["background"]}"/>')
    base = 24 * grid
    for step, width in enumerate((12 * grid, 9 * grid, 6 * grid, 3 * grid)):
        inset = base + step * width
        radius = int(WIDTH * 0.36 - inset * 0.5)
        lines.append(
            f'<circle cx="{WIDTH // 2}" cy="{int(HEIGHT * 0.44)}" r="{radius}" fill="none" '
            f'stroke="{theme["accent"]}" stroke-opacity="{0.28 - step * 0.05:.2f}" '
            f'stroke-width="{max(grid, width // 6)}"/>'
        )
    lines.append("</svg>")
    return "\n".join(lines)


def render_lattice_flat(tokens: dict, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    grid = tokens["meta"]["grid"]
    cell = 24 * grid
    lines = _svg_open("Lattice flat", theme_name)
    lines.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{theme["background"]}"/>')
    size = cell // 2
    radius = tokens["radii"]["sm"]
    for row in range(-1, 2):
        for column in range(-1, 2):
            opacity = 0.18 if (row or column) else 0.28
            cx = WIDTH // 2 + column * cell
            cy = HEIGHT // 2 + row * cell
            lines.append(
                f'<rect x="{cx - size // 2}" y="{cy - size // 2}" width="{size}" height="{size}" '
                f'rx="{radius}" fill="{theme["accent"]}" opacity="{opacity}"/>'
            )
    lines.append("</svg>")
    return "\n".join(lines)


def render_horizon_flat(tokens: dict, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    grid = tokens["meta"]["grid"]
    lines = _svg_open("Horizon flat", theme_name)
    lines.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{theme["background"]}"/>')
    horizon = int(HEIGHT * 0.62)
    lines.append(
        f'<rect x="0" y="{horizon}" width="{WIDTH}" height="{HEIGHT - horizon}" '
        f'fill="{theme["surfaceAlt"]}"/>'
    )
    lines.append(
        f'<rect x="0" y="{horizon}" width="{WIDTH}" height="{max(1, grid // 2)}" '
        f'fill="{theme["border"]}"/>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


FLAT_RENDERERS = {
    "zaod-aurora": render_aurora_flat,
    "zaod-lattice": render_lattice_flat,
    "zaod-horizon": render_horizon_flat,
}


RENDERERS = {
    "zaod-aurora": render_aurora,
    "zaod-lattice": render_lattice,
    "zaod-horizon": render_horizon,
}


def outputs(tokens: dict) -> dict:
    """Both render tiers: full, and the flat tier the lite profile selects."""
    result = {}
    for design in tokens["wallpapers"]:
        renderer = RENDERERS[design["id"]]
        flat_renderer = FLAT_RENDERERS[design["id"]]
        for theme_name in ("light", "dark"):
            result[WALLPAPER_ROOT / f"{design['id']}-{theme_name}.svg"] = renderer(tokens, theme_name)
            result[WALLPAPER_ROOT / f"{design['id']}-{theme_name}-flat.svg"] = flat_renderer(
                tokens, theme_name
            )
    return result


def write_outputs(tokens: dict) -> list:
    written = []
    WALLPAPER_ROOT.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--check", action="store_true", help="fail if committed wallpapers are stale")
    args = parser.parse_args(argv)
    tokens = load_tokens()
    if args.check:
        stale = stale_paths(tokens)
        if stale:
            for path in stale:
                print(f"make_wallpapers: stale {path}", file=sys.stderr)
            return 1
        print("make_wallpapers: all generated wallpapers are up to date")
        return 0
    for path in write_outputs(tokens):
        print(f"make_wallpapers: wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
